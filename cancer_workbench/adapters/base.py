"""Specialist adapter contract and the single execution entry point.

An adapter wraps one specialist: it validates inputs, runs the model and
returns native outputs. `execute_specialist` enforces eligibility and wraps
everything in a ResultEnvelope; failures are reported, never papered over.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..common.types import ResultEnvelope, ResultStatus
from ..routing.router import compatibility_reasons, runnable_blockers


@runtime_checkable
class Adapter(Protocol):
    id: str
    synthetic: bool  # True for fake adapters used in tests/demos

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        """Return input problems (missing files, wrong channels/geometry...). Empty means valid."""

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the specialist and return its native outputs. May raise."""


def execute_specialist(model: dict, request: dict, adapters: dict[str, Adapter]) -> ResultEnvelope:
    """Run `model` on `request` through its installed adapter.

    `request` holds routing fields (task/modality/anatomy/input) plus
    `inputs` (adapter-specific payload) and optional `input_refs`.
    """
    env = dict(
        model_id=model["id"],
        task=request.get("task", ""),
        adapter_id=model.get("adapter"),
        input_refs=list(request.get("input_refs", [])),
    )
    problems = compatibility_reasons(model, request) if all(request.get(k) for k in ("task", "modality", "anatomy")) else [
        "request missing task/modality/anatomy"
    ]
    problems += runnable_blockers(model)
    adapter = adapters.get(model.get("adapter") or "")
    if model.get("adapter") and adapter is None:
        problems.append(f"adapter {model['adapter']!r} is not installed in this process")
    if problems:
        return ResultEnvelope(status=ResultStatus.REJECTED, errors=problems, **env)

    env["synthetic"] = bool(getattr(adapter, "synthetic", False))
    input_errors = adapter.validate(request.get("inputs", {}))
    if input_errors:
        return ResultEnvelope(status=ResultStatus.REJECTED, errors=input_errors, **env)
    try:
        outputs = adapter.run(request.get("inputs", {}))
    except Exception as e:  # report the real failure to the caller/coordinator
        return ResultEnvelope(status=ResultStatus.FAILED, errors=[f"{type(e).__name__}: {e}"], **env)
    return ResultEnvelope(status=ResultStatus.OK, outputs=outputs, **env)
