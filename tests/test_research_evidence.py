"""Evidence semantics/denominator checks; all reports below are synthetic fixtures."""
import copy
import json
import unittest

from cancer_workbench.research.evidence import evidence_for, scoreboard


SHA = "a" * 64


def classification_fixture():
    return {"id": "fixture-breast", "name": "Synthetic evidence fixture", "state": "verified", "backend": "pixels",
            "classes": ["malignant", "normal-benign"], "limitations": ["Patient identities are not supplied."],
            "training": {"method": "Synthetic classifier evidence fixture", "dataset": "synthetic",
                         "counts": {"train": 346, "val": 78, "test": 156},
                         "source_split": "Synthetic sample-level split with no patient map",
                         "test": {"n": 156, "accuracy": 119 / 156,
                                  "balanced_accuracy": (28 / 42 + 91 / 114) / 2,
                                  "macro_ovr_or_binary_roc_auc": .833,
                                  "confusion_rows_true_columns_pred": [[28, 14], [23, 91]]}}}


class EvidenceExtractionTests(unittest.TestCase):
    def test_binary_class_order_denominators_and_real_rates(self):
        model = classification_fixture()
        result = evidence_for(model, SHA)
        evaluation = result["evaluation"]
        self.assertEqual(evaluation["scope"], "local_sample_level_test")
        self.assertEqual(evaluation["n"], 156)
        self.assertEqual(evaluation["metrics"]["correct"], 119)
        self.assertAlmostEqual(evaluation["per_class"]["malignant"]["recall"], 28 / 42)
        self.assertEqual(evaluation["per_class"]["malignant"]["support"], 42)
        self.assertAlmostEqual(evaluation["per_class"]["malignant"]["specificity"], 91 / 114)
        self.assertEqual(evaluation["per_class"]["malignant"]["negative_support"], 114)
        self.assertEqual(evaluation["metrics"]["roc_auc_positive_class"], "normal-benign")
        self.assertFalse(evaluation["independent_patient_evaluation"])
        self.assertFalse(evaluation["medical_validation"])
        self.assertNotIn("recorded_ci95", evaluation)

    def test_swapping_class_order_and_confusion_keeps_each_class_meaning(self):
        model = classification_fixture()
        model["classes"] = ["normal-benign", "malignant"]
        model["training"]["test"]["confusion_rows_true_columns_pred"] = [[91, 23], [14, 28]]
        result = evidence_for(model, SHA)["evaluation"]
        self.assertAlmostEqual(result["per_class"]["malignant"]["recall"], 28 / 42)
        self.assertAlmostEqual(result["per_class"]["malignant"]["specificity"], 91 / 114)
        self.assertEqual(result["metrics"]["roc_auc_positive_class"], "malignant")

    def test_multiclass_result_uses_declared_matrix_order_without_binary_specificity(self):
        model = classification_fixture()
        model.update(backend="btxrd", classes=["normal", "benign", "malignant"])
        model["training"]["counts"]["test"] = 6
        model["training"]["test"] = {"n": 6, "classes": model["classes"], "macro_roc_auc": .8,
            "confusion": {"labels": model["classes"], "rows_true_cols_pred": [[2, 0, 0], [0, 1, 1], [1, 0, 1]]}}
        result = evidence_for(model, SHA)["evaluation"]
        self.assertEqual(result["per_class"]["normal"]["recall"], 1.)
        self.assertEqual(result["per_class"]["malignant"]["recall"], .5)
        self.assertNotIn("specificity", result["per_class"]["malignant"])
        self.assertEqual(result["metrics"]["roc_auc_definition"], "macro one-vs-rest")

    def test_conflicting_denominators_class_order_and_accuracy_are_refused(self):
        for change in ("denominator", "class_order", "accuracy", "matrix_shape"):
            with self.subTest(change=change):
                model = classification_fixture()
                test = model["training"]["test"]
                if change == "denominator":
                    test["n"] = 155
                elif change == "class_order":
                    test["classes"] = list(reversed(model["classes"]))
                elif change == "accuracy":
                    test["accuracy"] = .99
                else:
                    test["confusion_rows_true_columns_pred"] = [[28, 14]]
                with self.assertRaises(ValueError):
                    evidence_for(model, SHA)

    def test_no_false_metrics_for_untrained_candidates_or_missing_test(self):
        model = classification_fixture()
        model["state"] = "candidate"
        with self.assertRaisesRegex(ValueError, "artifact-verified"):
            evidence_for(model, SHA)
        model["state"] = "verified"
        model["training"].pop("test")
        result = evidence_for(model, SHA)["evaluation"]
        self.assertEqual(result["scope"], "not_evaluated")
        self.assertEqual(result["metrics"], {})
        self.assertIsNone(result["n"])

    def test_mri_and_ct_never_promote_demonstration_into_evaluated_metrics(self):
        for backend, scope, kind in [("mri", "potentially_overlapping_demonstration", "segmentation_output"),
                                      ("ct", "publisher_validation_demonstration", "detection_output")]:
            with self.subTest(backend=backend):
                model = classification_fixture()
                model["backend"] = backend
                # Even a stray classifier-like field cannot promote this demonstration.
                result = evidence_for(model, SHA)
                self.assertEqual(result["evaluation"]["scope"], scope)
                self.assertEqual(result["evaluation"]["metrics"], {})
                self.assertIsNone(result["evaluation"]["n"])
                self.assertEqual(result["rationale"]["type"], kind)

    def test_zero_support_is_explicit_and_no_rate_is_divided_by_zero(self):
        model = classification_fixture()
        model["training"]["counts"]["test"] = 3
        model["training"]["test"] = {"n": 3, "confusion_rows_true_columns_pred": [[0, 0], [0, 3]]}
        evaluation = evidence_for(model, SHA)["evaluation"]
        self.assertIsNone(evaluation["per_class"]["malignant"]["recall"])
        self.assertIsNone(evaluation["per_class"]["normal-benign"]["specificity"])

    def test_only_recorded_intervals_are_exposed_with_their_limits(self):
        model = classification_fixture()
        model["training"]["test"].update(balanced_accuracy_ci95=[.6, .8], ci_method="Synthetic image bootstrap, not patient groups")
        evaluation = evidence_for(model, SHA)["evaluation"]
        self.assertEqual(evaluation["recorded_ci95"], {"balanced_accuracy": [.6, .8]})
        self.assertIn("not patient", evaluation["ci_method"])

    def test_neural_task_head_keeps_actual_classes_without_assuming_three(self):
        model = classification_fixture()
        model['backend'] = 'neural'
        result = evidence_for(model, SHA)
        self.assertEqual(result['evaluation']['class_order'], ['malignant', 'normal-benign'])
        self.assertEqual(result['rationale']['type'], 'encoder_head_class_score')
        self.assertNotIn('three-class', result['rationale']['method'])
        self.assertFalse(result['rationale']['morphology_explanation_available'])

    def test_source_objects_are_unchanged_and_morphology_is_not_invented(self):
        model = classification_fixture(); before = copy.deepcopy(model)
        result = evidence_for(model, SHA)
        self.assertEqual(model, before)
        self.assertEqual(result["rationale"]["type"], "pixel_class_score")
        self.assertFalse(result["rationale"]["morphology_explanation_available"])
        json.dumps(result, allow_nan=False)

    def test_nonfinite_boolean_or_invalid_identity_evidence_is_refused(self):
        for bad in [float("nan"), float("inf"), True, -0.1, 1.1]:
            model = classification_fixture(); model["training"]["test"]["accuracy"] = bad
            with self.assertRaises(ValueError):
                evidence_for(model, SHA)
        with self.assertRaisesRegex(ValueError, "manifest SHA"):
            evidence_for(classification_fixture(), "declared-but-not-measured")


