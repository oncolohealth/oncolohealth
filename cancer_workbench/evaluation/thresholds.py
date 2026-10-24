"""Decision thresholds. Owner: Workstream F. Choose on development (val) data only, never on test."""
from __future__ import annotations

from ._validation import binary_inputs


def choose_threshold(y_true: list[int], scores: list[float], rule: str = "youden") -> float:
    """`youden` maximizes sensitivity + specificity - 1; `sensitivity>=X` takes the highest threshold reaching X."""
    import numpy as np
    from sklearn.metrics import roc_curve

    y, s = binary_inputs(y_true, scores)
    if len(set(y.tolist())) != 2:
        raise ValueError("threshold selection requires both classes in development data")
    if not isinstance(rule, str):
        raise ValueError("rule must be 'youden' or 'sensitivity>=X'")
    target = None
    if rule.startswith("sensitivity>="):
        try:
            target = float(rule.split(">=", 1)[1])
        except ValueError:
            raise ValueError("sensitivity target must be finite and within [0, 1]") from None
        if not np.isfinite(target) or not 0 <= target <= 1:
            raise ValueError("sensitivity target must be finite and within [0, 1]")
    elif rule != "youden":
        raise ValueError(f"unknown threshold rule {rule!r}")
    fpr, tpr, thr = roc_curve(y, s, drop_intermediate=False)
    # Preserve the no-positive-predictions ROC point even when a score is 1.
    # Clipping +inf to 1 would change the predictions at that operating point.
    thr = np.where(np.isinf(thr), np.nextafter(s.max(), np.inf), thr)
    if rule == "youden":
        return float(thr[int(np.argmax(tpr - fpr))])
    if target is not None:
        ok = np.where(tpr >= target)[0]
        return float(thr[ok[0]])
    raise ValueError(f"unknown threshold rule {rule!r}")
