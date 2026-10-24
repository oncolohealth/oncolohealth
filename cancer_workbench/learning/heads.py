"""Feature-head training/evaluation. Owner: Workstream E. Needs the `ml` extra.

Contract change from the package docstring: the head is an L2-regularized
logistic regression (scikit-learn, lbfgs) on standardized features, with
balanced class weights. Its regularization strength is picked from `c_grid`
on VAL rows only; the head is fit on TRAIN rows only. Distillation
(`teacher_weight > 0`) is not implemented yet.
"""
from __future__ import annotations

import dataclasses
from typing import Any

C_GRID = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0)


@dataclasses.dataclass
class HeadModel:
    encoder: dict[str, str]  # encoder_id, revision, preprocessing_hash
    classes: list[str]  # ordered; probability column i is classes[i]
    C: float
    val_score: float  # macro one-vs-rest ROC-AUC on val at the chosen C
    mean: Any
    scale: Any
    clf: Any
    train_ids: frozenset
    train_patients: frozenset


def _rows(data: dict, partition: str):
    import numpy as np

    idx = np.where(data["partitions"] == partition)[0]
    if not len(idx):
        raise ValueError(f"no {partition!r} rows")
    return idx


def _check(data: dict) -> None:
    for k in ("features", "labels", "partitions", "sample_ids", "classes", "encoder"):
        if k not in data:
            raise ValueError(f"data lacks {k!r}")
    unknown = set(data["labels"].tolist()) - set(data["classes"])
    if unknown:
        raise ValueError(f"labels outside the declared classes: {sorted(unknown)}")


def _auc(y, probs, n_classes):
    from sklearn.metrics import roc_auc_score

    return roc_auc_score(y, probs[:, 1]) if n_classes == 2 else roc_auc_score(y, probs, multi_class="ovr", average="macro")


def train_feature_head(data: dict[str, Any], *, c_grid=C_GRID, teacher_weight: float = 0.0) -> HeadModel:
    """`data`: features (N x D), labels, partitions, sample_ids, optional patient_ids, ordered classes, encoder ref."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    if teacher_weight:
        raise NotImplementedError("distillation needs a reviewed teacher and permission; not implemented")
    _check(data)
    classes = list(data["classes"])
    y = np.array([classes.index(l) for l in data["labels"]])
    tr, va = _rows(data, "train"), _rows(data, "val")
    if len(set(y[tr])) < len(classes):
        raise ValueError("train rows do not cover every class")
    X = data["features"].astype(np.float64)
    mean, scale = X[tr].mean(0), X[tr].std(0) + 1e-6
    Z = (X - mean) / scale

    def fit(C):
        return LogisticRegression(C=C, class_weight="balanced", max_iter=5000).fit(Z[tr], y[tr])

    scored = [(_auc(y[va], fit(C).predict_proba(Z[va]), len(classes)), C) for C in c_grid]
    best_score, best_C = max(scored, key=lambda s: (s[0], -s[1]))  # ties go to the stronger regularization
    pids = data.get("patient_ids")
    return HeadModel(encoder=dict(data["encoder"]), classes=classes, C=best_C, val_score=float(best_score),
                     mean=mean, scale=scale, clf=fit(best_C), train_ids=frozenset(data["sample_ids"][tr].tolist()),
                     train_patients=frozenset(p for p in (pids[tr].tolist() if pids is not None else []) if p))


def evaluate_head(model: HeadModel, data: dict[str, Any], partition: str = "test") -> dict[str, Any]:
    """Predict `partition` rows. Refuses leakage or a mismatched encoder/class order; computes no headline metrics."""
    import numpy as np

    _check(data)
    if dict(data["encoder"]) != model.encoder:
        raise ValueError(f"encoder mismatch: head trained on {model.encoder}, data from {dict(data['encoder'])}")
    if list(data["classes"]) != model.classes:
        raise ValueError(f"class order mismatch: {model.classes} vs {list(data['classes'])}")
    idx = _rows(data, partition)
    ids = data["sample_ids"][idx].tolist()
    if overlap := model.train_ids & set(ids):
        raise ValueError(f"{len(overlap)} {partition} samples were used for training, e.g. {sorted(overlap)[:3]}")
    pids = data.get("patient_ids")
    if pids is not None and (overlap := model.train_patients & {p for p in pids[idx].tolist() if p}):
        raise ValueError(f"{len(overlap)} {partition} patients also appear in training")
    Z = (data["features"][idx].astype(np.float64) - model.mean) / model.scale
    return {"sample_ids": ids, "classes": model.classes, "y_true": [model.classes.index(l) for l in data["labels"][idx]],
            "probs": model.clf.predict_proba(Z).tolist()}
