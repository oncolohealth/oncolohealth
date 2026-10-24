"""Decision thresholds. Owner: Workstream F. Choose on development (val) data only, never on test."""
from __future__ import annotations


def choose_threshold(y_true: list[int], scores: list[float], rule: str = "youden") -> float:
    """`youden` maximizes sensitivity + specificity - 1; `sensitivity>=X` takes the highest threshold reaching X."""
    import numpy as np
    from sklearn.metrics import roc_curve

    fpr, tpr, thr = roc_curve(np.asarray(y_true), np.asarray(scores, dtype=float))
    thr = np.minimum(thr, 1.0)  # roc_curve's first threshold is +inf
    if rule == "youden":
        return float(thr[int(np.argmax(tpr - fpr))])
    if rule.startswith("sensitivity>="):
        target = float(rule.split(">=", 1)[1])
        ok = np.where(tpr >= target)[0]
        return float(thr[ok[0]])
    raise ValueError(f"unknown threshold rule {rule!r}")
