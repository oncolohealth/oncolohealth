"""Validation shared by the standard-library binary evaluation utilities."""
from __future__ import annotations

import math


def binary_rows(rows: list[dict], *, patients: bool = True) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected a nonempty list of binary prediction rows")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("prediction row must be a record")
        for key in ("sample_id", "patient_id") if patients else ("sample_id",):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{key} must be a nonempty, trimmed string; never infer patient ids")
        if row["sample_id"] in seen:
            raise ValueError("duplicate sample_id")
        seen.add(row["sample_id"])
        if isinstance(row.get("label"), bool) or row.get("label") not in (0, 1):
            raise ValueError("label must be binary 0/1 with a declared positive class")
        if row.get("partition") is not None and row["partition"] not in ("train", "val", "test"):
            raise ValueError("partition must be train, val or test when supplied")
        score = row.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1 or not math.isfinite(score):
            raise ValueError("score must be finite and between 0 and 1")
