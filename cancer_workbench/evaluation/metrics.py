"""Metrics. Owner: Workstream F. Needs the `ml` extra (numpy, scikit-learn).

Bootstrap CIs resample by group when `group_ids` are given. Without them they
resample images, which treats every image as independent: when several images
come from one patient the intervals are too narrow, and the report says so.
"""
from __future__ import annotations

UNGROUPED = "resampled by image: intervals are too narrow if images share patients"


def _resample_groups(group_ids, n, rng):
    import numpy as np

    if group_ids is None:
        return lambda: rng.integers(0, n, n)
    groups = {}
    for i, g in enumerate(group_ids):
        groups.setdefault(g, []).append(i)
    members = list(groups.values())
    return lambda: np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])


def _ci(stat, y_true, scores, group_ids, n_boot, seed):
    import numpy as np

    rng = np.random.default_rng(seed)
    draw = _resample_groups(group_ids, len(y_true), rng)
    vals = []
    for _ in range(n_boot):
        idx = draw()
        try:
            vals.append(stat(y_true[idx], scores[idx]))
        except ValueError:  # a resample missing a class
            continue
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


def binary_report(y_true: list[int], scores: list[float], threshold: float, group_ids: list[str] | None = None,
                  *, n_boot: int = 1000, seed: int = 0) -> dict:
    """Threshold metrics at `threshold` (chosen on development data) plus ROC-AUC and PR-AUC with 95% CIs."""
    import numpy as np
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, s = np.asarray(y_true), np.asarray(scores, dtype=float)
    pred = (s >= threshold).astype(int)
    tp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 0) & (y == 1)).sum())
    tn, fp = int(((pred == 0) & (y == 0)).sum()), int(((pred == 1) & (y == 0)).sum())
    div = lambda a, b: a / b if b else None
    return {
        "n": int(len(y)), "positives": int(y.sum()), "threshold": float(threshold),
        "sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
        "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn),
        "confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        "roc_auc": float(roc_auc_score(y, s)), "pr_auc": float(average_precision_score(y, s)),
        "roc_auc_ci95": _ci(roc_auc_score, y, s, group_ids, n_boot, seed),
        "pr_auc_ci95": _ci(average_precision_score, y, s, group_ids, n_boot, seed),
        "ci_method": "grouped bootstrap" if group_ids is not None else UNGROUPED,
    }


def multiclass_report(y_true: list[int], probs: list[list[float]], classes: list[str], group_ids: list[str] | None = None,
                      *, n_boot: int = 1000, seed: int = 0) -> dict:
    """Per-class recall, balanced accuracy and macro one-vs-rest ROC-AUC (with CIs), confusion matrix. Argmax decisions."""
    import numpy as np
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score

    y, p = np.asarray(y_true), np.asarray(probs, dtype=float)
    pred = p.argmax(1)
    cm = confusion_matrix(y, pred, labels=list(range(len(classes))))
    macro_auc = lambda yy, pp: roc_auc_score(yy, pp, multi_class="ovr", average="macro", labels=list(range(len(classes))))
    bacc = lambda yy, pp: balanced_accuracy_score(yy, pp.argmax(1))
    return {
        "n": int(len(y)), "classes": list(classes),
        "support": {c: int((y == i).sum()) for i, c in enumerate(classes)},
        "recall": {c: (float(cm[i, i] / cm[i].sum()) if cm[i].sum() else None) for i, c in enumerate(classes)},
        "one_vs_rest_roc_auc": {c: float(roc_auc_score(y == i, p[:, i])) for i, c in enumerate(classes) if 0 < (y == i).sum() < len(y)},
        "balanced_accuracy": float(bacc(y, p)), "balanced_accuracy_ci95": _ci(bacc, y, p, group_ids, n_boot, seed),
        "macro_roc_auc": float(macro_auc(y, p)), "macro_roc_auc_ci95": _ci(macro_auc, y, p, group_ids, n_boot, seed),
        "confusion": {"labels": list(classes), "rows_true_cols_pred": cm.tolist()},
        "ci_method": "grouped bootstrap" if group_ids is not None else UNGROUPED,
    }


def calibration(y_true: list[int], probs: list[float], n_bins: int = 10) -> dict:
    """Expected calibration error and reliability bins for a binary probability."""
    import numpy as np

    y, p = np.asarray(y_true), np.asarray(probs, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    bins, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            conf, acc = float(p[m].mean()), float(y[m].mean())
            ece += m.mean() * abs(conf - acc)
            bins.append({"lo": float(lo), "hi": float(hi), "n": int(m.sum()), "mean_prob": conf, "observed_rate": acc})
    return {"ece": float(ece), "bins": bins}
