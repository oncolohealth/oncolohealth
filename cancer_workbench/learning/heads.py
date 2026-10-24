"""Feature-head training/evaluation. Owner: Workstream E. Needs the `ml` extra.

Contract change from the package docstring: the head is an L2-regularized
logistic regression (scikit-learn, lbfgs) on standardized features, with
balanced class weights. Its regularization strength is picked from `c_grid`
on VAL rows only; the head is fit on TRAIN rows only. Distillation
(`teacher_weight > 0`) is not implemented yet. `save_head` / `load_head`
store a head as plain arrays so a run's head can be reused for scoring.
"""
from __future__ import annotations

import dataclasses
from typing import Any

C_GRID = (0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0)


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


def _check(data: dict) -> dict:
    """Normalize and validate a feature table before any fitting or prediction.

    Empty patient/duplicate identities remain unknown. These checks detect
    declared overlap only and cannot establish independence from missing IDs.
    """
    import numpy as np

    for k in ("features", "labels", "partitions", "sample_ids", "classes", "encoder"):
        if k not in data:
            raise ValueError(f"data lacks {k!r}")
    checked = dict(data)
    classes = data["classes"]
    if not isinstance(classes, (list, tuple)) or len(classes) < 2 or any(
            not isinstance(c, str) or not c.strip() for c in classes) or len(set(classes)) != len(classes):
        raise ValueError("classes must contain at least two unique nonempty strings")
    X = np.asarray(data["features"])
    if X.ndim != 2 or 0 in X.shape or X.dtype.kind not in "iuf":
        raise ValueError("features must be a nonempty real numeric N x D array")
    X = X.astype(np.float64, copy=False)
    if not np.isfinite(X).all():
        raise ValueError("features must be finite")
    checked["features"] = X
    for key in ("labels", "partitions", "sample_ids", "patient_ids", "group_ids", "duplicate_groups", "image_hashes"):
        if key not in data or (key in ("patient_ids", "group_ids", "duplicate_groups", "image_hashes") and data[key] is None):
            checked.pop(key, None)
            continue
        col = np.asarray(data[key])
        if col.ndim != 1 or len(col) != len(X):
            raise ValueError(f"{key} must be one-dimensional and aligned with features")
        if any(not isinstance(v, str) for v in col.tolist()):
            raise ValueError(f"{key} must contain strings")
        if key in ("labels", "partitions", "sample_ids") and any(not v.strip() for v in col.tolist()):
            raise ValueError(f"{key} must contain nonempty strings")
        checked[key] = col
    if len(set(checked["sample_ids"].tolist())) != len(X):
        raise ValueError("sample_ids must be unique; duplicate samples cannot enter head fitting")
    if set(checked["partitions"].tolist()) - {"train", "val", "test", "unassigned"}:
        raise ValueError("partitions must be train, val, test or unassigned")
    unknown = set(checked["labels"].tolist()) - set(classes)
    if unknown:
        raise ValueError(f"labels outside the declared classes: {sorted(unknown)}")
    enc = data["encoder"]
    if not isinstance(enc, dict) or any(not isinstance(enc.get(k), str) or not enc[k].strip()
                                          for k in ("encoder_id", "revision", "preprocessing_hash")):
        raise ValueError("encoder must declare nonempty encoder_id, revision and preprocessing_hash")
    for key in ("patient_ids", "group_ids", "duplicate_groups", "image_hashes"):
        seen = {}
        for identity, part in zip(checked.get(key, []), checked["partitions"]):
            if not identity.strip() or part == "unassigned":
                continue
            if identity in seen and seen[identity] != part:
                raise ValueError(f"{key} overlap across {seen[identity]} and {part} partitions")
            seen[identity] = part
    return checked


PARTITIONS = ("train", "val", "test", "unassigned")


def validate_head_inputs(data: dict[str, Any]) -> None:
    """Public pre-fit guard retained from the source-shift implementation.

    Uses the shared normalized table checks, including canonical group_ids.
    Unassigned rows may share declared groups but never enter head fitting.
    Missing identities remain unknown and do not establish independence.
    """
    data = _check(data)
    for name in ("train", "val"):
        idx = _rows(data, name)
        if set(data["labels"][idx].tolist()) != set(data["classes"]):
            raise ValueError(f"{name} rows do not cover every class")


def _auc(y, probs, n_classes):
    from sklearn.metrics import roc_auc_score

    return roc_auc_score(y, probs[:, 1]) if n_classes == 2 else roc_auc_score(y, probs, multi_class="ovr", average="macro")


def train_feature_head(data: dict[str, Any], *, c_grid=C_GRID, teacher_weight: float = 0.0) -> HeadModel:
    """Fit after `validate_head_inputs` checks the normalized feature table.

    `data` has features (N x D), labels, partitions, sample_ids, optional
    patient_ids/group_ids/image_hashes, ordered classes and encoder identity.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    if teacher_weight:
        raise NotImplementedError("distillation needs a reviewed teacher and permission; not implemented")
    data = _check(data)
    validate_head_inputs(data)
    if isinstance(c_grid, (str, bytes)):
        raise ValueError("c_grid must contain finite positive numbers")
    try:
        c_grid = tuple(c_grid)
    except TypeError as e:
        raise ValueError("c_grid must contain finite positive numbers") from e
    if not c_grid or any(isinstance(c, (bool, np.bool_)) or not isinstance(c, (int, float, np.integer, np.floating))
                         or not np.isfinite(c) or c <= 0 for c in c_grid):
        raise ValueError("c_grid must contain finite positive numbers")
    classes = list(data["classes"])
    y = np.array([classes.index(l) for l in data["labels"]])
    tr, va = _rows(data, "train"), _rows(data, "val")
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

    data = _check(data)
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


class _LinearProbs:
    """predict_proba of a fitted LogisticRegression rebuilt from its coefficients (sigmoid for 2 classes, else softmax)."""

    def __init__(self, coef, intercept):
        self.coef_, self.intercept_ = coef, intercept

    def predict_proba(self, Z):
        import numpy as np

        logits = Z @ self.coef_.T + self.intercept_
        if self.coef_.shape[0] == 1:
            p = 1.0 / (1.0 + np.exp(-logits[:, 0]))
            return np.column_stack([1.0 - p, p])
        e = np.exp(logits - logits.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)


def save_head(model: HeadModel, path) -> None:
    """Write the head as plain arrays (.npz, no pickle) so it can be reloaded without trusting the file's code."""
    import json

    import numpy as np

    np.savez(path, mean=model.mean, scale=model.scale, coef=model.clf.coef_, intercept=model.clf.intercept_,
             classes=np.array(model.classes), C=model.C, val_score=model.val_score, encoder=json.dumps(model.encoder),
             train_ids=np.array(sorted(model.train_ids)), train_patients=np.array(sorted(model.train_patients)))


def load_head(path) -> HeadModel:
    import json

    import numpy as np

    with np.load(path, allow_pickle=False) as z:
        return HeadModel(encoder=json.loads(z["encoder"].item()), classes=z["classes"].tolist(), C=float(z["C"]),
                         val_score=float(z["val_score"]), mean=z["mean"], scale=z["scale"],
                         clf=_LinearProbs(z["coef"], z["intercept"]), train_ids=frozenset(z["train_ids"].tolist()),
                         train_patients=frozenset(z["train_patients"].tolist()))
