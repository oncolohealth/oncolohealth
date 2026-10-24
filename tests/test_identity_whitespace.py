"""Synthetic record formatting regressions; no medical data or model fitting."""
import copy
import importlib.util
import unittest

from cancer_workbench.datasets.audit import audit_dataset


def rows():
    return [{"sample_id": f"S{i}", "patient_id": f"P{i}", "duplicate_group": "",
             "partition": ("train", "val", "test")[i // 2], "label": ("n", "p")[i % 2]}
            for i in range(6)]


class ManifestIdentityWhitespaceTests(unittest.TestCase):
    def audit(self, records):
        return audit_dataset({"id": "synthetic", "classes": ["n", "p"], "unresolved": []}, records)

    def test_padded_patient_duplicate_and_sample_aliases_block_readiness(self):
        for field in ("patient_id", "duplicate_group", "sample_id"):
            for padded in (" SAME", "SAME ", "\tSAME\n"):
                records = rows(); records[0][field] = "SAME"; records[2][field] = padded
                before = copy.deepcopy(records)
                with self.subTest(field=field, padded=padded):
                    result = self.audit(records)
                    self.assertFalse(result["ready_for_training"])
                    self.assertTrue(any(f["code"] == "invalid_identity" and field in f["detail"]
                                        for f in result["findings"]))
                    self.assertEqual(records, before)

    def test_whitespace_only_patients_are_missing_and_not_counted(self):
        records = [dict(r, patient_id=(" ", "\t", "\n")[i // 2]) for i, r in enumerate(rows())]
        result = self.audit(records)
        self.assertFalse(result["ready_for_training"])
        self.assertEqual(result["patients_per_partition"], {})
        self.assertTrue(any(f["code"] == "missing_patient_id" and "6/6" in f["detail"]
                            for f in result["findings"]))

    def test_empty_patient_ids_remain_unknown(self):
        result = self.audit([dict(r, patient_id="") for r in rows()])
        self.assertFalse(result["ready_for_training"])
        self.assertEqual(result["patients_per_partition"], {})
        self.assertTrue(any(f["code"] == "missing_patient_id" for f in result["findings"]))

    def test_internal_spaces_and_case_are_not_silently_rewritten(self):
        records = [dict(r, sample_id=f"Sample {i}", patient_id=f"Patient {i}", duplicate_group=f"Group {i}")
                   for i, r in enumerate(rows())]
        records[0]["patient_id"] = "Case A"; records[2]["patient_id"] = "case A"
        before = copy.deepcopy(records)
        self.assertTrue(self.audit(records)["ready_for_training"])
        self.assertEqual(records, before)

    def test_empty_sample_identity_is_invalid(self):
        records = rows(); records[0]["sample_id"] = ""
        result = self.audit(records)
        self.assertFalse(result["ready_for_training"])
        self.assertTrue(any(f["code"] == "invalid_identity" and "sample_id" in f["detail"]
                            for f in result["findings"]))


@unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy for synthetic input arrays")
class HeadIdentityWhitespaceTests(unittest.TestCase):
    def data(self):
        import numpy as np
        return {"features": np.ones((6, 2)), "labels": np.array(["n", "p"] * 3),
                "classes": ["n", "p"], "partitions": np.array([r["partition"] for r in rows()]),
                "sample_ids": np.array([r["sample_id"] for r in rows()], dtype=object),
                "patient_ids": np.array([r["patient_id"] for r in rows()], dtype=object),
                "encoder": {"encoder_id": "synthetic", "revision": "0", "preprocessing_hash": "0"}}

    def test_outer_whitespace_aliases_are_rejected_for_every_identity_channel(self):
        import numpy as np
        from cancer_workbench.learning.heads import validate_head_inputs
        for field in ("sample_ids", "patient_ids", "group_ids", "duplicate_groups", "image_hashes"):
            for padded in (" SAME", "SAME ", "\tSAME\n"):
                data = self.data(); data[field] = np.array(["SAME", "B", padded, "D", "E", "F"], dtype=object)
                with self.subTest(field=field, padded=padded), self.assertRaisesRegex(ValueError, "surrounding whitespace"):
                    validate_head_inputs(data)

    def test_whitespace_only_optional_identities_are_rejected(self):
        import numpy as np
        from cancer_workbench.learning.heads import validate_head_inputs
        for field in ("patient_ids", "group_ids", "duplicate_groups", "image_hashes"):
            data = self.data(); data[field] = np.array([" "] * 6)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "surrounding whitespace"):
                validate_head_inputs(data)

    def test_internal_spaces_are_preserved(self):
        import numpy as np
        from cancer_workbench.learning.heads import validate_head_inputs
        data = self.data(); data["patient_ids"] = np.array([f"Patient {i}" for i in range(6)])
        before = data["patient_ids"].copy()
        validate_head_inputs(data)
        np.testing.assert_array_equal(data["patient_ids"], before)

    def test_empty_optional_identities_remain_unknown_for_exploratory_input(self):
        import numpy as np
        from cancer_workbench.learning.heads import validate_head_inputs
        data = self.data()
        for field in ("patient_ids", "group_ids", "duplicate_groups", "image_hashes"):
            data[field] = np.array([""] * 6)
        validate_head_inputs(data)

    def test_exact_group_overlap_still_fails(self):
        import numpy as np
        from cancer_workbench.learning.heads import validate_head_inputs
        data = self.data(); data["patient_ids"] = np.array(["SAME", "B", "SAME", "D", "E", "F"])
        with self.assertRaisesRegex(ValueError, "patient_ids overlap"):
            validate_head_inputs(data)


if __name__ == "__main__":
    unittest.main()
