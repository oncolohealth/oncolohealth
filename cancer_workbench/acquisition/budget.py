"""Local storage accounting for datasets + model weights. Unlimited unless CW_STORAGE_BUDGET_GB sets a cap."""
from __future__ import annotations

import os
from pathlib import Path

from ..common.paths import DATA_DIR, MODELS_DIR


def budget_bytes() -> int | None:
    """The optional cap in bytes, or None when storage is unlimited (the default)."""
    raw = os.environ.get("CW_STORAGE_BUDGET_GB", "").strip()
    return int(float(raw) * 1e9) if raw else None


def usage_bytes(*roots: Path) -> int:
    roots = roots or (DATA_DIR, MODELS_DIR)
    total = 0
    for root in roots:
        if root.exists():
            total += sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return total


def describe(cap: int | None) -> str:
    return "no limit" if cap is None else f"{cap / 1e9:.0f} GB"


def check(planned_bytes: int) -> tuple[bool, int, int | None]:
    """Return (fits, currently_used, budget); budget is None and fits is True when unlimited."""
    used, budget = usage_bytes(), budget_bytes()
    return budget is None or used + planned_bytes <= budget, used, budget
