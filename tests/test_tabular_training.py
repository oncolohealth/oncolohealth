import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("sklearn"), "ML extra required")
class TabularTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / "synthetic.csv"
        self.schema = {"features": {"feature": "synthetic_unit"}, "target": "synthetic_label", "classes": ["a", "b"],
                       "target_description": "Synthetic software test only", "source_url": "synthetic://fixture",
                       "label_reference": "synthetic labels", "split_reference": "synthetic disjoint groups"}
        self.rows = []
        for p, offset in (("train", 0), ("val", 0.0001), ("test", 0.0002)):
            for i in range(12):
                self.rows.append({"sample_id": f"{p}-{i}", "patient_id": f"group-{p}-{i}", "partition": p,
                                  "feature": (-2 if i < 6 else 2) + i / 100 + offset,
                                  "synthetic_label": "a" if i < 6 else "b"})
        self.write()

    def write(self):
        with self.csv.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)

    def test_fit_reload_predict_and_source_binding(self):
        from cancer_workbench.learning.tabular import fit, predict_profile
        schema = self.root / "schema.json"
        schema.write_text(json.dumps(self.schema))
        report = fit(self.csv, schema, self.root / "candidate")
        self.assertEqual(report["counts"], {"train": 12, "val": 12, "test": 12})
        self.assertTrue(report["saved_reload_verified"])
        self.assertEqual(report["state"], "candidate_not_promoted")
        out = predict_profile(self.root / "candidate", {"feature": 2.2}, {"feature": "synthetic_unit"})
        self.assertEqual(out["class"], "b")
        with self.assertRaisesRegex(ValueError, "units"):
            predict_profile(self.root / "candidate", {"feature": 2.2}, {"feature": "other"})
        (self.root / "candidate" / "head.npz").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "changed"):
            predict_profile(self.root / "candidate", {"feature": 2.2}, self.schema["features"])

    def test_missing_group_and_patient_leakage_are_rejected(self):
        from cancer_workbench.learning.tabular import prepare
        self.rows[12]["patient_id"] = self.rows[0]["patient_id"]
        self.write()
        with self.assertRaises(ValueError):
            prepare(self.csv, self.schema)
        self.rows[12]["patient_id"] = ""
        self.write()
        with self.assertRaisesRegex(ValueError, "patient/group ID"):
            prepare(self.csv, self.schema)

    def test_label_features_duplicates_and_nonfinite_values_are_rejected(self):
        from cancer_workbench.learning.tabular import prepare
        bad = dict(self.schema, features={"synthetic_label": "unit"})
        with self.assertRaisesRegex(ValueError, "cannot be predictors"):
            prepare(self.csv, bad)
        self.rows[12]["feature"] = self.rows[0]["feature"]
        self.write()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare(self.csv, self.schema)
        self.rows[12]["feature"] = "nan"
        self.write()
        with self.assertRaisesRegex(ValueError, "non-finite"):
            prepare(self.csv, self.schema)