class ScoreboardDenominatorTests(unittest.TestCase):
    def test_failures_refusals_duplicates_and_candidate_attempts_stay_separate(self):
        model = classification_fixture()
        observations = [
            {"id": "ok1", "model_id": model["id"], "status": "ok", "kind": "classification", "comparison": {"matches": True}},
            {"id": "ok2", "model_id": model["id"], "status": "ok", "comparison": {"matches": False}},
            {"id": "fail", "model_id": model["id"], "status": "failed", "error": "actual failure"},
            {"id": "refuse", "model_id": model["id"], "status": "rejected", "errors": ["ineligible input"]},
            {"id": "ok1", "model_id": model["id"], "status": "ok", "comparison": {"matches": True}},
            {"id": "candidate1", "model_id": "unverified-candidate", "status": "failed", "error": "missing weight"},
            {"id": "fake", "model_id": model["id"], "status": "ok", "synthetic": True},
        ]
        board = scoreboard([{"model": model, "manifest_sha256": SHA}], observations)
        row = board["models"][0]
        self.assertEqual(row["execution"]["attempts"], 4)
        self.assertEqual(row["execution"]["completed"], 2)
        self.assertEqual(row["execution"]["failed"], 1)
        self.assertEqual(row["execution"]["refused"], 1)
        self.assertEqual(row["reference_agreement"]["classification_compared"], 2)
        self.assertEqual(row["reference_agreement"]["classification_matched"], 1)
        self.assertEqual(row["evidence"]["evaluation"]["n"], 156)
        self.assertEqual(row["evidence"]["evaluation"]["metrics"]["correct"], 119)
        candidate = next(r for r in board["models"] if r["model_id"] == "unverified-candidate")
        self.assertFalse(candidate["available"])
        self.assertNotIn("evidence", candidate)
        self.assertEqual(candidate["execution"]["failed"], 1)
        self.assertEqual(board["totals"]["execution"]["attempts"], 5)

    def test_recorded_failed_refusal_is_not_reclassified_by_error_words(self):
        board = scoreboard([], [{"id": "1", "model_id": "missing", "status": "failed", "error": "refused because unknown"}])
        self.assertEqual(board["totals"]["execution"]["failed"], 1)
        self.assertEqual(board["totals"]["execution"]["refused"], 0)

    def test_segmentation_and_detection_comparisons_never_enter_classification_accuracy(self):
        observations = [
            {"id": "m", "model_id": "mri", "status": "ok", "kind": "segmentation", "comparison": {"regions": {}}},
            {"id": "c", "model_id": "ct", "status": "ok", "kind": "detection", "comparison": {"agreement": []}},
            {"id": "f", "model_id": "ct", "status": "failed", "comparison": {"matches": True}},
        ]
        agreement = scoreboard([], observations)["totals"]["reference_agreement"]
        self.assertEqual(agreement["classification_compared"], 0)
        self.assertEqual(agreement["segmentation_compared"], 1)
        self.assertEqual(agreement["detection_compared"], 1)

    def test_unavailable_profiles_and_unmatched_observations_remain_visible(self):
        board = scoreboard([{"id": "broken-profile", "error": "checksum mismatch"}], [{"status": "failed", "error": "missing model id"}])
        self.assertFalse(board["models"][0]["available"])
        self.assertIn("checksum mismatch", board["models"][0]["blocker"])
        self.assertEqual(board["totals"]["execution"]["unmatched_model_records"], 1)
        self.assertEqual(board["totals"]["execution"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
