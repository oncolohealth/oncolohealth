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


# Spelling variants people (and language models) use for the catalog's own terms. Only exact
# equivalents belong here: never map a narrower term to a broader one or vice versa.
_MODALITY_SYNONYMS = {
    "radiograph": "xray", "radiography": "xray", "plainfilm": "xray", "cxr": "xray",
    "computedtomography": "ct",
    "mr": "mri", "magneticresonance": "mri", "magneticresonanceimaging": "mri",
    "histopathology": "pathology", "histology": "pathology", "wsi": "pathology", "wholeslideimage": "pathology",
    "sonography": "ultrasound", "ultrasonography": "ultrasound",
    "dermatoscopy": "dermoscopy", "mammogram": "mammography",
}
_ANATOMY_SYNONYMS = {"bones": "bone", "skeleton": "bone", "skeletal": "bone"}


def _term(value, synonyms: dict | None = None) -> str:
    """Compare terms by letters and digits only, case-insensitively: "X-ray" == "xray" == "x ray"."""
    key = "".join(ch for ch in str(value).lower() if ch.isalnum())
    return (synonyms or {}).get(key, key)


def _matches(wanted, offered, synonyms: dict | None = None) -> bool:
    return _term(wanted, synonyms) in {_term(o, synonyms) for o in _as_list(offered)}


def compatibility_reasons(model: dict, request: dict) -> list[str]:
    """Return why `model` cannot serve `request` (empty list means compatible).

    Terms match after normalizing case, spacing, punctuation and listed synonyms, so a request
    for "X-ray" reaches models declared for "xray". Reasons quote the original wording."""
    reasons = []
    if not _matches(request["task"], model.get("tasks", [])):
        reasons.append(f"task {request['task']!r} not in {model.get('tasks')}")
    if not _matches(request["modality"], model.get("modality", []), _MODALITY_SYNONYMS):
        reasons.append(f"modality {request['modality']!r} not in {model.get('modality')}")
    anatomy = _as_list(model.get("anatomy", []))
    if "any" not in anatomy and not _matches(request["anatomy"], anatomy, _ANATOMY_SYNONYMS):
        reasons.append(f"anatomy {request['anatomy']!r} not in {anatomy}")
    want_in, have_in = request.get("input", {}), model.get("input", {})
    for key in ("channels", "spatial_dims"):
        if key in want_in and key in have_in and want_in[key] != have_in[key]:
            reasons.append(f"input {key} {want_in[key]!r} != required {have_in[key]!r}")
    return reasons


def runnable_blockers(model: dict) -> list[str]:
    blockers = []
    if model.get("evidence_state") != EvidenceState.LOCALLY_REPRODUCED.value:
        blockers.append(f"evidence_state is {model.get('evidence_state')!r}, needs 'locally_reproduced'")
    if model.get("inference_permission") != Permission.ALLOWED.value:
        blockers.append(f"inference_permission is {model.get('inference_permission')!r}, needs reviewed 'allowed'")
    if not model.get("adapter"):
        blockers.append("no adapter installed")
    return blockers


def route_models(request: dict, models: list[dict]) -> dict:
    """Return {"compatible": [...], "rejected": [...]} or {"error": ...} for an incomplete request.

    Each compatible entry carries `runnable` and `blockers`; the caller decides what to do.
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
            blockers = runnable_blockers(m)
            compatible.append({"id": m["id"], "runnable": not blockers, "blockers": blockers})
    return {"compatible": compatible, "rejected": rejected}
