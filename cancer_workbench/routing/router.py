"""Compatibility routing: list compatible and rejected models for a request, never pick one silently.

Implemented checks: task, modality, anatomy, input channels, spatial dims,
plus a separate `runnable` verdict (evidence state, inference permission, adapter).
Specified but NOT implemented: geometry/spacing, acquisition protocol,
normalization, population eligibility, output-semantics matching.
"""
from __future__ import annotations

from ..common.types import EvidenceState, Permission

REQUIRED_REQUEST_FIELDS = ("task", "modality", "anatomy")


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def compatibility_reasons(model: dict, request: dict) -> list[str]:
    """Return why `model` cannot serve `request` (empty list means compatible)."""
    reasons = []
    if request["task"] not in model.get("tasks", []):
        reasons.append(f"task {request['task']!r} not in {model.get('tasks')}")
    if request["modality"] not in _as_list(model.get("modality", [])):
        reasons.append(f"modality {request['modality']!r} not in {model.get('modality')}")
    anatomy = _as_list(model.get("anatomy", []))
    if "any" not in anatomy and request["anatomy"] not in anatomy:
        reasons.append(f"anatomy {request['anatomy']!r} not in {anatomy}")
    want_in, have_in = request.get("input", {}), model.get("input", {})
    for key in ("channels", "spatial_dims"):
        if key in want_in and key in have_in and want_in[key] != have_in[key]:
            reasons.append(f"input {key} {want_in[key]!r} != required {have_in[key]!r}")
    return reasons


def runnable_blockers(model: dict, installed: set[str] | None = None) -> list[str]:
    """Why `model` cannot run. `installed` is the set of adapter ids this process can
    run; when given, a named but uninstalled adapter is a blocker too."""
    blockers = []
    if model.get("evidence_state") != EvidenceState.LOCALLY_REPRODUCED.value:
        blockers.append(f"evidence_state is {model.get('evidence_state')!r}, needs 'locally_reproduced'")
    if model.get("inference_permission") != Permission.ALLOWED.value:
        blockers.append(f"inference_permission is {model.get('inference_permission')!r}, needs reviewed 'allowed'")
    if not model.get("adapter"):
        blockers.append("no adapter installed")
    elif installed is not None and model["adapter"] not in installed:
        blockers.append(f"adapter {model['adapter']!r} is not installed in this process")
    return blockers


def route_models(request: dict, models: list[dict], installed: set[str] | None = None) -> dict:
    """Return {"compatible": [...], "rejected": [...]} or {"error": ...} for an incomplete request.

    Each compatible entry carries `runnable` and `blockers`; the caller decides what to do.
    `installed` is the set of adapter ids this process can run; when given, a
    named but uninstalled adapter is a blocker too.
    """
    missing = [f for f in REQUIRED_REQUEST_FIELDS if not request.get(f)]
    if missing:
        return {"error": f"request missing required fields: {missing}", "compatible": [], "rejected": []}
    compatible, rejected = [], []
    for m in models:
        reasons = compatibility_reasons(m, request)
        if reasons:
            rejected.append({"id": m["id"], "reasons": reasons})
        else:
            blockers = runnable_blockers(m, installed)
            compatible.append({"id": m["id"], "runnable": not blockers, "blockers": blockers})
    return {"compatible": compatible, "rejected": rejected}
