"""Frozen image encoders behind the Adapter contract. Owner: Workstream C. Needs the `ml` extra.

One preprocessing policy for every encoder, so the arms stay matched:
grayscale -> pad to square with black (keeps the whole radiograph; no center
crop that could cut a lesion off) -> bicubic resize to the encoder's input
size -> 3 identical channels -> scale to [0, 1] -> the encoder's published
mean/std. Weights load only from local .safetensors files: no pickles, no network.

Import this module explicitly; it is not re-exported from `adapters` so the
core package stays standard-library only.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

from ..common.paths import MODELS_DIR

IMAGENET = {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}
ENCODERS: dict[str, dict[str, Any]] = {
    "rad-dino": {"arch": "dinov2", "size": 518, "mean": [0.5307] * 3, "std": [0.2583] * 3, "dim": 768,
                 "output": "CLS token after the final layer norm (pooler_output)",
                 "source": "preprocessor_config.json mean/std; 518 px as in the model's training"},
    "resnet50-a1-in1k": {"arch": "resnet50", "size": 288, **IMAGENET, "dim": 2048,
                         "output": "global average pool before the classifier",
                         "source": "timm pretrained_cfg mean/std; 288 px test_input_size"},
}
PAD_POLICY = "JPEG draft decode >= target, grayscale, pad to square (black), bicubic resize, replicate to 3 channels"


def preprocessing(encoder_id: str) -> dict[str, Any]:
    spec = ENCODERS[encoder_id]
    return {"policy": PAD_POLICY, "size": spec["size"], "mean": spec["mean"], "std": spec["std"]}


def preprocessing_hash(encoder_id: str) -> str:
    return hashlib.sha256(json.dumps(preprocessing(encoder_id), sort_keys=True).encode()).hexdigest()[:12]


def revision(encoder_id: str) -> str | None:
    prov = MODELS_DIR / encoder_id / "PROVENANCE.json"
    return json.loads(prov.read_text())["source"].get("revision") if prov.exists() else None


def load_image(path: Path, size: int):
    """Return a 3 x size x size float tensor in [0, 1] (not yet normalized)."""
    import torch
    from PIL import Image

    with Image.open(path) as im:
        im.draft("L", (size, size))  # JPEG: decode at a reduced scale that stays >= the target size
        im = im.convert("L")
        side = max(im.size)
        canvas = Image.new("L", (side, side), 0)
        canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    canvas = canvas.resize((size, size), Image.Resampling.BICUBIC)
    t = torch.frombuffer(bytearray(canvas.tobytes()), dtype=torch.uint8).reshape(size, size).float() / 255.0
    return t.unsqueeze(0).expand(3, size, size).clone()


def _load_model(encoder_id: str, root: Path):
    import safetensors.torch

    arch = ENCODERS[encoder_id]["arch"]
    if arch == "dinov2":
        from transformers import Dinov2Model

        return Dinov2Model.from_pretrained(root, local_files_only=True, use_safetensors=True)
    if arch == "resnet50":
        import timm

        model = timm.create_model("resnet50", pretrained=False, num_classes=0)
        state = {k: v for k, v in safetensors.torch.load_file(root / "model.safetensors").items() if not k.startswith("fc.")}
        model.load_state_dict(state, strict=True)
        return model
    raise ValueError(f"unknown arch {arch!r}")


def default_device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


class FrozenEncoderAdapter:
    """Embeds radiographs with a frozen encoder. `run` returns one embedding; `embed` does batches."""

    synthetic = False

    def __init__(self, encoder_id: str, device: str | None = None, models_dir: Path = MODELS_DIR):
        if encoder_id not in ENCODERS:
            raise KeyError(f"no encoder spec for {encoder_id!r}; known: {sorted(ENCODERS)}")
        self.encoder_id = encoder_id
        self.id = f"frozen-encoder:{encoder_id}"
        self.spec = ENCODERS[encoder_id]
        self.root = Path(models_dir) / encoder_id
        self.device = device
        self._model = None

    def _ensure(self):
        if self._model is None:
            import torch

            if not (self.root / "model.safetensors").exists():
                raise FileNotFoundError(f"{self.root}/model.safetensors missing; fetch {self.encoder_id} first")
            self.device = self.device or default_device()
            self._model = _load_model(self.encoder_id, self.root).eval().to(self.device)
            self._mean = torch.tensor(self.spec["mean"]).view(1, 3, 1, 1).to(self.device)
            self._std = torch.tensor(self.spec["std"]).view(1, 3, 1, 1).to(self.device)
        return self._model

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        p = inputs.get("image_path")
        if not isinstance(p, str) or not p:
            return ["inputs.image_path must be a path string"]
        if not Path(p).is_file():
            return [f"image not found: {p}"]
        return []

    def _forward(self, batch):
        import torch

        model = self._ensure()
        with torch.inference_mode():
            x = (batch.to(self.device) - self._mean) / self._std
            out = model(pixel_values=x).pooler_output if self.spec["arch"] == "dinov2" else model(x)
            return out.float().cpu()

    def embed(self, paths: list[Path], batch_size: int = 16, progress=None):
        """Return an N x dim float32 numpy array, in the order of `paths`."""
        import numpy as np
        import torch

        size, chunks = self.spec["size"], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, len(paths), batch_size):
                imgs = list(pool.map(lambda p: load_image(p, size), paths[start:start + batch_size]))
                chunks.append(self._forward(torch.stack(imgs)).numpy())
                if progress:
                    progress(min(start + batch_size, len(paths)), len(paths))
        return np.concatenate(chunks).astype(np.float32) if chunks else np.zeros((0, self.spec["dim"]), np.float32)

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        emb = self.embed([Path(inputs["image_path"])], batch_size=1)[0]
        return {"type": "embedding", "dim": int(emb.shape[0]), "embedding": emb.tolist(), "encoder": self.encoder_id,
                "revision": revision(self.encoder_id), "preprocessing": preprocessing(self.encoder_id),
                "note": "Frozen-encoder features, not a diagnosis."}
