"""Real specialist adapters this process can install, keyed by catalog `adapter` id. Owner: Workstream C.

`installed_adapters(models)` returns the mapping that `execute_specialist` and
the coordinator's `run_specialist` tool look adapters up in. An adapter is
installed only when the catalog names it, the `ml` extra imports, and the
model's local weights are present; otherwise the call path reports "not
installed in this process" instead of failing later.

The frozen encoders return a feature vector, never a probability or label.
Inputs are image references inside the data folder, not arbitrary paths:
`btxrd:<sample_id>` (the BTXRD manifest) or `uploads:<id>` (the app's uploads).

Standard library at import; torch and Pillow load only when an adapter runs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import threading
import time
from pathlib import Path
from typing import Any

from ..common.paths import DATA_DIR, MODELS_DIR

ENCODER_ADAPTERS = {"frozen-encoder:rad-dino": "rad-dino", "frozen-encoder:resnet50-a1-in1k": "resnet50-a1-in1k"}
_ARCH_MODULE = {"rad-dino": "transformers", "resnet50-a1-in1k": "timm"}
_BASE_MODULES = ("numpy", "torch", "PIL", "safetensors")
IMAGE_SUFFIXES = (".jpeg", ".jpg", ".png")
_REF = re.compile(r"(btxrd|uploads):([A-Za-z0-9_.-]{1,64})")
INPUT_KEYS = {"image", "return_vector"}
SEMANTICS = ("Frozen-encoder feature vector. Not a probability, label, detection or diagnosis: "
             "turning it into a prediction needs a separately fitted and evaluated head.")
PREVIEW = 8

_lock = threading.Lock()
_cache: dict[str, "EncoderSpecialist"] = {}
_manifest_cache: dict[str, Any] = {}


def missing_modules(encoder_id: str) -> list[str]:
    return [m for m in (*_BASE_MODULES, _ARCH_MODULE[encoder_id]) if importlib.util.find_spec(m) is None]


def adapter_status(models: list[dict], models_dir: Path | None = None) -> dict[str, dict]:
    """Why each catalog-named real adapter is or is not installed in this process."""
    root = Path(MODELS_DIR if models_dir is None else models_dir)
    out = {}
    for m in models:
        aid = m.get("adapter") or ""
        enc = ENCODER_ADAPTERS.get(aid)
        if enc is None:
            continue
        reasons = [f"{name} not importable (start the app with .venv/bin/python)" for name in missing_modules(enc)]
        if not (root / enc / "model.safetensors").is_file():
            reasons.append(f"{enc}/model.safetensors missing; fetch {enc} first")
        out[aid] = {"model_id": m["id"], "encoder": enc, "installed": not reasons, "reasons": reasons}
    return out


def installed_adapters(models: list[dict], models_dir: Path | None = None, data_dir: Path | None = None) -> dict[str, "EncoderSpecialist"]:
    """Adapters that can actually run here. Instances are reused so weights load once per process."""
    out = {}
    for aid, status in adapter_status(models, models_dir).items():
        if not status["installed"]:
            continue
        record = next(m for m in models if m.get("adapter") == aid)
        key = f"{aid}|{models_dir}|{data_dir}"
        with _lock:
            if key not in _cache:
                _cache[key] = EncoderSpecialist(status["encoder"], record, models_dir, data_dir)
            out[aid] = _cache[key]
    return out


def resolve_image_ref(ref: str, data_dir: Path | None = None) -> tuple[Path, str]:
    """Return (file, path relative to the data folder) for `btxrd:<id>` or `uploads:<id>`. Raises ValueError."""
    from ..datasets import read_manifest
    from ..datasets.btxrd import MANIFEST_PATH as BTXRD_MANIFEST, RAW_DIR as BTXRD_RAW

    data = Path(DATA_DIR if data_dir is None else data_dir).resolve()
    m = _REF.fullmatch(ref) if isinstance(ref, str) else None
    if m is None:
        raise ValueError("inputs.image must be 'btxrd:<sample_id>' or 'uploads:<id>'")
    kind, ident = m.groups()
    if kind == "uploads":
        found = sorted(p for p in (data / "uploads").glob(f"{ident}.*") if p.suffix.lower() in IMAGE_SUFFIXES)
        if not found:
            raise ValueError(f"no uploaded image {ident!r}")
        path = found[0].resolve()
    else:
        manifest = data / BTXRD_MANIFEST.relative_to(DATA_DIR)
        if not manifest.is_file():
            raise ValueError("no BTXRD manifest here; run `python -m cancer_workbench btxrd manifest`")
        stamp = (manifest.stat().st_mtime_ns, manifest.stat().st_size)
        with _lock:
            if _manifest_cache.get("stamp") != (manifest, stamp):
                _manifest_cache.update(stamp=(manifest, stamp),
                                       files={r["sample_id"]: (r["file"], r.get("sha256", "")) for r in read_manifest(manifest)})
            files = _manifest_cache["files"]
        if ident not in files:
            raise ValueError(f"{ident!r} is not in the BTXRD manifest")
        rel_file, declared = files[ident]
        path = (data / BTXRD_RAW.relative_to(DATA_DIR) / rel_file).resolve()
    if not path.is_relative_to(data) or path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"{ref!r} does not resolve to a JPEG or PNG inside the data folder")
    if not path.is_file():
        raise ValueError(f"image file for {ref!r} is missing: {path.relative_to(data).as_posix()}")
    if kind == "btxrd" and declared and _sha256(path)[0] != declared.lower():
        raise ValueError(f"{ref!r} does not match the SHA-256 its manifest declares; re-audit the release")
    return path, path.relative_to(data).as_posix()


def _sha256(path: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


class EncoderSpecialist:
    """A catalog encoder behind the Adapter contract, with measured input and model provenance in its output."""

    synthetic = False

    def __init__(self, encoder_id: str, record: dict, models_dir: Path | None = None, data_dir: Path | None = None):
        from .encoder import FrozenEncoderAdapter  # torch itself loads lazily on first run

        self.encoder_id, self.record, self.data_dir = encoder_id, record, data_dir
        self.encoder = FrozenEncoderAdapter(encoder_id, models_dir=models_dir)
        self.id = self.encoder.id
        self._run_lock = threading.Lock()

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        problems = [f"unknown input {k!r}; this adapter takes {sorted(INPUT_KEYS)}" for k in sorted(set(inputs) - INPUT_KEYS)]
        if "return_vector" in inputs and not isinstance(inputs["return_vector"], bool):
            problems.append("inputs.return_vector must be true or false")
        try:
            resolve_image_ref(inputs.get("image"), self.data_dir)
        except ValueError as e:
            problems.append(str(e))
        return problems

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        import numpy as np
        from PIL import Image

        from ..learning.provenance import model_identity

        path, rel = resolve_image_ref(inputs["image"], self.data_dir)
        before = _sha256(path)
        with Image.open(path) as im:
            width, height, mode, fmt = im.width, im.height, im.mode, im.format
        t0 = time.monotonic()
        with self._run_lock:
            native = self.encoder.run({"image_path": str(path)})
            identity = model_identity(self.encoder_id, self.encoder.variant, self.encoder.root.parent)
        seconds = time.monotonic() - t0
        if identity["sha256"] != native["model_fingerprint"] or _sha256(path) != before:
            raise ValueError("Model or input bytes changed during the call. No result was published.")
        vec = np.asarray(native["embedding"], dtype=np.float32)
        if vec.shape != (self.encoder.spec["dim"],) or not np.isfinite(vec).all():
            raise ValueError(f"Encoder returned shape {vec.shape} or non-finite values; expected ({self.encoder.spec['dim']},).")
        files = identity["files"]
        processor = identity["processor_config"]
        out = {
            "type": "embedding",
            "semantics": SEMANTICS,
            "dim": int(vec.shape[0]),
            "dtype": "float32",
            "l2_norm": round(float(np.linalg.norm(vec)), 6),
            "embedding_sha256": hashlib.sha256(vec.astype("<f4").tobytes()).hexdigest(),
            "embedding_preview": [round(float(x), 6) for x in vec[:PREVIEW]],
            "input": {"image": inputs["image"], "file": rel, "sha256": before[0], "bytes": before[1],
                      "width": width, "height": height, "mode": mode, "format": fmt},
            "encoder": {
                "model_id": self.record["id"], "encoder_id": self.encoder_id, "revision": identity["revision"],
                "model_fingerprint": identity["sha256"],
                "weights": {"file": "model.safetensors", **files["model.safetensors"]},
                "files": files,
                "processor_config": {"file": processor, "sha256": files[processor]["sha256"],
                                     "parsed": identity["publisher_preprocessing"]},
                "variant": identity["variant"], "preprocessing": identity["preprocessing"],
                "preprocessing_hash": identity["preprocessing_hash"],
                "native_output": self.encoder.spec["output"],
                "implementation_sha256": identity["implementation_sha256"],
                "library_versions": identity["library_versions"], "device": self.encoder.device,
            },
            "terms": (self.record.get("terms_review") or {}).get("inference"),
            "seconds": round(seconds, 3),
        }
        if inputs.get("return_vector"):
            out["embedding"] = [float(x) for x in vec]
        return out
