"""Project directory layout. Override storage locations with CW_DATA_DIR / CW_MODELS_DIR / CW_RUNS_DIR."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = PROJECT_ROOT / "catalog"
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = Path(os.environ.get("CW_DATA_DIR", PROJECT_ROOT / "data"))
MODELS_DIR = Path(os.environ.get("CW_MODELS_DIR", PROJECT_ROOT / "models"))

RUNS_DIR = Path(os.environ.get("CW_RUNS_DIR", PROJECT_ROOT / "runs"))
