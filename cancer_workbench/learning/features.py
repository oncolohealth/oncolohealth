"""Frozen-encoder feature extraction. Owner: Workstream E. Needs the `ml` extra (see package docstring)."""
from __future__ import annotations

import sys
import time
from pathlib import Path


def extract_features(encoder_id: str, manifest_rows: list[dict], data_root: Path, out_path: Path,
                     *, batch_size: int = 16, device: str | None = None, quiet: bool = False, variant: str = "pad") -> Path:
    """Embed every manifest row's `file` (relative to `data_root`) and write an .npz.

    The file holds sample_ids, patient_ids, partitions, labels, features (N x D), plus
    encoder id, revision, preprocessing variant and hash so a stale cache is never reused silently.
    """
    import numpy as np

    from ..adapters.encoder import FrozenEncoderAdapter, preprocessing_hash, revision

    missing = [r["sample_id"] for r in manifest_rows if not r.get("file")]
    if missing:
        raise ValueError(f"{len(missing)} rows have no file, e.g. {missing[:3]}")
    adapter = FrozenEncoderAdapter(encoder_id, device=device, variant=variant)
    t0 = time.monotonic()

    def progress(done, total):
        if not quiet:
            rate = done / max(time.monotonic() - t0, 1e-9)
            print(f"\r  {encoder_id}: {done}/{total} images ({rate:.1f}/s)", end="", file=sys.stderr)

    feats = adapter.embed([Path(data_root) / r["file"] for r in manifest_rows], batch_size=batch_size, progress=progress)
    if not quiet:
        print(file=sys.stderr)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    col = lambda k: np.array([r.get(k, "") for r in manifest_rows])
    np.savez(out_path, sample_ids=col("sample_id"), patient_ids=col("patient_id"), partitions=col("partition"),
             labels=col("label"), features=feats, encoder_id=encoder_id, revision=str(revision(encoder_id)),
             preprocessing_hash=preprocessing_hash(encoder_id, variant), variant=variant, device=str(adapter.device),
             seconds=round(time.monotonic() - t0, 1))
    return out_path


def cache_path(encoder_id: str, dataset_id: str, root: Path, variant: str = "pad") -> Path:
    """Feature file name pinned to encoder revision and preprocessing, so changes never reuse stale features."""
    from ..adapters.encoder import preprocessing_hash, revision

    return Path(root) / f"{dataset_id}-{encoder_id}-{str(revision(encoder_id))[:8]}-{preprocessing_hash(encoder_id, variant)}.npz"


def load_features(path: Path) -> dict:
    import numpy as np

    with np.load(path, allow_pickle=False) as z:
        return {k: (z[k].item() if z[k].ndim == 0 else z[k]) for k in z.files}
