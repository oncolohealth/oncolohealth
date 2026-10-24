"""Metrics. Owner: Workstream F. Needs the `ml` extra (numpy, scikit-learn).

Bootstrap CIs resample by group when `group_ids` are given. Without them they
resample images, which treats every image as independent: when several images
come from one patient the intervals are too narrow, and the report says so.
"""
from __future__ import annotations

from ._validation import binary_inputs, bootstrap_options, finite_number, groups, labels, positive_int, probabilities

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


def _ci(stat, y_true, scores, group_ids, n_boot, seed, required_classes):
    import numpy as np

    rng = np.random.default_rng(seed)
    draw = _resample_groups(group_ids, len(y_true), rng)
    vals, missing_class, nonfinite = [], 0, 0
    for _ in range(n_boot):
        idx = draw()
        if set(y_true[idx].tolist()) != set(required_classes):
            missing_class += 1
            continue
        value = float(stat(y_true[idx], scores[idx]))
        if not np.isfinite(value):
            nonfinite += 1
            continue
        vals.append(value)
    n_groups = len(set(group_ids)) if group_ids is not None else len(y_true)
    enough = n_groups >= 2 and len(vals) >= 2 and len(vals) / n_boot >= 0.8
    interval = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if enough else None
    return {"ci95": interval, "requested": n_boot, "valid": len(vals),
            "invalid_missing_class": missing_class, "invalid_nonfinite": nonfinite,
            "n_groups": n_groups, "unit": "patient" if group_ids is not None else "image", "seed": seed,
            "warning": None if enough else "Interval withheld: fewer than two groups/valid draws or under 80% valid draws"}


def binary_report(y_true: list[int], scores: list[float], threshold: float, group_ids: list[str] | None = None,
                  *, n_boot: int = 1000, seed: int = 0) -> dict:
    """Threshold metrics at `threshold` (chosen on development data) plus ROC-AUC and PR-AUC with 95% CIs."""
    import numpy as np
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, s = binary_inputs(y_true, scores)
    threshold = finite_number(threshold, "threshold")
    group_ids = groups(group_ids, len(y))
    bootstrap_options(n_boot, seed)
    n_boot, seed = int(n_boot), int(seed)
    pred = (s >= threshold).astype(int)
    tp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 0) & (y == 1)).sum())
    tn, fp = int(((pred == 0) & (y == 0)).sum()), int(((pred == 1) & (y == 0)).sum())
    div = lambda a, b: a / b if b else None
    both_classes = len(set(y.tolist())) == 2
    bootstrap = {key: _ci(stat, y, s, group_ids, n_boot, seed, (0, 1)) for key, stat in
                 (("roc_auc", roc_auc_score), ("pr_auc", average_precision_score))}
    return {
        "n": int(len(y)), "positives": int(y.sum()), "threshold": float(threshold),
        "sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
        "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn),
        "confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        "roc_auc": float(roc_auc_score(y, s)) if both_classes else None,
        "pr_auc": float(average_precision_score(y, s)) if both_classes else None,
        "roc_auc_ci95": bootstrap["roc_auc"]["ci95"], "pr_auc_ci95": bootstrap["pr_auc"]["ci95"],
        "pr_auc_definition": "non-interpolated average precision", "bootstrap": bootstrap,
        "warnings": [] if both_classes else ["Ranking metrics undefined by policy: cohort contains only one class"],
        "ci_method": "grouped bootstrap" if group_ids is not None else UNGROUPED,
    }


def multiclass_report(y_true: list[int], probs: list[list[float]], classes: list[str], group_ids: list[str] | None = None,
                      *, n_boot: int = 1000, seed: int = 0) -> dict:
    """Per-class recall, balanced accuracy and macro one-vs-rest ROC-AUC (with CIs), confusion matrix. Argmax decisions."""
    import numpy as np
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score

    if (not isinstance(classes, (list, tuple)) or len(classes) < 3
            or any(not isinstance(c, str) or not c.strip() for c in classes) or len(set(classes)) != len(classes)):
        raise ValueError("classes must contain at least three unique nonempty class names in probability-column order")
    y = labels(y_true, len(classes))
    p = probabilities(probs, len(y), len(classes))
    group_ids = groups(group_ids, len(y))
    bootstrap_options(n_boot, seed)
    n_boot, seed = int(n_boot), int(seed)
    pred = p.argmax(1)
    cm = confusion_matrix(y, pred, labels=list(range(len(classes))))
    macro_auc = lambda yy, pp: roc_auc_score(yy, pp, multi_class="ovr", average="macro", labels=list(range(len(classes))))
    bacc = lambda yy, pp: balanced_accuracy_score(yy, pp.argmax(1))
    all_classes = set(y.tolist()) == set(range(len(classes)))
    bootstrap = {key: _ci(stat, y, p, group_ids, n_boot, seed, range(len(classes))) for key, stat in
                 (("balanced_accuracy", bacc), ("macro_roc_auc", macro_auc))}
    return {
        "n": int(len(y)), "classes": list(classes),
        "support": {c: int((y == i).sum()) for i, c in enumerate(classes)},
        "recall": {c: (float(cm[i, i] / cm[i].sum()) if cm[i].sum() else None) for i, c in enumerate(classes)},
        "one_vs_rest_roc_auc": {c: float(roc_auc_score(y == i, p[:, i])) for i, c in enumerate(classes) if 0 < (y == i).sum() < len(y)},
        "balanced_accuracy": float(bacc(y, p)) if all_classes else None,
        "balanced_accuracy_ci95": bootstrap["balanced_accuracy"]["ci95"],
        "macro_roc_auc": float(macro_auc(y, p)) if all_classes else None,
        "macro_roc_auc_ci95": bootstrap["macro_roc_auc"]["ci95"], "bootstrap": bootstrap,
        "warnings": [] if all_classes else ["Full-class aggregate metrics undefined: at least one declared class has no observations"],
        "confusion": {"labels": list(classes), "rows_true_cols_pred": cm.tolist()},
        "ci_method": "grouped bootstrap" if group_ids is not None else UNGROUPED,
    }


def calibration(y_true: list[int], probs: list[float], n_bins: int = 10) -> dict:
    """Expected calibration error and reliability bins for a binary probability."""
    import numpy as np

    y, p = binary_inputs(y_true, probs)
    n_bins = positive_int(n_bins, "n_bins")
    edges = np.linspace(0, 1, n_bins + 1)
    bins, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            conf, acc = float(p[m].mean()), float(y[m].mean())
            ece += m.mean() * abs(conf - acc)
            bins.append({"lo": float(lo), "hi": float(hi), "n": int(m.sum()), "mean_prob": conf, "observed_rate": acc})
    return {"ece": float(ece), "bins": bins}
