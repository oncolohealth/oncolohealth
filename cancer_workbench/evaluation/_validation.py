"""Input checks for optional-ML evaluation. NumPy is imported only on use."""
from __future__ import annotations

import math
import numbers


def finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def bootstrap_options(n_boot, seed) -> None:
    positive_int(n_boot, "n_boot")
    if isinstance(seed, bool) or not isinstance(seed, numbers.Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")


def labels(y_true, n_classes: int):
    import numpy as np

    y = np.asarray(y_true)
    if y.ndim != 1 or not len(y) or y.dtype.kind not in "iuf":
        raise ValueError("labels must be a nonempty one-dimensional numeric vector")
    if not np.isfinite(y).all() or not np.equal(y, np.floor(y)).all() or (y < 0).any() or (y >= n_classes).any():
        raise ValueError("labels must be integer class indices within the declared class order")
    return y.astype(int)


def probabilities(values, n: int, n_classes: int | None = None):
    import numpy as np

    p = np.asarray(values)
    shape = (n,) if n_classes is None else (n, n_classes)
    if p.shape != shape or p.dtype.kind not in "iuf":
        raise ValueError(f"probabilities must be numeric with shape {shape}")
    p = p.astype(float)
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("probabilities must be finite and within [0, 1]")
    if n_classes is not None and not np.allclose(p.sum(axis=1), 1, rtol=0, atol=1e-6):
        raise ValueError("each probability row must sum to 1 within 1e-6")
    return p


def binary_inputs(y_true, scores):
    y = labels(y_true, 2)
    return y, probabilities(scores, len(y))


def groups(group_ids, n: int):
    if group_ids is None:
        return None
    if isinstance(group_ids, (str, bytes)):
        raise ValueError("group_ids must be a sequence of identifiers, not a string")
    try:
        values = list(group_ids)
    except TypeError:
        raise ValueError("group_ids must be a sequence of identifiers") from None
    if len(values) != n or any(not isinstance(g, str) or not g.strip() or g != g.strip() for g in values):
        raise ValueError("group_ids must align with every row and contain nonempty declared string identifiers")
    return values
