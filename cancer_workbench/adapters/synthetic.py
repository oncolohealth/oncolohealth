"""SYNTHETIC adapter for software tests and demos. Its outputs are not model predictions."""
from __future__ import annotations

from typing import Any


class SyntheticThresholdAdapter:
    """Pretends to classify a scalar `signal` in [0, 1]. Exists to exercise plumbing only."""

    id = "synthetic-threshold"
    synthetic = True

    def __init__(self, fail: bool = False):
        self.fail = fail

    def validate(self, inputs: dict[str, Any]) -> list[str]:
        sig = inputs.get("signal")
        if not isinstance(sig, (int, float)):
            return ["inputs.signal must be a number"]
        if not 0.0 <= sig <= 1.0:
            return ["inputs.signal must be within [0, 1]"]
        return []

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("synthetic adapter configured to fail")
        p = float(inputs["signal"])
        return {"labels": ["negative", "positive"], "scores": [1 - p, p], "note": "SYNTHETIC: not a model output"}


SYNTHETIC_MODEL_RECORD = {
    "id": "synthetic-threshold-model",
    "name": "Synthetic threshold model (test fixture)",
    "kind": "specialist",
    "tasks": ["synthetic_classification"],
    "modality": ["synthetic"],
    "anatomy": ["any"],
    "input": {"channels": 1, "spatial_dims": 0},
    "outputs": {"type": "probabilities", "labels": ["negative", "positive"]},
    "license": {"id": "n/a"},
    "access": "open",
    "evidence_state": "locally_reproduced",
    "inference_permission": "allowed",
    "adapter": "synthetic-threshold",
    "citation": "synthetic fixture",
    "acquisition": {"tier": "default", "fetcher": "none"},
}
