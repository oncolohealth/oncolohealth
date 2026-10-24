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

    def test_refuses_bad_inputs_before_any_fit(self):
        from unittest import mock

        import numpy as np

        from cancer_workbench.learning.heads import train_feature_head

        data = synthetic_data()
        tr, va = (np.where(data["partitions"] == p)[0] for p in ("train", "val"))
        nan = data["features"].copy()
        nan[3, 0] = np.nan
        dup_ids, pids, groups, no_val_pos = (data[k].copy() for k in ("sample_ids", "patient_ids", "patient_ids", "labels"))
        dup_ids[va[0]] = dup_ids[tr[0]]
        pids[[tr[0], va[0]]] = "p1"
        groups[[tr[1], va[1]]] = "dup-1"
        no_val_pos[va] = "neg"
        cases = {
            "non-finite": dict(data, features=nan),
            "1-d features": dict(data, features=data["features"][:, 0]),
            "text features": dict(data, features=data["features"].astype(str)),
            "misaligned": dict(data, labels=data["labels"][:-1]),
            "duplicate id": dict(data, sample_ids=dup_ids),
            "unknown partition": dict(data, partitions=np.where(data["partitions"] == "test", "holdout", data["partitions"])),
            "patient spans train/val": dict(data, patient_ids=pids),
            "duplicate group spans train/val": dict(data, group_ids=groups),
            "val misses a class": dict(data, labels=no_val_pos),
            "repeated class": dict(data, classes=["neg", "neg"]),
        }
        with mock.patch("sklearn.linear_model.LogisticRegression.fit") as fit:
            for name, bad in cases.items():
                with self.subTest(name), self.assertRaises(ValueError):
                    train_feature_head(bad)
            fit.assert_not_called()

    def test_blank_groups_and_unassigned_rows_are_accepted(self):
        import numpy as np

        from cancer_workbench.learning.heads import train_feature_head

        data = synthetic_data()
        groups = np.array([""] * len(data["sample_ids"]), dtype=object)
        parts = data["partitions"].astype(object)
        parts[-1] = "unassigned"
        groups[[0, len(parts) - 1]] = "dup-1"  # shared only with an unassigned row
        self.assertGreater(train_feature_head(dict(data, partitions=parts, group_ids=groups)).val_score, 0.9)

    def test_three_class(self):
        from cancer_workbench.evaluation.metrics import multiclass_report
        from cancer_workbench.learning.heads import evaluate_head, train_feature_head

        data = synthetic_data(classes=("normal", "benign", "malignant"), sep=3.0)
        out = evaluate_head(train_feature_head(data), data)
        rep = multiclass_report(out["y_true"], out["probs"], out["classes"], n_boot=50)
        self.assertGreater(rep["balanced_accuracy"], 0.8)
        self.assertEqual(sum(rep["support"].values()), rep["n"])
        self.assertIn("too narrow", rep["ci_method"])

    def test_saved_head_reloads_to_same_predictions(self):
        import numpy as np

        from cancer_workbench.learning.heads import evaluate_head, load_head, save_head, train_feature_head

        for classes in (("neg", "pos"), ("normal", "benign", "malignant")):
            data = synthetic_data(classes=classes)
            head = train_feature_head(data)
            path = Path(tempfile.mkdtemp()) / "head.npz"
            save_head(head, path)
            back = load_head(path)
            np.testing.assert_allclose(evaluate_head(back, data)["probs"], evaluate_head(head, data)["probs"], atol=1e-12)
            self.assertEqual((back.classes, back.encoder, back.train_ids), (head.classes, head.encoder, head.train_ids))
            with self.assertRaises(ValueError):
                evaluate_head(back, data, "train")


