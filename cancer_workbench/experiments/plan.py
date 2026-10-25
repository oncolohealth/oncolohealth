"""Conservative, side-effect-free experiment drafts. See docs/reports/B-plan-contract.md."""
from __future__ import annotations

import math
import re

from ..routing.router import runnable_blockers
from .records import REUSE_PATHS


def _nonnegative_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    # Integers are finite without conversion to a bounded floating-point type.
    return value >= 0 and (isinstance(value, int) or math.isfinite(value))


def plan_experiment(path: str, model: dict, dataset_audit: dict | None = None, budget: dict | None = None) -> dict:
    """Return blocked or ready_for_review; neither state authorizes execution.

    Transfer/distillation rights are supplied as a reviewed overlay in
    model['reuse_permissions'][path] = {'status': 'allowed', 'evidence': '...'}.
    Budget is {used_bytes, planned_bytes, limit_bytes}; limit_bytes None means
    no configured cap. No resource estimates
    are invented. Catalog records and all input objects remain unchanged.
    """
    if path not in REUSE_PATHS:
        raise ValueError(f"unknown reuse path: {path!r}")
    if not isinstance(model, dict):
        raise ValueError("model must be a record")
    blockers = []
    if not isinstance(model.get("id"), str) or not model["id"].strip():
        blockers.append("missing model id")
    acquisition = model.get("acquisition")
    revision = acquisition.get("revision") if isinstance(acquisition, dict) else None
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
        blockers.append("model revision must be an immutable 40/64-character commit or digest")
    if path == "specialist_tools":
        blockers.extend(runnable_blockers(model))
    else:
        permissions = model.get("reuse_permissions", {})
        permission = permissions.get(path) if isinstance(permissions, dict) else None
        if (not isinstance(permission, dict) or permission.get("status") != "allowed"
                or not isinstance(permission.get("evidence"), str) or not permission["evidence"].strip()):
            blockers.append(f"{path} requires reviewed permission with an evidence reference")
        if model.get("evidence_state") not in {"access_obtained", "runnable", "locally_reproduced", "externally_evaluated"}:
            blockers.append("model access has not been recorded")

    if not isinstance(dataset_audit, dict):
        blockers.append("dataset audit is required")
    else:
        if dataset_audit.get("ready_for_training") is not True:
            blockers.append("dataset audit is not ready_for_training")
        rows = dataset_audit.get("rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows <= 0:
            blockers.append("dataset audit has no positive row count")
        findings = dataset_audit.get("findings")
        if not isinstance(findings, list):
            blockers.append("dataset audit findings are missing or malformed")
        else:
            for finding in findings:
                if (not isinstance(finding, dict) or not isinstance(finding.get("code"), str)
                        or not finding["code"].strip() or finding.get("severity") not in {"info", "warning", "error"}):
                    blockers.append("malformed dataset audit finding")
                elif finding.get("severity") == "error" or finding["code"] in {"missing_patient_id", "unresolved_evidence"}:
                    blockers.append(f"dataset audit: {finding['code']}")

    checked_budget = None
    keys = ("used_bytes", "planned_bytes", "limit_bytes")
    limit = budget.get("limit_bytes", False) if isinstance(budget, dict) else False
    if (not isinstance(budget, dict) or any(not _nonnegative_number(budget.get(k)) for k in keys[:2])
            or not (limit is None or _nonnegative_number(limit))):
        blockers.append("budget requires finite nonnegative used_bytes and planned_bytes, and limit_bytes (null for no cap)")
    else:
        checked_budget = {k: budget[k] for k in keys}
        if limit is not None and budget["used_bytes"] + budget["planned_bytes"] > limit:
            blockers.append("planned storage exceeds budget")
    return {
        "path": path, "model_id": model.get("id"), "model_revision": revision,
        "dataset_id": dataset_audit.get("dataset_id") if isinstance(dataset_audit, dict) else None,
        "state": "blocked" if blockers else "ready_for_review", "blockers": blockers,
        "budget": checked_budget, "execution_authorized": False,
        "note": "Draft checks only. Endpoint, eligibility, overlap, split and execution scope still require protocol review.",
    }
