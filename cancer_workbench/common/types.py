"""Shared types used by every workstream.

Changing anything here affects all modules: open a PR and get review from at
least one other workstream before merging.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import uuid
from typing import Any


class EvidenceState(str, enum.Enum):
    """How far a model or dataset has actually progressed. Ordered weakest to strongest."""

    CATALOGED = "cataloged"  # a record exists; nothing obtained
    ACCESS_OBTAINED = "access_obtained"  # files are present locally with verified identity
    RUNNABLE = "runnable"  # an adapter executes it on a reference example
    LOCALLY_REPRODUCED = "locally_reproduced"  # a documented result was reproduced here
    EXTERNALLY_EVALUATED = "externally_evaluated"  # evaluated on an independent cohort

    @property
    def rank(self) -> int:
        return list(EvidenceState).index(self)


class Permission(str, enum.Enum):
    ALLOWED = "allowed"
    NOT_ALLOWED = "not_allowed"
    UNREVIEWED = "unreviewed"


class ResultStatus(str, enum.Enum):
    OK = "ok"
    REJECTED = "rejected"  # inputs or eligibility failed before execution
    FAILED = "failed"  # execution started and raised


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclasses.dataclass
class ResultEnvelope:
    """Common wrapper for every specialist call.

    `outputs` holds the model's native output (labels, scores, box/mask
    references, units) unchanged. Never collapse different models into one
    universal cancer probability here.
    """

    model_id: str
    task: str
    status: ResultStatus
    adapter_id: str | None = None
    input_refs: list[str] = dataclasses.field(default_factory=list)
    outputs: dict[str, Any] | None = None
    errors: list[str] = dataclasses.field(default_factory=list)
    synthetic: bool = False  # True when produced by a fake adapter or synthetic input
    evaluation_refs: list[str] = dataclasses.field(default_factory=list)
    run_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = dataclasses.field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d
