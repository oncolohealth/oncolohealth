"""SYNTHETIC metric fixtures. No medical data, model execution or performance evidence."""
import importlib.util
import json
import unittest

from cancer_workbench.experiments.btxrd_baseline import summary

HAS_ML = all(importlib.util.find_spec(m) for m in ("numpy", "sklearn"))


@unittest.skipUnless(HAS_ML, "needs numpy and scikit-learn")
class ValidationTests(unittest.TestCase):
    def setUp(self):
        from cancer_workbench.evaluation.metrics import binary_report, calibration, multiclass_report
        from cancer_workbench.evaluation.thresholds import choose_threshold

        self.binary, self.calibration, self.multi, self.threshold = binary_report, calibration, multiclass_report, choose_threshold

    def report(self, y=(0, 1, 0, 1), s=(0.1, 0.9, 0.2, 0.8), **kwargs):
        return self.binary(y, s, 0.5, n_boot=40, **kwargs)

    def test_misaligned_empty_and_nondimensional_inputs_refused(self):
        for y, scores in (([], []), ([0, 1], [0.2]), ([[0, 1]], [0.2, 0.8]), ([0, 1], [[0.2], [0.8]])):
            for function in (lambda: self.report(y, scores), lambda: self.calibration(y, scores), lambda: self.threshold(y, scores)):
                with self.subTest(y=y, scores=scores), self.assertRaises(ValueError):
                    function()

    def test_invalid_labels_refused(self):
        for y in ([0, 2], [0, -1], [0, 0.5], [0, float("nan")], ["0", "1"], [False, True]):
            with self.subTest(y=y), self.assertRaises(ValueError):
                self.report(y, [0.2, 0.8])

    def test_nonfinite_out_of_range_and_nonnumeric_scores_refused(self):
        for scores in ([0.2, float("nan")], [float("inf"), 0.8], [-0.1, 0.8], [0.1, 1.1], ["0.2", "0.8"]):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                self.report([0, 1], scores)

    def test_threshold_must_be_finite(self):
        for threshold in (float("nan"), float("inf"), True, "0.5"):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.binary([0, 1], [0.2, 0.8], threshold, n_boot=20)

    def test_group_ids_require_complete_aligned_identifiers(self):
        for gids in (["a"], ["a", "", "c", "d"], ["a", None, "c", "d"], [1, 2, 3, 4], "abcd", 7):
            with self.subTest(gids=gids), self.assertRaises(ValueError):
                self.report(group_ids=gids)

    def test_bootstrap_options_are_checked(self):
        for kwargs in ({"n_boot": 0}, {"n_boot": True}, {"n_boot": 1.5}, {"seed": -1}, {"seed": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.binary([0, 1], [0.2, 0.8], 0.5, **kwargs)

    def test_single_class_binary_is_explicit_null_and_strict_json(self):
        for label in (0, 1):
            report = self.report([label] * 4, [0.1, 0.4, 0.6, 0.9])
            self.assertIsNone(report["roc_auc"])
            self.assertIsNone(report["pr_auc"])
            self.assertEqual(report["bootstrap"]["roc_auc"]["invalid_missing_class"], 40)
            self.assertTrue(report["warnings"])
            json.dumps(report, allow_nan=False)

    def test_undefined_threshold_denominators_are_null(self):
        report = self.report([0, 0], [0.1, 0.2])
        self.assertIsNone(report["sensitivity"])
        self.assertIsNone(report["ppv"])
        self.assertEqual(report["specificity"], 1)

    def test_missing_class_draws_are_counted_and_ci_withheld(self):
        report = self.report([0, 1], [0.2, 0.8], group_ids=["a", "b"])
        bootstrap = report["bootstrap"]["roc_auc"]
        self.assertEqual(bootstrap["valid"] + bootstrap["invalid_missing_class"] + bootstrap["invalid_nonfinite"], 40)
        self.assertGreater(bootstrap["invalid_missing_class"], 0)
        self.assertIsNone(report["roc_auc_ci95"])

    def test_grouped_resampling_retains_all_views(self):
        report = self.report(group_ids=["a", "a", "b", "b"])
        bootstrap = report["bootstrap"]["roc_auc"]
        self.assertEqual(bootstrap["unit"], "patient")
        self.assertEqual(bootstrap["n_groups"], 2)
        self.assertEqual(bootstrap["valid"], 40)
        self.assertEqual(report["roc_auc_ci95"], [1, 1])

    def test_one_patient_never_gets_an_interval(self):
        report = self.report(group_ids=["a"] * 4)
        self.assertEqual(report["bootstrap"]["roc_auc"]["valid"], 40)
        self.assertIsNone(report["roc_auc_ci95"])

    def test_nonfinite_bootstrap_statistics_are_counted(self):
        import numpy as np
        from cancer_workbench.evaluation.metrics import _ci

        result = _ci(lambda y, s: float("nan"), np.array([0, 1, 0, 1]), np.array([0.1, 0.9, 0.2, 0.8]),
                     ["a", "a", "b", "b"], 20, 0, (0, 1))
        self.assertEqual(result["invalid_nonfinite"], 20)
        self.assertEqual(result["valid"], 0)
        self.assertIsNone(result["ci95"])
        json.dumps(result, allow_nan=False)

    def test_seeded_reports_reproduce_and_ap_is_named(self):
        self.assertEqual(self.report(seed=7), self.report(seed=7))
        self.assertEqual(self.report()["pr_auc_definition"], "non-interpolated average precision")

    def test_calibration_bins_account_for_boundary_scores(self):
        result = self.calibration([0, 0, 1, 1], [0, 0.5, 0.5, 1], n_bins=2)
        self.assertEqual(sum(b["n"] for b in result["bins"]), 4)
        self.assertEqual(result["ece"], 0)

    def test_invalid_calibration_bin_count_refused(self):
        for bins in (0, -1, 1.5, True):
            with self.subTest(bins=bins), self.assertRaises(ValueError):
                self.calibration([0, 1], [0.2, 0.8], bins)

    def test_missing_multiclass_support_is_explicit(self):
        report = self.multi([0, 1], [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]], ["a", "b", "c"], n_boot=20)
        self.assertIsNone(report["macro_roc_auc"])
        self.assertIsNone(report["balanced_accuracy"])
        self.assertIsNone(report["recall"]["c"])
        self.assertEqual(report["bootstrap"]["macro_roc_auc"]["invalid_missing_class"], 20)
        json.dumps(report, allow_nan=False)

    def test_multiclass_probabilities_and_class_order_validated(self):
        cases = [(["a", "a", "c"], [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]]),
                 (["a", "b", "c"], [[0.8, 0.1], [0.1, 0.8]]),
                 (["a", "b", "c"], [[0.8, 0.1, 0.4], [0.1, 0.8, 0.1]]),
                 (["a", "b", "c"], [[0.8, 0.1, float("nan")], [0.1, 0.8, 0.1]])]
        for classes, probs in cases:
            with self.subTest(classes=classes, probs=probs), self.assertRaises(ValueError):
                self.multi([0, 1], probs, classes, n_boot=20)

    def test_multiclass_grouped_report_retains_all_classes(self):
        report = self.multi([0, 1, 2, 0, 1, 2], [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]] * 2,
                            ["a", "b", "c"], group_ids=["p1"] * 3 + ["p2"] * 3, n_boot=20)
        self.assertEqual(report["macro_roc_auc"], 1)
        self.assertEqual(report["macro_roc_auc_ci95"], [1, 1])
        self.assertEqual(report["bootstrap"]["balanced_accuracy"]["valid"], 20)

    def test_threshold_requires_two_development_classes(self):
        with self.assertRaisesRegex(ValueError, "both classes"):
            self.threshold([1, 1], [0.2, 0.8])

    def test_threshold_target_and_rule_are_validated(self):
        for rule in ("sensitivity>=nan", "sensitivity>=inf", "sensitivity>=-0.1", "sensitivity>=1.1", "sensitivity>=bad", "bogus", None):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                self.threshold([0, 1], [0.2, 0.8], rule)

    def test_no_positive_threshold_preserves_roc_point_when_score_is_one(self):
        threshold = self.threshold([0, 1], [1.0, 0.0])
        self.assertGreater(threshold, 1)
        report = self.binary([0, 1], [1.0, 0.0], threshold, n_boot=20)
        self.assertEqual(report["confusion"], {"tp": 0, "fn": 1, "tn": 1, "fp": 0})
        json.dumps(report, allow_nan=False)

    def test_requested_development_sensitivity_is_attained_with_ties(self):
        y, scores = [0, 1, 0, 1], [0.1, 0.8, 0.8, 0.8]
        threshold = self.threshold(y, scores, "sensitivity>=1")
        self.assertEqual(threshold, 0.8)
        self.assertEqual(self.binary(y, scores, threshold, n_boot=20)["sensitivity"], 1)


class SummaryTests(unittest.TestCase):
    def test_undefined_binary_metrics_render_without_failure(self):
        result = {"protocol": "SYNTHETIC", "endpoint": "SYNTHETIC", "encoder": "SYNTHETIC", "test": {
            "n": 2, "roc_auc": None, "roc_auc_ci95": None, "sensitivity": None, "specificity": 1, "positive_class": "SYNTHETIC"}}
        self.assertIn("undefined", summary([result]))

    def test_undefined_multiclass_metrics_render_without_failure(self):
        result = {"protocol": "SYNTHETIC", "endpoint": "SYNTHETIC", "encoder": "SYNTHETIC", "test": {
            "n": 2, "macro_roc_auc": None, "macro_roc_auc_ci95": None, "balanced_accuracy": None,
            "recall": {"a": 1, "b": 1, "c": None}}}
        self.assertIn("undefined", summary([result]))


if __name__ == "__main__":
    unittest.main()
