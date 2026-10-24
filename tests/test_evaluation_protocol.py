"""SYNTHETIC scores/identifiers only. These tests say nothing about medical performance."""
import itertools
import unittest

from cancer_workbench.evaluation.aggregate import patient_level
from cancer_workbench.evaluation.comparison import paired_binary, ranking_metrics
from cancer_workbench.evaluation.leakage import check


def predictions(labels=(0, 1, 0, 1, 0, 1), scores=(0.1, 0.9, 0.2, 0.8, 0.3, 0.7)):
    return [{"sample_id": f"s{i}", "patient_id": f"p{i // 2}", "label": label, "score": score, "partition": "test"}
            for i, (label, score) in enumerate(zip(labels, scores))]


class AggregationTests(unittest.TestCase):
    def test_max_mean_counts_and_stable_membership(self):
        rows = predictions(labels=(0, 0, 1, 1), scores=(0.1, 0.3, 0.6, 0.8))
        self.assertEqual([r["score"] for r in patient_level(rows)], [0.3, 0.8])
        out = patient_level(list(reversed(rows)), "mean")
        self.assertAlmostEqual(out[0]["score"], 0.2)
        self.assertEqual(out[0]["sample_ids"], ["s0", "s1"])
        self.assertEqual(out[0]["n_images"], 2)
        self.assertEqual(rows[0]["score"], 0.1)

    def test_missing_patient_ids_never_fall_back_to_images(self):
        for patient in (None, "", " "):
            with self.subTest(patient=patient), self.assertRaises(ValueError):
                patient_level([dict(predictions()[0], patient_id=patient)])

    def test_conflicting_labels_require_adjudication(self):
        with self.assertRaisesRegex(ValueError, "conflicting labels"):
            patient_level(predictions())

    def test_cross_partition_patient_is_refused(self):
        rows = predictions(labels=(0, 0), scores=(0.1, 0.2))
        rows[1]["partition"] = "val"
        with self.assertRaisesRegex(ValueError, "spans partitions"):
            patient_level(rows)

    def test_invalid_predictions_and_duplicate_samples_are_refused(self):
        base = predictions()[0]
        for rows in ([], [base, base], [dict(base, score=float("nan"))], [dict(base, score=1.1)],
                     [dict(base, score=True)], [dict(base, label=2)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                patient_level(rows)
        with self.assertRaises(ValueError):
            patient_level([base], "median")


class LeakageTests(unittest.TestCase):
    TRAIN = [{"sample_id": "s1", "patient_id": "p1", "duplicate_group": "d1", "sha256": "abc",
              "dataset_id": "SYNTHETIC", "source": "SYNTHETIC-source"}]
    EVAL = [{"sample_id": "s2", "patient_id": "p2", "duplicate_group": "d2", "sha256": "def",
             "dataset_id": "SYNTHETIC", "source": "SYNTHETIC-source"}]

    def test_all_exact_cross_split_keys_are_checked(self):
        codes = {f["code"] for f in check(self.TRAIN, self.TRAIN, [])}
        self.assertTrue({f"{k}_overlap" for k in ("sample_id", "patient_id", "duplicate_group", "sha256")} <= codes)

    def test_shared_source_is_a_warning_not_case_leakage(self):
        findings = check(self.TRAIN, self.EVAL, [])
        shared = next(f for f in findings if f["code"] == "shared_source")
        self.assertEqual(shared["severity"], "warning")
        self.assertFalse(any(f["severity"] == "error" for f in findings))
        self.assertIn("pretraining_unresolved", {f["code"] for f in findings})

    def test_missing_patient_ids_and_empty_partitions_remain_visible(self):
        findings = check([], [dict(self.EVAL[0], patient_id="")], [])
        self.assertTrue({"missing_patient_id", "empty_partition"} <= {f["code"] for f in findings})

    def test_duplicate_ids_within_a_partition_are_errors(self):
        self.assertIn("duplicate_sample_id", {f["code"] for f in check(self.TRAIN * 2, self.EVAL, [])})

    def test_namespaces_prevent_false_pretraining_id_matches(self):
        refs = [{"id": "fixture", "citation": "SYNTHETIC", "coverage": "complete", "dataset_id": "OTHER",
                 "records": [{"sample_id": "s2", "patient_id": "p2"}]}]
        self.assertFalse(any(f["code"] == "pretraining_overlap" for f in check(self.TRAIN, self.EVAL, refs)))
        refs[0]["dataset_id"] = "SYNTHETIC"
        self.assertTrue(any(f["code"] == "pretraining_overlap" and f["severity"] == "error"
                            for f in check(self.TRAIN, self.EVAL, refs)))

    def test_pretraining_hash_match_works_without_dataset_namespace(self):
        refs = [{"id": "fixture", "citation": "SYNTHETIC", "coverage": "partial", "records": [{"sha256": "def"}]}]
        findings = check(self.TRAIN, self.EVAL, refs)
        self.assertTrue(any(f["code"] == "pretraining_overlap" and f["key"] == "sha256" for f in findings))
        self.assertIn("pretraining_unresolved", {f["code"] for f in findings})

    def test_unstructured_refs_never_become_a_no_overlap_conclusion(self):
        findings = check(self.TRAIN, self.EVAL, ["paper citation only"])
        self.assertIn("pretraining_unresolved", {f["code"] for f in findings})


class PairedComparisonTests(unittest.TestCase):
    def compare(self, a, b, **kwargs):
        return paired_binary(a, b, n_boot=100, min_valid=50, **kwargs)

    def test_known_tied_metrics(self):
        out = ranking_metrics(predictions(labels=(0, 1, 1), scores=(0.5, 0.5, 1.0)))
        self.assertEqual(out["roc_auc"], 0.75)
        self.assertAlmostEqual(out["average_precision"], (1 + 2 / 3) / 2)

    def test_metrics_against_independent_small_oracles(self):
        # 14 nondegenerate label vectors x 81 tied score vectors = 1,134
        # cases. AUC is explicit pair counting; AP is threshold integration.
        for labels in itertools.product((0, 1), repeat=4):
            if len(set(labels)) < 2:
                continue
            for scores in itertools.product((0.0, 0.5, 1.0), repeat=4):
                pairs = [(scores[p], scores[n]) for p in range(4) for n in range(4) if labels[p] == 1 and labels[n] == 0]
                auc = sum(1 if p > n else 0.5 if p == n else 0 for p, n in pairs) / len(pairs)
                ap, old_recall = 0.0, 0.0
                for threshold in sorted(set(scores), reverse=True):
                    selected = [i for i in range(4) if scores[i] >= threshold]
                    tp = sum(labels[i] for i in selected)
                    recall = tp / sum(labels)
                    ap += (recall - old_recall) * tp / len(selected)
                    old_recall = recall
                out = ranking_metrics(predictions(labels, scores))
                self.assertAlmostEqual(out["roc_auc"], auc)
                self.assertAlmostEqual(out["average_precision"], ap)

    def test_identical_arms_have_zero_paired_interval(self):
        rows = predictions()
        out = self.compare(rows, list(reversed(rows)))
        self.assertEqual(out["delta_ci95"]["roc_auc"], [0.0, 0.0])
        self.assertEqual(out["bootstrap"]["valid"], 100)  # both labels in every patient cluster

    def test_direction_pairing_and_cluster_multiplicity(self):
        good = predictions()
        bad = [dict(r, score=1 - r["score"]) for r in good]
        out = self.compare(bad, good)
        self.assertEqual(out["delta_b_minus_a"]["roc_auc"], 1)
        self.assertEqual(out["delta_ci95"]["roc_auc"], [1, 1])
        self.assertEqual(out["bootstrap"]["unit"], "patient")
        self.assertEqual(out["n_patients"], 3)

    def test_seed_and_row_order_are_reproducible(self):
        a = predictions(scores=(0.6, 0.4, 0.4, 0.8, 0.2, 0.3))
        b = predictions()
        self.assertEqual(self.compare(a, b, seed=7), self.compare(list(reversed(a)), b, seed=7))

    def test_alignment_label_group_and_partition_mismatches_refused(self):
        a = predictions()
        for b in (a[:-1], [dict(a[0], label=1)] + a[1:], [dict(a[0], patient_id="other")] + a[1:],
                  [dict(a[0], partition="val")] + a[1:], a + [a[0]]):
            with self.subTest(b=b), self.assertRaises(ValueError):
                self.compare(a, b)
        mixed = [dict(a[0], partition="val")] + a[1:]
        with self.assertRaises(ValueError):
            self.compare(mixed, mixed)
        train = [dict(r, partition="train") for r in a]
        with self.assertRaises(ValueError):
            self.compare(train, train)

    def test_unknown_groups_are_refused(self):
        a = [dict(r, patient_id="") for r in predictions()]
        with self.assertRaises(ValueError):
            self.compare(a, a)

    def test_single_class_draws_are_counted_and_ci_withheld(self):
        a = predictions(labels=(0, 1), scores=(0.1, 0.9))
        a[1]["patient_id"] = "p1"
        out = self.compare(a, a)
        self.assertGreater(out["bootstrap"]["invalid_single_class"], 0)
        self.assertEqual(out["delta_ci95"]["roc_auc"], None)
        self.assertTrue(out["warnings"])

    def test_single_patient_and_single_class_do_not_get_intervals(self):
        a = predictions(labels=(0, 1), scores=(0.1, 0.9))
        self.assertIsNone(self.compare(a, a)["delta_ci95"]["roc_auc"])
        a = predictions(labels=(1, 1), scores=(0.2, 0.8))
        out = self.compare(a, a)
        self.assertIsNone(out["arm_a"]["roc_auc"])
        self.assertEqual(out["bootstrap"]["valid"], 0)

    def test_invalid_bootstrap_options_are_refused(self):
        a = predictions()
        for opts in ({"n_boot": 0}, {"min_valid": 1}, {"n_boot": 10, "min_valid": 11}, {"n_boot": True}, {"seed": None}):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                paired_binary(a, a, **opts)


if __name__ == "__main__":
    unittest.main()
