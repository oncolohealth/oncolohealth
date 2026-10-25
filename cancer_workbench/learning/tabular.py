"""Explicit-schema local tabular baseline; no network or automatic promotion.

Rows must already have reviewed patient grouping, labels, units and partitions.
This cannot manufacture a CBC prediction target from a resource catalog.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from itertools import islice
from pathlib import Path


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(csv_path: Path, schema: dict):
    import numpy as np
    from .heads import validate_head_inputs

    features = schema.get("features")
    if not isinstance(features, dict) or not features or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in features.items()):
        raise ValueError("features must map each numeric column to its explicit source unit.")
    target = schema.get("target")
    reserved = {"sample_id", "patient_id", "partition", target}
    if not isinstance(target, str) or target in {"sample_id", "patient_id", "partition"} or set(features) & reserved:
        raise ValueError("Target/identity/partition columns cannot be predictors.")
    for field in ("target_description", "label_reference", "split_reference", "source_url"):
        if not isinstance(schema.get(field), str) or not schema[field].strip():
            raise ValueError(f"A reviewed {field} is required; it is not inferred.")
    classes = schema.get("classes")
    if not isinstance(classes, list) or len(classes) < 2 or len(set(classes)) != len(classes):
        raise ValueError("Declare at least two unique class labels in output order.")
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV column names must be unique.")
        if not (set(features) | reserved) <= set(reader.fieldnames):
            raise ValueError("CSV lacks declared features, target or explicit identity/split columns.")
        rows = list(islice(reader, 100_001))
    if not rows or len(rows) > 100_000 or len(features) > 500:
        raise ValueError("Use 1–100,000 rows and at most 500 numeric features for this bounded baseline.")
    if any(not r["patient_id"].strip() for r in rows):
        raise ValueError("Every row needs a reviewed patient/group ID; never derive it from row order.")
    if any(r["partition"] not in {"train", "val", "test"} for r in rows):
        raise ValueError("Every row must have an explicit train, val or test partition.")
    # The same exact numeric profile and label cannot leak across partitions.
    signatures = {}
    for r in rows:
        values = tuple(float(r[k]) for k in features)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Missing/non-finite numeric values require an explicit reviewed policy.")
        key = values
        if key in signatures and signatures[key] != r["partition"]:
            raise ValueError("Duplicate numeric profile crosses partitions.")
        signatures[key] = r["partition"]
    identity = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
    data = {"features": np.array([[float(r[k]) for k in features] for r in rows]),
            "labels": np.array([r[target] for r in rows]), "classes": classes,
            "partitions": np.array([r["partition"] for r in rows]),
            "sample_ids": np.array([r["sample_id"] for r in rows]),
            "patient_ids": np.array([r["patient_id"] for r in rows]),
            "encoder": {"encoder_id": "explicit-numeric-columns", "revision": "tabular-v1", "preprocessing_hash": identity}}
    validate_head_inputs(data)
    if set(data["labels"][data["partitions"] == "test"].tolist()) != set(classes):
        raise ValueError("Reserved test rows must cover all declared classes.")
    return data


def fit(csv_path: Path, schema_path: Path, out: Path):
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
    from .heads import train_feature_head, evaluate_head, save_head, load_head
    import numpy as np

    out = Path(out)
    if out.exists():
        raise FileExistsError("Use a fresh candidate directory; existing artifacts are never overwritten.")
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))
    data = prepare(Path(csv_path), schema)
    # Existing shared head fitter fits normalization on train, chooses C on val.
    head = train_feature_head(data)
    test = evaluate_head(head, data, "test")
    out.mkdir(parents=True, exist_ok=False)
    save_head(head, out / "head.npz")
    restored = evaluate_head(load_head(out / "head.npz"), data, "test")
    if not np.allclose(test["probs"], restored["probs"], atol=1e-12):
        raise ValueError("Saved head did not reproduce reserved test predictions.")
    (out / "schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    pred = np.argmax(test["probs"], axis=1)
    report = {"state": "candidate_not_promoted", "method": "train-standardized class-balanced logistic regression; C selected on validation only",
              "input_sha256": _sha(csv_path), "schema_sha256": _sha(out / "schema.json"),
              "head_sha256": _sha(out / "head.npz"), "classes": head.classes,
              "counts": {p: int(sum(data["partitions"] == p)) for p in ("train", "val", "test")},
              "validation_auc": head.val_score, "selected_C": head.C,
              "test": {"accuracy": float(accuracy_score(test["y_true"], pred)),
                       "balanced_accuracy": float(balanced_accuracy_score(test["y_true"], pred)),
                       "confusion_rows_true_columns_pred": confusion_matrix(test["y_true"], pred, labels=list(range(len(head.classes)))).tolist()},
              "saved_reload_verified": True, "grouping": "Declared patient IDs were checked; their real identity and label validity still need source review.",
              "medical_validation": False, "scores_calibrated": False,
              "next": "Review source labels/units/grouping, compare baselines, reserve external evaluation and add a reviewed runtime adapter before app registration."}
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def predict_profile(artifact_dir: Path, values: dict, units: dict):
    import numpy as np
    from .heads import load_head

    root = Path(artifact_dir)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if _sha(root / "head.npz") != report["head_sha256"] or _sha(root / "schema.json") != report["schema_sha256"]:
        raise ValueError("Candidate artifact or schema changed after training.")
    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    if set(values) != set(schema["features"]) or units != schema["features"]:
        raise ValueError("Supply exactly the trained numeric features and units; no implicit unit conversions.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values.values()):
        raise ValueError("Profile values must be finite numbers.")
    head = load_head(root / "head.npz")
    x = np.array([[values[k] for k in schema["features"]]], dtype=float)
    scores = head.clf.predict_proba((x - head.mean) / head.scale)[0]
    return {"class": head.classes[int(scores.argmax())], "classes": head.classes, "scores": scores.tolist(),
            "state": "candidate_not_promoted", "medical_validation": False, "scores_calibrated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(fit(args.csv, args.schema, args.out), indent=2))


if __name__ == "__main__":
    main()
