"""Metrics. Owner: Workstream F. STUB (see package docstring for the contract)."""
from __future__ import annotations


def binary_report(y_true: list[int], scores: list[float], threshold: float, group_ids: list[str] | None = None) -> dict:
    raise NotImplementedError("Workstream F")


def calibration(y_true: list[int], probs: list[float], n_bins: int = 10) -> dict:
    raise NotImplementedError("Workstream F")
