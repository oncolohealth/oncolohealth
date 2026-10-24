"""Validation for catalog records. Returns human-readable problems instead of raising.

Implemented: required fields, enum values, adapter/evidence consistency.
Not implemented yet: JSON-Schema export, citation resolution, license-text checks.
"""
from __future__ import annotations

from ..common.types import EvidenceState, Permission

ACCESS = {"open", "gated_auto", "gated_manual", "registration", "hosted_only", "unknown"}
TIERS = {"default", "optional", "gated", "big_machine", "manual"}
MODEL_KINDS = {"specialist", "encoder", "coordinator", "retrieval", "vlm"}
SUBSET_UNITS = {"patient", "file", "image", "slide"}
SUBSET_FETCHERS = {"tcia", "zenodo", "figshare", "isic", "gdc", "s3"}

_COMMON = ("id", "name", "license", "access", "evidence_state", "acquisition", "citation")
_MODEL = ("kind", "tasks", "modality", "anatomy", "input", "outputs", "inference_permission")
_DATASET = ("modality", "anatomy", "counts", "labels")


def _common(rec: dict) -> list[str]:
    errs = [f"missing field {f!r}" for f in _COMMON if f not in rec]
    if rec.get("access") not in ACCESS:
        errs.append(f"access {rec.get('access')!r} not in {sorted(ACCESS)}")
    if rec.get("evidence_state") not in {s.value for s in EvidenceState}:
        errs.append(f"evidence_state {rec.get('evidence_state')!r} invalid")
    acq = rec.get("acquisition", {})
    if acq.get("tier") not in TIERS:
        errs.append(f"acquisition.tier {acq.get('tier')!r} not in {sorted(TIERS)}")
    if acq.get("tier") == "manual" and not acq.get("instructions"):
        errs.append("manual-tier records need acquisition.instructions")
    return errs + _subset(acq) + _supporting(acq)


def _subset(acq: dict) -> list[str]:
    errs = []
    sub = acq.get("subset")
    if sub is not None:
        if not isinstance(sub, dict) or sub.get("unit") not in SUBSET_UNITS:
            return [f"acquisition.subset.unit must be one of {sorted(SUBSET_UNITS)}"]
        if acq.get("fetcher") not in SUBSET_FETCHERS:
            errs.append(f"fetcher {acq.get('fetcher')!r} has no subset listing")
        if sub.get("required") and acq.get("tier") == "default":
            errs.append("default-tier records must be downloadable without choosing a subset")
    if acq.get("fetcher") in {"isic", "gdc", "s3"} and not (sub or {}).get("required"):
        errs.append(f"{acq['fetcher']} records are subset-only; set acquisition.subset.required")
    if acq.get("fetcher") == "gdc":
        content = acq.get("filters", {}).get("content", [])
        if not any(c.get("op") == "=" and c.get("content") == {"field": "access", "value": "open"} for c in content):
            errs.append("gdc filters must include access = open")
    return errs


def _supporting(acq: dict) -> list[str]:
    files = acq.get("supporting", [])
    if not isinstance(files, list):
        return ["acquisition.supporting must be a list"]
    errs = []
    for i, f in enumerate(files):
        rel = f.get("relpath", "") if isinstance(f, dict) else ""
        if not isinstance(f, dict) or not str(f.get("url", "")).startswith("https://"):
            errs.append(f"acquisition.supporting[{i}] needs an https url")
        elif not rel or rel.startswith("/") or ".." in rel.split("/"):
            errs.append(f"acquisition.supporting[{i}].relpath must be a relative path inside the record")
        elif not isinstance(f.get("size"), int):
            errs.append(f"acquisition.supporting[{i}] needs its size in bytes")
    return errs


def validate_model(rec: dict) -> list[str]:
    errs = _common(rec) + [f"missing field {f!r}" for f in _MODEL if f not in rec]
    if rec.get("kind") not in MODEL_KINDS:
        errs.append(f"kind {rec.get('kind')!r} not in {sorted(MODEL_KINDS)}")
    if rec.get("inference_permission") not in {p.value for p in Permission}:
        errs.append(f"inference_permission {rec.get('inference_permission')!r} invalid")
    state = rec.get("evidence_state")
    if state in {EvidenceState.RUNNABLE.value, EvidenceState.LOCALLY_REPRODUCED.value} and not rec.get("adapter"):
        errs.append(f"evidence_state {state!r} requires an adapter id")
    return [f"{rec.get('id', '?')}: {e}" for e in errs]


def validate_dataset(rec: dict) -> list[str]:
    errs = _common(rec) + [f"missing field {f!r}" for f in _DATASET if f not in rec]
    return [f"{rec.get('id', '?')}: {e}" for e in errs]