class SourceShiftTests(unittest.TestCase):
    def test_selection_prefers_val_score_then_baseline(self):
        from cancer_workbench.experiments.btxrd_source_shift import select

        self.assertEqual(select({"pad": 0.80, "pad_pstretch": 0.82, "native_crop": 0.81}), "pad_pstretch")
        self.assertEqual(select({"native_crop": 0.85, "pad_pstretch": 0.85, "pad": 0.85}), "pad")
        self.assertEqual(select({"native_crop": 0.85, "pad_pstretch": 0.85, "pad": 0.80}), "pad_pstretch")

    def test_summary_reports_test_only_for_baseline_and_pick(self):
        from cancer_workbench.experiments.btxrd_source_shift import LABEL, summary

        t = {"n": 10, "macro_roc_auc": 0.6, "macro_roc_auc_ci95": [0.5, 0.7], "balanced_accuracy": 0.5, "recall": {"a": 0.5}}
        sel = [{"endpoint": "three_class", "encoder": "e", "selected": "native_crop",
                "val_macro_roc_auc": {"pad": 0.8, "pad_pstretch": 0.7, "native_crop": 0.9}}]
        res = [{"endpoint": "three_class", "encoder": "e", "variant": v, "selected": v == "native_crop", "test": t}
               for v in ("pad", "native_crop")]
        text = summary(sel, res)
        self.assertIn(LABEL, text)
        self.assertIn("already seen", text)
        test_rows = text.split("TEST (centers 2 + 3)")[1]
        self.assertIn("native_crop (selected)", test_rows)
        self.assertNotIn("pad_pstretch", test_rows)


@unittest.skipUnless(HAS_ML, "needs the ml extra")
class NearDuplicateTests(unittest.TestCase):
    def test_pairs_need_both_encoders_to_agree(self):
        import numpy as np

        from cancer_workbench.experiments.btxrd_near_duplicates import pair_scores

        rng = np.random.default_rng(0)  # SYNTHETIC features, not image embeddings
        a, b = rng.normal(size=(20, 8)), rng.normal(size=(20, 8))
        a[5], b[5] = a[2] + 0.01, b[2] + 0.01  # 2 and 5 match under both encoders
        a[9] = a[7]  # 7 and 9 match under one encoder only
        pairs, _ = pair_scores([a, b], top=3)
        self.assertEqual(pairs[0][:2], (2, 5))
        self.assertGreater(pairs[0][2], 0.99)
        self.assertNotIn((7, 9), [p[:2] for p in pairs])
        self.assertTrue(all(i < j for i, j, *_ in pairs))
        self.assertEqual([p[2] for p in pairs], sorted((p[2] for p in pairs), reverse=True))


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

    def test_variants(self):
        from PIL import Image

        from cancer_workbench.adapters.encoder import load_image, preprocessing_hash

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wide.png"
            im = Image.new("L", (200, 100), 100)  # SYNTHETIC: grey, with a brighter right half
            im.paste(150, (100, 0, 200, 100))
            im.save(p)
            stretched = load_image(p, 64, "pad_pstretch")
            cropped = load_image(p, 64, "native_crop")
            with self.assertRaises(ValueError):
                load_image(p, 64, "unknown")
        self.assertAlmostEqual(float(stretched[0, 32, 8]), 0.0, places=2)  # grey half becomes black
        self.assertAlmostEqual(float(stretched[0, 32, 56]), 1.0, places=2)  # brighter half becomes white
        self.assertEqual(tuple(cropped.shape), (3, 64, 64))
        self.assertAlmostEqual(float(cropped[0, 2, 32]), 150 / 255, places=1)  # no black padding: the crop fills the square
        self.assertEqual(len({preprocessing_hash("rad-dino", v) for v in ("pad", "pad_pstretch", "native_crop")}), 3)

    def test_only_native_crop_decodes_jpegs_at_full_resolution(self):
        from unittest import mock

        from PIL import Image, JpegImagePlugin

        from cancer_workbench.adapters.encoder import load_image

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "large.jpg"
            Image.linear_gradient("L").resize((640, 480)).save(p)  # SYNTHETIC gradient, large enough to draft
            draft = JpegImagePlugin.JpegImageFile.draft
            with mock.patch.object(JpegImagePlugin.JpegImageFile, "draft", autospec=True, side_effect=draft) as spy:
                for variant, calls in (("pad", 1), ("pad_pstretch", 1), ("native_crop", 0)):
                    spy.reset_mock()
                    load_image(p, 64, variant)
                    with self.subTest(variant=variant):
                        self.assertEqual(spy.call_count, calls)


if __name__ == "__main__":
    unittest.main()
