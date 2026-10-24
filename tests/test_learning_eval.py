import importlib.util
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.experiments.btxrd_baseline import endpoint_rows, make_split

HAS_ML = all(importlib.util.find_spec(m) for m in ("numpy", "sklearn"))
HAS_TORCH = HAS_ML and all(importlib.util.find_spec(m) for m in ("torch", "PIL"))
ENC = {"encoder_id": "synthetic", "revision": "0", "preprocessing_hash": "0"}


def synthetic_data(n=300, classes=("neg", "pos"), sep=2.0, seed=0):
    """SYNTHETIC Gaussian blobs, one per class. Not image features."""
    import numpy as np

    rng = np.random.default_rng(seed)
    y = rng.integers(0, len(classes), n)
    X = rng.normal(size=(n, 8)) + sep * np.eye(len(classes), 8)[y]
    parts = np.array(["train"] * (n * 6 // 10) + ["val"] * (n * 2 // 10) + ["test"] * (n - n * 8 // 10))
    return {"features": X, "labels": np.array([classes[i] for i in y]), "partitions": parts,
            "sample_ids": np.array([f"s{i}" for i in range(n)]), "patient_ids": np.array([""] * n),
            "classes": list(classes), "encoder": ENC}


class SplitProtocolTests(unittest.TestCase):
    ROWS = [{"sample_id": f"s{i}", "patient_id": "", "duplicate_group": "", "partition": "unassigned",
             "label": ("normal", "benign", "malignant")[i % 3], "label_derived": ("normal", "benign", "malignant")[i % 3],
             "center": "1" if i < 60 else "2"} for i in range(90)]

    def test_source_holdout_tests_only_other_centers(self):
        rows = make_split(self.ROWS, "source_holdout")
        self.assertEqual({r["center"] for r in rows if r["partition"] == "test"}, {"2"})
        self.assertEqual({r["partition"] for r in rows if r["center"] == "1"}, {"train", "val"})
        self.assertEqual(len(rows), 90)

    def test_image_stratified_is_deterministic(self):
        a, b = make_split(self.ROWS, "image_stratified", "1"), make_split(self.ROWS, "image_stratified", "1")
        self.assertEqual([r["partition"] for r in a], [r["partition"] for r in b])

    def test_endpoint_rows(self):
        self.assertEqual({r["label"] for r in endpoint_rows(self.ROWS, "tumor_vs_normal")}, {"normal", "tumor"})
        self.assertEqual(len(endpoint_rows(self.ROWS, "benign_vs_malignant")), 60)
        quarantined = [dict(self.ROWS[0], label="", label_derived=""), dict(self.ROWS[1], label="")]
        self.assertEqual(endpoint_rows(quarantined, "three_class"), [])


@unittest.skipUnless(HAS_ML, "needs the ml extra")
class HeadTests(unittest.TestCase):
    def test_learns_separable_classes(self):
        from cancer_workbench.evaluation.metrics import binary_report
        from cancer_workbench.learning.heads import evaluate_head, train_feature_head

        data = synthetic_data()
        head = train_feature_head(data)
        out = evaluate_head(head, data)
        rep = binary_report(out["y_true"], [p[1] for p in out["probs"]], 0.5, n_boot=50)
        self.assertGreater(rep["roc_auc"], 0.9)

    def test_refuses_leakage_and_mismatches(self):
        from cancer_workbench.learning.heads import evaluate_head, train_feature_head

        data = synthetic_data()
        head = train_feature_head(data)
        with self.assertRaises(ValueError):
            evaluate_head(head, data, "train")
        with self.assertRaises(ValueError):
            evaluate_head(head, dict(data, encoder=dict(ENC, revision="1")))
        with self.assertRaises(ValueError):
            evaluate_head(head, dict(data, classes=["pos", "neg"]))

    def test_three_class(self):
        from cancer_workbench.evaluation.metrics import multiclass_report
        from cancer_workbench.learning.heads import evaluate_head, train_feature_head

        data = synthetic_data(classes=("normal", "benign", "malignant"), sep=3.0)
        out = evaluate_head(train_feature_head(data), data)
        rep = multiclass_report(out["y_true"], out["probs"], out["classes"], n_boot=50)
        self.assertGreater(rep["balanced_accuracy"], 0.8)
        self.assertEqual(sum(rep["support"].values()), rep["n"])
        self.assertIn("too narrow", rep["ci_method"])


@unittest.skipUnless(HAS_ML, "needs the ml extra")
class MetricTests(unittest.TestCase):
    def test_binary_report_and_threshold(self):
        from cancer_workbench.evaluation.metrics import binary_report, calibration
        from cancer_workbench.evaluation.thresholds import choose_threshold

        y, s = [0, 0, 0, 1, 1, 1], [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
        t = choose_threshold(y, s)
        rep = binary_report(y, s, t, n_boot=50)
        self.assertEqual((rep["sensitivity"], rep["specificity"], rep["roc_auc"]), (1.0, 1.0, 1.0))
        self.assertEqual(choose_threshold(y, s, "sensitivity>=1.0"), 0.7)
        self.assertLess(calibration(y, s, n_bins=5)["ece"], 0.35)

    def test_grouped_bootstrap_label(self):
        from cancer_workbench.evaluation.metrics import binary_report

        rep = binary_report([0, 1, 0, 1], [0.2, 0.8, 0.4, 0.6], 0.5, group_ids=["a", "a", "b", "b"], n_boot=20)
        self.assertEqual(rep["ci_method"], "grouped bootstrap")


@unittest.skipUnless(HAS_TORCH, "needs torch and pillow")
class PreprocessingTests(unittest.TestCase):
    def test_pads_whole_image_to_square(self):
        from PIL import Image

        from cancer_workbench.adapters.encoder import load_image

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wide.png"
            Image.new("L", (200, 100), 255).save(p)  # SYNTHETIC white rectangle
            t = load_image(p, 64)
        self.assertEqual(tuple(t.shape), (3, 64, 64))
        self.assertAlmostEqual(float(t[0, 32, 32]), 1.0, places=2)  # content kept in the middle
        self.assertAlmostEqual(float(t[0, 2, 32]), 0.0, places=2)  # black padding above
        self.assertTrue(bool((t[0] == t[1]).all()))


if __name__ == "__main__":
    unittest.main()
