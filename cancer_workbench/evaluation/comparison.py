"""Paired binary ranking comparisons with patient-cluster bootstrap (stdlib).

Binary prediction rows use sample_id, patient_id, label=0/1 and score=0..1.
Both arms must score exactly the same samples. All views of a sampled patient
travel together, and both arms use the same draw. Deltas are arm_b minus arm_a.
"""
from __future__ import annotations

import math
import random

from ._binary import binary_rows


def ranking_metrics(rows: list[dict]) -> dict:
    """ROC-AUC (half credit for ties) and non-interpolated average precision.

    Single-class input returns null ranking metrics. Average precision is
    named explicitly; it is not trapezoidal area under a PR curve.
    """
    binary_rows(rows, patients=False)
    positives = sum(r["label"] for r in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return {"roc_auc": None, "average_precision": None}
    grouped = {}
    for row in rows:
        counts = grouped.setdefault(row["score"], [0, 0])
        counts[int(row["label"])] += 1
    lower_negatives = concordant = 0
    for score in sorted(grouped):
        neg, pos = grouped[score]
        concordant += pos * (lower_negatives + 0.5 * neg)
        lower_negatives += neg
    tp = seen = 0
    ap = 0.0
    for score in sorted(grouped, reverse=True):
        neg, pos = grouped[score]
        tp += pos
        seen += pos + neg
        ap += pos / positives * tp / seen
    return {"roc_auc": concordant / (positives * negatives), "average_precision": ap}


def _percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def paired_binary(arm_a: list[dict], arm_b: list[dict], *, n_boot: int = 1000, seed: int = 0,
                  min_valid: int = 100) -> dict:
    """Return ranking deltas and percentile 95% CIs; never silently fall back to images.

    Intervals are withheld unless >= min_valid and >= 80% of requested draws
    contain both classes, with >= 2 distinct patient groups. These software
    safeguards are not a power analysis or a guarantee of CI coverage.
    """
    binary_rows(arm_a)
    binary_rows(arm_b)
    if isinstance(n_boot, bool) or not isinstance(n_boot, int) or n_boot < 1:
        raise ValueError("n_boot must be a positive integer")
    if isinstance(min_valid, bool) or not isinstance(min_valid, int) or min_valid < 2 or min_valid > n_boot:
        raise ValueError("min_valid must be between 2 and n_boot")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer for reproducible resampling")
    a, b = ({r["sample_id"]: r for r in arm} for arm in (arm_a, arm_b))
    if a.keys() != b.keys():
        raise ValueError("arms must have exactly the same sample_ids; do not intersect or truncate")
    ids = sorted(a)
    for sid in ids:
        if any(a[sid].get(k) != b[sid].get(k) for k in ("label", "patient_id", "partition")):
            raise ValueError(f"label, patient or partition mismatch for {sid!r}")
    if len({a[sid].get("partition") for sid in ids}) > 1:
        raise ValueError("comparison must cover one evaluation partition")
    if any(a[sid].get("partition") == "train" for sid in ids):
        raise ValueError("comparison requires evaluation predictions, not train rows")
    groups = {}
    for sid in ids:
        groups.setdefault(a[sid]["patient_id"], []).append(sid)
    # Shared patient ids must never bridge partitions (checked above). Multiple
    # image labels per patient are allowed here: this estimates image-weighted
    # ranking uncertainty with clustered draws, not a patient endpoint.
    point_a, point_b = ranking_metrics(arm_a), ranking_metrics(arm_b)
    deltas = {k: point_b[k] - point_a[k] if point_a[k] is not None else None for k in point_a}
    draws = {k: [] for k in deltas}
    rng = random.Random(seed)
    members = [groups[k] for k in sorted(groups)]
    valid = 0
    for _ in range(n_boot):
        sampled = [sid for _ in members for sid in members[rng.randrange(len(members))]]
        # Draw multiplicity must be retained, so assign temporary draw ids;
        # sample_id validation in ranking_metrics must still reject caller duplicates.
        metrics = [ranking_metrics([dict(arm[sid], sample_id=str(i)) for i, sid in enumerate(sampled)]) for arm in (a, b)]
        if metrics[0]["roc_auc"] is None:
            continue
        valid += 1
        for key in deltas:
            draws[key].append(metrics[1][key] - metrics[0][key])
    enough = len(groups) >= 2 and valid >= min_valid and valid / n_boot >= 0.8
    return {"n_samples": len(ids), "n_patients": len(groups), "arm_a": point_a, "arm_b": point_b,
            "delta_b_minus_a": deltas,
            "delta_ci95": {k: [_percentile(v, 0.025), _percentile(v, 0.975)] if enough else None for k, v in draws.items()},
            "bootstrap": {"unit": "patient", "paired": True, "requested": n_boot, "valid": valid,
                          "invalid_single_class": n_boot - valid, "seed": seed, "min_valid": min_valid},
            "warnings": [] if enough else ["Intervals withheld: too few patients or valid two-class bootstrap draws"],
            "estimand": "image-weighted ranking metrics with patient-cluster uncertainty; not patient-level diagnosis"}
