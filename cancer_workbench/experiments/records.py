"""Experiment record schema and job states."""
from __future__ import annotations

import dataclasses
import enum
from typing import Any

REUSE_PATHS = ("specialist_tools", "transfer_learning", "distillation")


class JobState(str, enum.Enum):
    PLANNED = "planned"
    BLOCKED = "blocked"
    READY_FOR_REVIEW = "ready_for_review"
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    RUNNING = "running"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclasses.dataclass
class ExperimentRecord:
    id: str
    path: str  # one of REUSE_PATHS
    task: str  # precise endpoint, e.g. "btxrd_tumor_vs_normal_image"
    cohort: str  # dataset id + release + manifest sha256
    split: str  # split file + seed + grouping key
    model: str  # catalog id + revision
    source_revision: str  # git commit of this repo
    environment: dict[str, str]  # python + package versions, device
    preprocessing: dict[str, Any]
    objective: str
    metrics: list[str]
    seed_policy: str
    execution_scope: str  # what was authorized to run, where
    state: JobState = JobState.PLANNED
    resource_profile: dict[str, Any] = dataclasses.field(default_factory=dict)  # measured, never estimated
    outputs: list[str] = dataclasses.field(default_factory=list)
    blockers: list[str] = dataclasses.field(default_factory=list)
