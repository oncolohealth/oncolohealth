"""Reviewed tool-use examples for possible coordinator adaptation. Owner: Workstream D.

export_curriculum(records) -> list[dict]
    Export only records marked reviewed whose tool results were OBSERVED (e.g.
    TurnRecord.steps from coordinator.loop), pairing every call with its result
    and validating arguments against the tool schema. Include rejections,
    failures and abstentions. Never include invented results or hidden reasoning.

Candidates are captured by `curriculum.capture` (python -m cancer_workbench
curriculum capture) and start pending review.
"""
from __future__ import annotations


def export_curriculum(records: list[dict]) -> list[dict]:
    """Return the training-admissible subset: reviewed train candidates with fresh responses and observed calls only."""
    from ..coordinator.tools import _argument_errors

    out = []
    for rec in records:
        review = rec.get("review") or {}
        if (review.get("status") != "reviewed" or review.get("rights_status") != "cleared"
                or rec.get("split") != "train_candidate" or rec.get("state") != "pending_review"):
            continue
        calls = rec.get("calls") or []
        if not calls or any("observed" not in c or not c.get("schema") for c in calls):
            continue
        if any(_argument_errors(c["arguments"], dict(c["schema"]["function"]["parameters"], additionalProperties=False))
               and "error" not in c["observed"] for c in calls):
            continue
        out.append({"candidate_id": rec["candidate_id"], "messages": rec["messages"], "thinking_mode": rec["thinking_mode"]})
    return out
