"""Small, standard-library evidence summaries for verified local specialist profiles.

Callers must first validate artifact/implementation identities through
``runtime.profile``. Passing a manifest hash here records that identity; this
module does not read weights or promote an unverified candidate. Saved runtime
observations describe execution attempts and selected-input agreement, which
are deliberately separate from a model's recorded test-set metrics.
"""
from __future__ import annotations

import math
import re
from typing import Iterable


_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_STATUSES = {"ok": "completed", "failed": "failed", "rejected": "refused", "refused": "refused"}


def _count(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(name + " must be a nonnegative integer.")
    return value


def _rate(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(name + " must be a finite rate between zero and one.")
    return float(value)


def _ordered_classes(model: dict) -> list[str]:
    classes = model.get("classes", [])
    if (not isinstance(classes, list) or not classes or
            any(not isinstance(c, str) or not c.strip() for c in classes) or len(set(classes)) != len(classes)):
        raise ValueError("Evidence requires unique declared output classes/regions.")
    return list(classes)


def _counts(training: dict) -> dict[str, int]:
    source = training.get("counts") or {}
    if not isinstance(source, dict):
        raise ValueError("Training partition counts must be an object.")
    return {key: _count(source[key], key + " count") for key in ("train", "val", "test") if key in source}


def _classification_metrics(test: dict, classes: list[str], counts: dict) -> dict:
    n = _count(test.get("n"), "test n")
    if n == 0:
        raise ValueError("An evaluated classification report needs a nonempty test set.")
    if "test" in counts and counts["test"] != n:
        raise ValueError("Test denominator disagrees with the recorded partition count.")
    if "classes" in test and test["classes"] != classes:
        raise ValueError("Test class order differs from the verified model's class order.")
    metrics = {}
    for key in ("accuracy", "balanced_accuracy"):
        if key in test:
            metrics[key] = _rate(test[key], key)
    auc_key = next((key for key in ("macro_roc_auc", "macro_ovr_or_binary_roc_auc", "roc_auc") if key in test), None)
    if auc_key:
        metrics["roc_auc"] = _rate(test[auc_key], auc_key)
        metrics["roc_auc_definition"] = "binary" if len(classes) == 2 else "macro one-vs-rest"
        if len(classes) == 2:
            metrics["roc_auc_positive_class"] = classes[1]
    # No confidence interval is manufactured from these finite point estimates.
    intervals = {}
    for source, output in (("balanced_accuracy_ci95", "balanced_accuracy"), ("macro_roc_auc_ci95", "roc_auc")):
        if source in test:
            interval = test[source]
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                raise ValueError("Recorded confidence interval must have two bounds.")
            lo, hi = (_rate(v, source) for v in interval)
            if lo > hi:
                raise ValueError("Recorded confidence interval bounds are reversed.")
            intervals[output] = [lo, hi]
    matrix = test.get("confusion_rows_true_columns_pred")
    if matrix is None and isinstance(test.get("confusion"), dict):
        confusion = test["confusion"]
        if confusion.get("labels", classes) != classes:
            raise ValueError("Confusion-matrix class order differs from the model.")
        matrix = confusion.get("rows_true_cols_pred")
    result = {"n": n, "metrics": metrics, "per_class": {}, "confusion": None}
    if intervals:
        result["recorded_ci95"] = intervals
        result["ci_method"] = test.get("ci_method", "Method not recorded in this manifest.")
    if matrix is None:
        return result
    if (not isinstance(matrix, list) or len(matrix) != len(classes) or
            any(not isinstance(row, list) or len(row) != len(classes) for row in matrix)):
        raise ValueError("Confusion matrix must match the declared class order.")
    matrix = [[_count(v, "confusion count") for v in row] for row in matrix]
    if sum(map(sum, matrix)) != n:
        raise ValueError("Confusion-matrix denominator differs from test n.")
    correct = sum(matrix[i][i] for i in range(len(classes)))
    if "accuracy" in metrics and not math.isclose(metrics["accuracy"], correct / n, abs_tol=1e-6):
        raise ValueError("Recorded accuracy disagrees with the confusion matrix.")
    metrics.setdefault("accuracy", correct / n)
    metrics["correct"] = correct
    recalls = []
    for i, name in enumerate(classes):
        support, tp = sum(matrix[i]), matrix[i][i]
        entry = {"support": support, "true_positive": tp, "false_negative": support - tp,
                 "recall": tp / support if support else None}
        if support:
            recalls.append(tp / support)
        if len(classes) == 2:
            negative_support = n - support
            fp = sum(matrix[j][i] for j in range(len(classes)) if j != i)
            tn = negative_support - fp
            entry.update(negative_support=negative_support, true_negative=tn, false_positive=fp,
                         specificity=tn / negative_support if negative_support else None)
        result["per_class"][name] = entry
    balanced = sum(recalls) / len(recalls) if recalls else None
    if balanced is not None:
        if "balanced_accuracy" in metrics and not math.isclose(metrics["balanced_accuracy"], balanced, abs_tol=1e-6):
            raise ValueError("Recorded balanced accuracy disagrees with the confusion matrix.")
        metrics.setdefault("balanced_accuracy", balanced)
    result["confusion"] = {"class_order": classes, "rows_true_columns_pred": matrix}
    return result


def _rationale(model: dict) -> dict:
    backend = model.get("backend")
    common = {"morphology_explanation_available": False,
              "limit": "No measured semantic feature attribution is produced; do not invent visual findings or causal clinical explanations."}
    if backend == "pixels":
        return {**common, "type": "pixel_class_score",
                "method": "Declared pixel/voxel preprocessing followed by a fitted class-balanced logistic-regression head.",
                "decision_basis": "The reported class has the highest observed uncalibrated class score; stored coefficients are not a measured morphology explanation."}
    if backend in ("btxrd", "neural"):
        return {**common, "type": "encoder_head_class_score",
                "method": "Frozen ResNet-50 image features followed by the fitted three-class head.",
                "decision_basis": "Highest observed class score; no lesion-localization or morphology-attribution result is computed."}
    if backend == "mri":
        return {**common, "type": "segmentation_output",
                "decision_basis": "Actual thresholded regional masks and their derived overlay/voxel counts; this is not a classifier probability or a narrative morphology assessment."}
    if backend == "ct":
        return {**common, "type": "detection_output",
                "decision_basis": "Actual candidate nodule boxes and detector scores after recorded selection/NMS; these are not cancer probabilities or a malignancy rationale."}
    return {**common, "type": "unavailable", "decision_basis": "No measured explanation method is recorded for this backend."}


def evidence_for(model: dict, manifest_sha256: str) -> dict:
    """Summarize an already-verified full manifest, without loading/inferencing.

    ``model`` is the dictionary returned by ``runtime.profile``; the supplied
    SHA-256 must identify the actual manifest bytes measured by its caller.
    An unverified candidate or internally inconsistent denominator is refused.
    """
    if not isinstance(model, dict) or model.get("state") != "verified":
        raise ValueError("Evidence requires an artifact-verified profile; candidates cannot be promoted by a summary.")
    if not isinstance(model.get("id"), str) or not model["id"]:
        raise ValueError("Evidence requires a model identity.")
    if not isinstance(manifest_sha256, str) or not _SHA256.fullmatch(manifest_sha256):
        raise ValueError("Evidence requires the measured manifest SHA-256.")
    classes = _ordered_classes(model)
    training = model.get("training", {})
    if not isinstance(training, dict):
        raise ValueError("Training evidence must be an object.")
    backend = model.get("backend")
    limits = [str(value) for value in model.get("limitations", [])]
    split = training.get("source_split") or training.get("grouping")
    if split:
        limits.insert(0, str(split))
    evaluation = {"scope": "not_evaluated", "method": training.get("method", "Not recorded"),
                  "dataset": training.get("dataset") or training.get("publisher_dataset") or
                             ("btxrd" if backend == "btxrd" else training.get("publisher_data")),
                  "counts": _counts(training), "class_order": classes, "n": None, "metrics": {},
                  "per_class": {}, "confusion": None, "split_limits": limits,
                  "independent_patient_evaluation": False, "medical_validation": False}
    if backend in ("pixels", "btxrd", "neural"):
        test = training.get("test", training.get("test_metrics"))
        if test:
            if not isinstance(test, dict):
                raise ValueError("Recorded test metrics must be an object.")
            evaluation.update(_classification_metrics(test, classes, evaluation["counts"]))
            evaluation["scope"] = "local_sample_level_test"
            evaluation["evaluation_unit"] = "image_or_patch; patient/lesion independence is not established"
        else:
            limits.insert(0, "No test-set metrics are recorded for this verified artifact.")
    elif backend == "mri":
        evaluation["scope"] = "potentially_overlapping_demonstration"
        evaluation["evaluation_unit"] = "demonstration volume; not an independent test cohort"
    elif backend == "ct":
        evaluation["scope"] = "publisher_validation_demonstration"
        evaluation["evaluation_unit"] = "publisher-validation scan; not an independent test cohort"
        if training.get("demo_partition"):
            limits.insert(0, str(training["demo_partition"]))
    return {"model_id": model["id"], "manifest_sha256": manifest_sha256.lower(),
            "evaluation": evaluation, "rationale": _rationale(model)}


def _attempts(observations: Iterable[dict]) -> dict:
    counts = {"attempts": 0, "completed": 0, "failed": 0, "refused": 0, "other_status": 0,
              "synthetic_excluded": 0, "unmatched_model_records": 0}
    comparisons = {"classification_compared": 0, "classification_matched": 0, "classification_disagreed": 0,
                   "segmentation_compared": 0, "detection_compared": 0,
                   "meaning": "Selected-input reference agreement is separate from test-set accuracy and may include repeated, validation or overlapping cases."}
    failures = []
    seen = set()
    for row in observations:
        if not isinstance(row, dict):
            counts["other_status"] += 1
            counts["attempts"] += 1
            continue
        # Each saved observation ID counts once, even if a caller supplied it twice.
        observation_id = row.get("id")
        if isinstance(observation_id, str) and observation_id:
            if observation_id in seen:
                continue
            seen.add(observation_id)
        if row.get("synthetic") is True:
            counts["synthetic_excluded"] += 1
            continue
        counts["attempts"] += 1
        status = _STATUSES.get(row.get("status"), "other_status")
        counts[status] += 1
        if row.get("error") or row.get("errors"):
            failures.append({"observation_id": observation_id,
                             "status": row.get("status"), "error": row.get("error", row.get("errors"))})
        if status != "completed" or not isinstance(row.get("comparison"), dict):
            continue
        comparison = row["comparison"]
        if row.get("kind") == "segmentation" or "segmentation" in row:
            comparisons["segmentation_compared"] += 1
        elif row.get("kind") == "detection" or "detection" in row:
            comparisons["detection_compared"] += 1
        elif type(comparison.get("matches")) is bool:
            comparisons["classification_compared"] += 1
            key = "classification_matched" if comparison["matches"] else "classification_disagreed"
            comparisons[key] += 1
    return {"execution": counts, "reference_agreement": comparisons, "recent_failures": failures[-5:],
            "denominator_note": "Execution attempts count saved observation IDs, not patients or independent test examples. Recorded failed refusals stay failed; refusal counts require an explicit rejected/refused status."}


def scoreboard(profiles: Iterable[dict], observations: Iterable[dict]) -> dict:
    """Join verified evidence and saved execution records without mixing scores.

    Profiles: ``[{"model": full_verified_manifest, "manifest_sha256": sha}, ...]``.
    An unavailable profile may instead be ``{"id": id, "error": reason}``.
    Observations: the actual top-level saved runtime receipt dictionaries.
    Unknown/candidate model records remain visible and count in totals, but
    never acquire evaluated accuracy merely because an inference was tried.
    """
    observations = list(observations)
    grouped = {}
    unmatched = []
    for row in observations:
        if not isinstance(row, dict) or not isinstance(row.get("model_id"), str) or not row["model_id"]:
            unmatched.append(row)
            continue
        grouped.setdefault(row["model_id"], []).append(row)
    rows = []
    seen = set()
    for entry in profiles:
        model = entry.get("model", {}) if isinstance(entry, dict) else {}
        model_id = model.get("id") or (entry.get("id") if isinstance(entry, dict) else None)
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            raise ValueError("Scoreboard profiles require distinct model IDs.")
        seen.add(model_id)
        row = {"model_id": model_id, "name": model.get("name", model_id), "available": False}
        try:
            if entry.get("error"):
                raise ValueError(str(entry["error"]))
            row["evidence"] = evidence_for(model, entry.get("manifest_sha256"))
            row["available"] = True
        except (ValueError, TypeError) as exc:
            row["blocker"] = str(exc)
        row.update(_attempts(grouped.pop(model_id, [])))
        rows.append(row)
    for model_id in sorted(grouped):
        rows.append({"model_id": model_id, "name": model_id, "available": False,
                     "blocker": "No currently verified profile supplied; candidate/missing artifact remains unavailable.",
                     **_attempts(grouped[model_id])})
    totals = _attempts(observations)
    totals["execution"]["unmatched_model_records"] = len(unmatched)
    return {"models": rows, "totals": totals,
            "meaning": "Test-set metrics, selected-input reference agreement and execution reliability have different denominators and must not be combined into one accuracy score.",
            "medical_validation": False}
