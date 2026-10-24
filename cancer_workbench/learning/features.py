"""Frozen-encoder feature extraction. Owner: Workstream E. STUB (see package docstring)."""
from __future__ import annotations

from pathlib import Path


def extract_features(encoder_id: str, manifest_rows: list[dict], data_root: Path, out_path: Path) -> Path:
    raise NotImplementedError("Workstream E: needs the `ml` extra (torch/timm/transformers)")
