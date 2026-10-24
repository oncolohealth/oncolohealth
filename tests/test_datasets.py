import unittest

from cancer_workbench.datasets import audit_dataset, grouped_split

SPEC = {"id": "synthetic", "classes": ["neg", "pos"], "unresolved": []}


def rows(n=60):
    # SYNTHETIC: 20 patients x 3 images
    return [{"sample_id": f"s{i}", "patient_id": f"p{i // 3}", "duplicate_group": "", "partition": "unassigned",
             "label": "pos" if (i // 3) % 4 == 0 else "neg"} for i in range(n)]


class AuditTests(unittest.TestCase):
    def test_detects_patient_leakage(self):
        r = rows()
        r[0]["partition"], r[1]["partition"] = "train", "test"
        codes = [f["code"] for f in audit_dataset(SPEC, r)["findings"]]
        self.assertIn("patient_leakage", codes)

    def test_missing_patient_ids_flagged(self):
        r = [dict(x, patient_id="") for x in rows()]
        rep = audit_dataset(SPEC, r)
        self.assertIn("missing_patient_id", [f["code"] for f in rep["findings"]])
        self.assertFalse(rep["ready_for_training"])

    def test_unresolved_evidence_blocks_readiness(self):
        rep = audit_dataset(dict(SPEC, unresolved=["label adjudication unknown"]), grouped_split(rows(), {"train": .8, "test": .2}))
        self.assertFalse(rep["ready_for_training"])

    def test_unknown_label(self):
        r = rows()
        r[0]["label"] = "maybe"
        self.assertIn("unknown_label", [f["code"] for f in audit_dataset(SPEC, r)["findings"]])


class SplitTests(unittest.TestCase):
    def test_groups_never_straddle_and_split_is_deterministic(self):
        a = grouped_split(rows(), {"train": .7, "val": .15, "test": .15}, seed="1")
        b = grouped_split(rows(), {"train": .7, "val": .15, "test": .15}, seed="1")
        self.assertEqual([r["partition"] for r in a], [r["partition"] for r in b])
        rep = audit_dataset(SPEC, a)
        self.assertNotIn("patient_leakage", [f["code"] for f in rep["findings"]])
        self.assertTrue(rep["ready_for_training"])
        self.assertEqual({r["partition"] for r in a}, {"train", "val", "test"})


if __name__ == "__main__":
    unittest.main()
