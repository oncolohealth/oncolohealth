"""Local storage budget for datasets + model weights (default 200 GB, CW_STORAGE_BUDGET_GB overrides)."""
from __future__ import annotations

import os
from pathlib import Path

from ..common.paths import DATA_DIR, MODELS_DIR

DEFAULT_BUDGET_GB = 200.0


def budget_bytes() -> int:
    return int(float(os.environ.get("CW_STORAGE_BUDGET_GB", DEFAULT_BUDGET_GB)) * 1e9)


def usage_bytes(*roots: Path) -> int:
    roots = roots or (DATA_DIR, MODELS_DIR)
    total = 0
    for root in roots:
        if root.exists():
            total += sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return total


def check(planned_bytes: int) -> tuple[bool, int, int]:
    """Return (fits, currently_used, budget)."""
    used, budget = usage_bytes(), budget_bytes()
    return used + planned_bytes <= budget, used, budget
