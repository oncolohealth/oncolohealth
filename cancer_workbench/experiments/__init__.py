"""Experiment plans and records. Owner: Workstream B (protocol) with E/F. Partially implemented.

plan.plan_experiment(path, model, dataset_audit=None, budget=None) -> dict
    path in REUSE_PATHS. Returns a draft with state "blocked" (and reasons) or
    "ready_for_review". Never submits or runs anything.
records.ExperimentRecord: the reproducibility record every run must write.
"""
from .records import REUSE_PATHS, ExperimentRecord, JobState

__all__ = ["REUSE_PATHS", "ExperimentRecord", "JobState"]
