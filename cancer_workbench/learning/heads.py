"""Feature-head training/evaluation. Owner: Workstream E. Needs the `ml` extra.

Contract change from the package docstring: the head is an L2-regularized
logistic regression (scikit-learn, lbfgs) on standardized features, with
balanced class weights. Its regularization strength is picked from `c_grid`
on VAL rows only; the head is fit on TRAIN rows only, after
`validate_head_inputs` refuses leaking or malformed inputs. Distillation
(`teacher_weight > 0`) is not implemented yet. `save_head` / `load_head`
store a head as plain arrays so a run's head can be reused for scoring.
"""
from __future__ import annotations

import collections
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


def _check(data: dict) -> None:
    for k in ("features", "labels", "partitions", "sample_ids", "classes", "encoder"):
        if k not in data:
            raise ValueError(f"data lacks {k!r}")
    unknown = set(data["labels"].tolist()) - set(data["classes"])
    if unknown:
        raise ValueError(f"labels outside the declared classes: {sorted(unknown)}")


PARTITIONS = ("train", "val", "test", "unassigned")


def validate_head_inputs(data: dict[str, Any]) -> None:
    """Refuse inputs a head must not be fit on, before any candidate C sees val.

    Checks array shapes and alignment, finite numeric features, unique sample
    ids, known partitions, class coverage in train and val, and that no patient
    (`patient_ids`) or duplicate group (`group_ids`) spans train, val and test.
    Blank patient or group ids mean unknown and are not compared.
    """
    import numpy as np

    _check(data)
    X = np.asarray(data["features"])
    if X.ndim != 2 or 0 in X.shape:
        raise ValueError(f"features must be a non-empty N x D array, got shape {X.shape}")
    if X.dtype.kind not in "fiu":
        raise ValueError(f"features must be numeric, got dtype {X.dtype}")
    if not np.isfinite(X).all():
        raise ValueError(f"{int((~np.isfinite(X)).any(1).sum())} feature rows contain NaN or infinite values")
    n = X.shape[0]
    for k in ("labels", "partitions", "sample_ids", "patient_ids", "group_ids"):
        if data.get(k) is not None and np.shape(data[k]) != (n,):
            raise ValueError(f"{k} has shape {np.shape(data[k])} but features have {n} rows")
    classes = list(data["classes"])
    if len(classes) < 2 or len(set(classes)) != len(classes):
        raise ValueError(f"classes must be at least two distinct names, got {classes}")
    ids = data["sample_ids"].tolist()
    if "" in ids:
        raise ValueError("blank sample ids")
    if len(set(ids)) != n:
        dupes = sorted(i for i, c in collections.Counter(ids).items() if c > 1)
        raise ValueError(f"{len(dupes)} sample ids appear more than once, e.g. {dupes[:3]}")
    parts = data["partitions"].tolist()
    if unknown := set(parts) - set(PARTITIONS):
        raise ValueError(f"unknown partitions: {sorted(unknown)}")
    labels = data["labels"].tolist()
    for p in ("train", "val"):
        seen = {l for l, q in zip(labels, parts) if q == p}
        if not seen:
            raise ValueError(f"no {p!r} rows")
        if missing := [c for c in classes if c not in seen]:
            raise ValueError(f"{p} rows do not cover every class; missing {missing}")
    for k, what in (("patient_ids", "patients"), ("group_ids", "duplicate groups")):
        if data.get(k) is None:
            continue
        where: dict[str, set] = {}
        for g, q in zip(data[k].tolist(), parts):
            if g and q != "unassigned":
                where.setdefault(g, set()).add(q)
        if spanning := sorted(g for g, qs in where.items() if len(qs) > 1):
            raise ValueError(f"{len(spanning)} {what} span more than one partition, e.g. {spanning[:3]}")


def _auc(y, probs, n_classes):
    from sklearn.metrics import roc_auc_score

    return roc_auc_score(y, probs[:, 1]) if n_classes == 2 else roc_auc_score(y, probs, multi_class="ovr", average="macro")


def train_feature_head(data: dict[str, Any], *, c_grid=C_GRID, teacher_weight: float = 0.0) -> HeadModel:
    """`data`: features (N x D), labels, partitions, sample_ids, optional patient_ids and group_ids, ordered classes, encoder ref.

    `validate_head_inputs` runs first, so leaking or malformed inputs are refused before any fit.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    if teacher_weight:
        raise NotImplementedError("distillation needs a reviewed teacher and permission; not implemented")
    validate_head_inputs(data)
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
