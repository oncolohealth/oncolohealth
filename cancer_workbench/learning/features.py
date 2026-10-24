"""Frozen-encoder feature extraction. Owner: Workstream E. Needs the `ml` extra (see package docstring)."""
from __future__ import annotations

import sys
import time
import hashlib
import json
import os
import tempfile
from pathlib import Path


def extract_features(encoder_id: str, manifest_rows: list[dict], data_root: Path, out_path: Path,
                     *, batch_size: int = 16, device: str | None = None, quiet: bool = False, variant: str = "pad",
                     models_dir: Path | None = None, expected_binding: dict | None = None) -> Path:
    """Embed every manifest row's `file` (relative to `data_root`) and write an .npz.

    The binding measures source-image, weight/config and processor identities.
    A second measurement after embedding refuses changed inputs before writing.
    """
    import numpy as np

    from ..adapters.encoder import FrozenEncoderAdapter
    from .provenance import feature_binding

    bound = feature_binding(encoder_id, manifest_rows, data_root, variant, models_dir)
    if expected_binding is not None and bound != expected_binding:
        raise ValueError("Feature inputs changed before extraction. Re-audit and restart the run.")
    adapter = FrozenEncoderAdapter(encoder_id, device=device, variant=variant, models_dir=models_dir)
    t0 = time.monotonic()

    def progress(done, total):
        if not quiet:
            rate = done / max(time.monotonic() - t0, 1e-9)
            print(f"\r  {encoder_id}: {done}/{total} images ({rate:.1f}/s)", end="", file=sys.stderr)

    feats = adapter.embed([Path(data_root) / r["file"] for r in manifest_rows], batch_size=batch_size, progress=progress)
    ids = [r["sample_id"] for r in manifest_rows]
    payload_sha = _payload_digest(feats, ids, bound["model"]["feature_dim"])
    if feature_binding(encoder_id, manifest_rows, data_root, variant, models_dir) != bound:
        raise ValueError("Feature inputs changed during extraction. No cache was published.")
    if not quiet:
        print(file=sys.stderr)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    col = lambda k: np.array([r.get(k, "") for r in manifest_rows])
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=out_path.parent, prefix=".feature-", suffix=".npz", delete=False) as stream:
            temp = Path(stream.name)
            np.savez(stream, sample_ids=col("sample_id"), patient_ids=col("patient_id"), partitions=col("partition"),
                     labels=col("label"), features=feats, encoder_id=encoder_id, revision=str(bound["model"]["revision"]),
                     preprocessing_hash=bound["model"]["preprocessing_hash"], variant=variant, device=str(adapter.device),
                     model_fingerprint=bound["model"]["sha256"], feature_binding_sha256=bound["sha256"],
                     source_binding=json.dumps(bound, sort_keys=True), feature_payload_sha256=payload_sha,
                     seconds=round(time.monotonic() - t0, 1))
        os.replace(temp, out_path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return out_path


def cache_path(encoder_id: str, dataset_id: str, root: Path, variant: str = "pad", *, binding: dict | None = None) -> Path:
    """Bound caches add the measured-input digest. Bare calls name legacy files."""
    from ..adapters.encoder import preprocessing_hash, revision

    suffix = "-" + binding["sha256"] if binding is not None else ""
    rev = binding["model"]["revision"] if binding is not None else revision(encoder_id)
    prep = binding["model"]["preprocessing_hash"] if binding is not None else preprocessing_hash(encoder_id, variant)
    return Path(root) / f"{dataset_id}-{encoder_id}-{str(rev)[:8]}-{prep}{suffix}.npz"


def _payload_digest(matrix, sample_ids: list[str], dim: int) -> str:
    import numpy as np

    values = np.asarray(matrix)
    if values.ndim != 2 or values.shape != (len(sample_ids), dim) or values.dtype.kind != "f" or not np.isfinite(values).all():
        raise ValueError("Feature payload must be a finite floating-point matrix aligned to samples and encoder dimension.")
    sha = hashlib.sha256()
    sha.update(json.dumps({"ids": sample_ids, "shape": list(values.shape), "dtype": values.dtype.str}, sort_keys=True).encode())
    sha.update(values.tobytes(order="C"))
    return sha.hexdigest()


def validate_feature_binding(features: dict, expected: dict) -> None:
    """Validate actual input identity and stored matrix alignment before fitting."""
    from .provenance import digest

    try:
        stored = json.loads(features["source_binding"])
        ids = features["sample_ids"].tolist()
        model = expected["model"]
        identity = {"encoder_id": model["encoder_id"], "revision": str(model["revision"]),
                    "preprocessing_hash": model["preprocessing_hash"], "model_fingerprint": model["sha256"],
                    "feature_binding_sha256": expected["sha256"], "variant": model["variant"]}
        if (stored != expected or stored["sha256"] != digest({k: v for k, v in stored.items() if k != "sha256"})
                or any(features.get(k) != v for k, v in identity.items())
                or len(ids) != len(set(ids)) or set(ids) != {s["sample_id"] for s in expected["sources"]["samples"]}
                or features.get("feature_payload_sha256") != _payload_digest(features["features"], ids, model["feature_dim"])):
            raise ValueError("Feature cache does not match the measured inputs or its stored feature payload.")
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("Legacy or malformed feature cache has no valid measured-input binding. Regenerate features; stored result replay remains available.") from exc


def ensure_features(encoder_id: str, rows: list[dict], data_root: Path, root: Path, variant: str = "pad") -> tuple[dict, Path]:
    """Get a verified bound cache, extracting a new version only when absent."""
    from .provenance import feature_binding

    expected = feature_binding(encoder_id, rows, data_root, variant)
    path = cache_path(encoder_id, "btxrd", root, variant, binding=expected)
    if not path.exists():
        extract_features(encoder_id, rows, data_root, path, variant=variant, expected_binding=expected)
    features = load_features(path)
    validate_feature_binding(features, expected)
    return features, path


def existing_features(encoder_id: str, rows: list[dict], data_root: Path, root: Path, variant: str = "pad") -> tuple[dict, Path]:
    """Read a verified cache only; review commands never trigger extraction."""
    from .provenance import feature_binding

    expected = feature_binding(encoder_id, rows, data_root, variant)
    path = cache_path(encoder_id, "btxrd", root, variant, binding=expected)
    if not path.is_file():
        raise FileNotFoundError(f"No cache matches the measured inputs: {path.name}. Legacy caches are not accepted. Generate a new reviewed exploratory run explicitly.")
    features = load_features(path)
    validate_feature_binding(features, expected)
    return features, path


def bound_source_rows(rows: list[dict], features: dict) -> list[dict]:
    """Keep measured hashes in the derived split and require later arms to match."""
    samples = json.loads(features["source_binding"])["sources"]["samples"]
    by_id = {s["sample_id"]: s["sha256"] for s in samples}
    return [dict(row, sha256=by_id[row["sample_id"]]) for row in rows]


def load_features(path: Path) -> dict:
    import numpy as np

    with np.load(path, allow_pickle=False) as z:
        return {k: (z[k].item() if z[k].ndim == 0 else z[k]) for k in z.files}
