"""Frozen image encoders behind the Adapter contract. Owner: Workstream C. Needs the `ml` extra.

One preprocessing policy for every encoder, so the arms stay matched:
grayscale -> pad to square with black (keeps the whole radiograph; no center
crop that could cut a lesion off) -> bicubic resize to the encoder's input
size -> 3 identical channels -> scale to [0, 1] -> the encoder's published
mean/std. Weights load only from local .safetensors files: no pickles, no network.

`VARIANTS` names two alternatives for the source-shift check: a per-image
contrast stretch before padding, and each encoder's native shortest-edge
resize and center crop, which matches the publishers' own processors. `pad`
stays the default for every caller.

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

# Identity of the implementation actually loaded into this process. Editing the
# source file does not change already loaded Python code; restart after updates.
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

IMAGENET = {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}
ENCODERS: dict[str, dict[str, Any]] = {
    "rad-dino": {"arch": "dinov2", "size": 518, "mean": [0.5307] * 3, "std": [0.2583] * 3, "dim": 768,
                 "output": "CLS token after the final layer norm (pooler_output)",
                 "source": "preprocessor_config.json mean/std; 518 px as in the model's training",
                 "processor_config": "preprocessor_config.json", "crop_offset": "floor"},
    "resnet50-a1-in1k": {"arch": "resnet50", "size": 288, **IMAGENET, "dim": 2048,
                         "output": "global average pool before the classifier",
                         "source": "timm pretrained_cfg mean/std; 288 px test_input_size",
                         "processor_config": "config.json", "crop_offset": "round"},
}
PAD_POLICY = "JPEG draft decode >= target, grayscale, pad to square (black), bicubic resize, replicate to 3 channels"
VARIANTS = {
    "pad": PAD_POLICY,
    "pad_pstretch": "JPEG draft decode >= target, grayscale, per-image 1st-99th percentile contrast stretch, "
                    "pad to square (black), bicubic resize, replicate to 3 channels",
    # RAD-DINO's processor and timm's test config (crop_pct 1.0 at 288) both resize the shortest edge, then center crop.
    # Both decode JPEGs at full resolution and truncate the long edge; the crop offset is floored by
    # transformers and rounded by torchvision.
    "native_crop": "full-resolution decode, grayscale, bicubic resize of the shortest edge to the input size "
                   "(long edge truncated), center crop to square with the publisher's offset rounding, replicate to 3 channels",
}


def _variant(variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"unknown preprocessing variant {variant!r}; known: {sorted(VARIANTS)}")
    return variant


def preprocessing(encoder_id: str, variant: str = "pad") -> dict[str, Any]:
    spec = ENCODERS[encoder_id]
    out = {"policy": VARIANTS[_variant(variant)], "size": spec["size"], "mean": spec["mean"], "std": spec["std"]}
    return {**out, "crop_offset": spec["crop_offset"]} if variant == "native_crop" else out


def preprocessing_hash(encoder_id: str, variant: str = "pad") -> str:
    return hashlib.sha256(json.dumps(preprocessing(encoder_id, variant), sort_keys=True).encode()).hexdigest()[:12]


def publisher_preprocessing(encoder_id: str, raw: bytes) -> dict[str, Any]:
    """Size, mean/std, interpolation and native crop read from the publisher's processor file bytes.

    Raises ValueError when they disagree with `ENCODERS`, so a replaced or edited
    processor file cannot silently pair with these hard-coded constants.
    """
    spec = ENCODERS[encoder_id]
    try:
        cfg = json.loads(raw)
        if spec["arch"] == "dinov2":  # transformers BitImageProcessor; resample 3 is PIL bicubic
            sizes = {cfg["size"]["shortest_edge"], cfg["crop_size"]["height"], cfg["crop_size"]["width"]}
            ok = (cfg["do_resize"] and cfg["do_center_crop"] and cfg["do_rescale"] and cfg["do_normalize"]
                  and abs(cfg["rescale_factor"] - 1 / 255) < 1e-12)
            found = {"size": sizes.pop() if len(sizes) == 1 else None, "mean": cfg["image_mean"], "std": cfg["image_std"],
                     "interpolation": "bicubic" if cfg["resample"] == 3 else cfg["resample"], "crop": "shortest edge, center crop"}
        else:  # timm pretrained_cfg; test_crop_pct 1.0 means the crop equals the resized shortest edge
            pre = cfg["pretrained_cfg"]
            size = pre["test_input_size"]
            ok = cfg["architecture"] == spec["arch"] and pre["test_crop_pct"] == 1.0 and pre["crop_mode"] == "center"
            found = {"size": size[1] if size[1] == size[2] else None, "mean": pre["mean"], "std": pre["std"],
                     "interpolation": pre["interpolation"], "crop": "shortest edge, center crop"}
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed publisher processor configuration for {encoder_id}.") from exc
    expected = {"size": spec["size"], "mean": spec["mean"], "std": spec["std"], "interpolation": "bicubic"}
    if not ok or any(found[k] != v for k, v in expected.items()):
        raise ValueError(f"Publisher processor configuration for {encoder_id} disagrees with the encoder constants.")
    return found


def revision(encoder_id: str, models_dir: Path | None = None) -> str | None:
    """Read the declared revision from the actual model folder, never a fallback.

    This metadata is not authentication of the weight bytes. Feature provenance
    separately measures the files used by the encoder.
    """
    prov = Path(MODELS_DIR if models_dir is None else models_dir) / encoder_id / "PROVENANCE.json"
    if not prov.exists():
        return None
    value = json.loads(prov.read_text())
    source = value.get("source") if isinstance(value, dict) else None
    if not isinstance(source, dict):
        raise ValueError(f"Malformed source provenance in {prov}")
    result = source.get("revision")
    if result is not None and (not isinstance(result, str) or not result.strip()):
        raise ValueError(f"Malformed revision in {prov}")
    return result


def load_image(path: Path, size: int, variant: str = "pad", crop_offset: str = "floor"):
    """Return a 3 x size x size float tensor in [0, 1] (not yet normalized), preprocessed as `VARIANTS[variant]`.

    `crop_offset` ("floor" or "round") only affects `native_crop`; take it from `ENCODERS[...]["crop_offset"]`.
    """
    import torch
    from PIL import Image, ImageOps

    _variant(variant)
    with Image.open(path) as im:
        if variant != "native_crop":  # native_crop decodes at full resolution, as the publishers do
            im.draft("L", (size, size))  # JPEG: decode at a reduced scale that stays >= the target size
        im = im.convert("L")
    if variant == "pad_pstretch":
        im = ImageOps.autocontrast(im, cutoff=1)  # before padding, so the black border doesn't count
    if variant == "native_crop":
        if crop_offset not in ("floor", "round"):
            raise ValueError(f"unknown crop offset {crop_offset!r}")
        short = min(im.size)
        long = int(size * max(im.size) / short)  # same float expression as transformers and torchvision
        w, h = (size, long) if im.width == short else (long, size)
        im = im.resize((w, h), Image.Resampling.BICUBIC)
        offset = (lambda n: n // 2) if crop_offset == "floor" else (lambda n: int(round(n / 2.0)))
        left, top = offset(w - size), offset(h - size)
        canvas = im.crop((left, top, left + size, top + size))
    else:
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

    def __init__(self, encoder_id: str, device: str | None = None, models_dir: Path | None = None, variant: str = "pad"):
        if encoder_id not in ENCODERS:
            raise KeyError(f"no encoder spec for {encoder_id!r}; known: {sorted(ENCODERS)}")
        self.encoder_id = encoder_id
        self.variant = _variant(variant)
        self.id = f"frozen-encoder:{encoder_id}"
        self.spec = ENCODERS[encoder_id]
        self.root = Path(MODELS_DIR if models_dir is None else models_dir) / encoder_id
        self.device = device
        self._model = None
        self._loaded_identity = None

    def _ensure(self):
        if self._model is None:
            import torch
            from ..learning.provenance import model_identity

            if not (self.root / "model.safetensors").exists():
                raise FileNotFoundError(f"{self.root}/model.safetensors missing; fetch {self.encoder_id} first")
            identity = model_identity(self.encoder_id, self.variant, self.root.parent)
            self.device = self.device or default_device()
            model = _load_model(self.encoder_id, self.root).eval().to(self.device)
            if model_identity(self.encoder_id, self.variant, self.root.parent) != identity:
                raise ValueError("Model files changed while loading. Create a new encoder after reviewing the files.")
            self._model, self._loaded_identity = model, identity
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
                imgs = list(pool.map(lambda p: load_image(p, size, self.variant, self.spec["crop_offset"]), paths[start:start + batch_size]))
                chunks.append(self._forward(torch.stack(imgs)).numpy())
                if progress:
                    progress(min(start + batch_size, len(paths)), len(paths))
        return np.concatenate(chunks).astype(np.float32) if chunks else np.zeros((0, self.spec["dim"]), np.float32)

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from ..learning.provenance import model_identity

        identity = model_identity(self.encoder_id, self.variant, self.root.parent)
        if self._model is not None and self._loaded_identity != identity:
            raise ValueError("Loaded encoder identity differs from its configured files. Create a new encoder.")
        emb = self.embed([Path(inputs["image_path"])], batch_size=1)[0]
        if (model_identity(self.encoder_id, self.variant, self.root.parent) != identity
                or self._loaded_identity is not None and self._loaded_identity != identity):
            raise ValueError("Model identity changed during embedding. No result was published.")
        return {"type": "embedding", "dim": int(emb.shape[0]), "embedding": emb.tolist(), "encoder": self.encoder_id,
                "revision": identity["revision"], "model_fingerprint": identity["sha256"],
                "preprocessing": preprocessing(self.encoder_id, self.variant),
                "note": "Frozen-encoder features, not a diagnosis."}
