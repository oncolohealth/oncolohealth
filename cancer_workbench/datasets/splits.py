"""Deterministic grouped splitting: every row of a group lands in the same partition."""
from __future__ import annotations

import collections
import hashlib


def _group_key(row: dict) -> str:
    # duplicates are merged with their patient: both must stay on one side
    return row.get("patient_id") or row.get("duplicate_group") or f"__sample__{row['sample_id']}"


def grouped_split(rows: list[dict], fractions: dict[str, float], seed: str = "0", stratify: bool = True) -> list[dict]:
    """Assign `partition` by group, approximately matching `fractions` (e.g. {"train":.7,"val":.15,"test":.15}).

    Rows without patient_id fall back to duplicate_group, then to their own sample:
    the audit flags those so the limitation stays visible. Returns new row dicts.
    """
    if abs(sum(fractions.values()) - 1.0) > 1e-6:
        raise ValueError("fractions must sum to 1")
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        groups[_group_key(r)].append(r)

    def majority_label(members: list[dict]) -> str:
        return collections.Counter(m["label"] for m in members).most_common(1)[0][0] if stratify else ""

    strata: dict[str, list[str]] = collections.defaultdict(list)
    for g, members in groups.items():
        strata[majority_label(members)].append(g)

    names = list(fractions)
    assignment: dict[str, str] = {}
    for _, gs in sorted(strata.items()):
        gs.sort(key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())
        n = len(gs)
        bounds, acc = [], 0.0
        for name in names:
            acc += fractions[name]
            bounds.append(round(acc * n))
        start = 0
        for name, end in zip(names, bounds):
            for g in gs[start:end]:
                assignment[g] = name
            start = end
    return [dict(r, partition=assignment[_group_key(r)]) for r in rows]
