"""Specialist adapters. Owner: Workstream C. Real adapters go in their own module (e.g. monai_lung.py)."""
from .base import Adapter, execute_specialist
from .synthetic import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter

__all__ = ["Adapter", "SYNTHETIC_MODEL_RECORD", "SyntheticThresholdAdapter", "execute_specialist"]
