"""Synthetic evidence-return checks; no mapping or diagnosis is authenticated."""

import copy
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from cancer_workbench.datasets.evidence import check_btxrd_evidence
from cancer_workbench.datasets.release_audit import prepare_btxrd_evidence_template, EVIDENCE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


class EvidenceCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / "source.zip"
        self.write_release()

    def write_release(self, duplicate=False):
        with ZipFile(self.archive, "w") as z:
            z.writestr("dataset.csv", "image_id,center,tumor,benign,malignant\nA.jpeg,1,1,1,0\nB.jpeg,1,0,0,0\nC.jpg,2,1,0,1\n")
            for name in ("A.jpeg", "B.jpeg", "C.jpg"):
                z.writestr("images/" + name, b"A" if duplicate and name == "B.jpeg" else name[0].encode())
            for name in ("A.jpeg", "C.jpg"):
                z.writestr("Annotations/" + Path(name).stem + ".json", json.dumps({
                    "imagePath": name, "shapes": [{"shape_type": "polygon", "label": "synthetic"}]}))

    def completed_rows(self):
        rows = prepare_btxrd_evidence_template(self.archive)
        for index, row in enumerate(rows):
            row.update(patient_id=f"PRIVATE-SYNTHETIC-PATIENT-{index}", grouping_reference="PRIVATE-SYNTHETIC-MAP",
                       lesion_id=f"synthetic-lesion-{index}", reference_standard="synthetic-test-standard",
                       reference_evidence="PRIVATE-SYNTHETIC-REFERENCE", review_status="reviewed")
        return rows

    def test_blank_template_is_source_bound_but_evidence_blocked(self):
        rows = prepare_btxrd_evidence_template(self.archive)
        result = check_btxrd_evidence(self.archive, rows, expected_md5=hashlib.md5(self.archive.read_bytes()).hexdigest())
        self.assertTrue(result["source_binding_verified"])
        self.assertTrue(result["archive_reference_md5_checked"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["missing_evidence_counts"], {k: 3 for k in (
            "patient_id", "grouping_reference", "lesion_id", "reference_standard", "reference_evidence")})
        self.assertFalse(result["ready_for_training"])
        self.assertFalse(result["cohort_created"])

    def test_source_flags_hashes_and_review_flags_cannot_be_silently_rewritten(self):
        original = self.completed_rows()
        for field, value in {"center": "3", "tumor": "0", "benign": "0", "malignant": "1",
                             "sha256": "0" * 64, "review_flags": "silently-cleared"}.items():
            rows = copy.deepcopy(original)
            rows[0][field] = value
            result = check_btxrd_evidence(self.archive, rows)
            self.assertFalse(result["source_binding_verified"], field)
            self.assertTrue(any(f["code"] == "source_field_drift" and f.get("field") == field for f in result["findings"]))
        rows = copy.deepcopy(original)
        rows[0].update(center="1.0", tumor="true", benign="1.0", malignant="false", sha256=rows[0]["sha256"].upper())
        self.assertTrue(check_btxrd_evidence(self.archive, rows)["source_binding_verified"])

    def test_missing_unknown_and_duplicate_rows_break_source_binding(self):
        original = self.completed_rows()
        unknown = copy.deepcopy(original)
        unknown[0]["image_id"] = "not-released.jpeg"
        for rows, code in ((original[:-1], "release_image_missing"),
                           (unknown, "unknown_image_id"),
                           (original + [original[0]], "duplicate_image_id")):
            result = check_btxrd_evidence(self.archive, rows)
            self.assertFalse(result["source_binding_verified"])
            self.assertIn(code, {f["code"] for f in result["findings"]})

    def test_complete_declarations_remain_unverified_and_values_are_not_exported(self):
        rows = self.completed_rows()
        result = check_btxrd_evidence(self.archive, rows)
        self.assertEqual(result["status"], "declared_evidence_requires_review")
        self.assertTrue(result["source_binding_verified"])
        self.assertNotIn("PRIVATE-SYNTHETIC", json.dumps(result))
        self.assertFalse(result["patient_grouping_verified"])
        self.assertFalse(result["reference_standard_verified"])
        self.assertFalse(result["medical_validation_established"])
        self.assertEqual(result["evidence_content_sha256"], check_btxrd_evidence(self.archive, list(reversed(rows)))["evidence_content_sha256"])

    def test_placeholder_and_image_identifiers_are_not_completed_evidence(self):
        original = self.completed_rows()
        for field, value in (("patient_id", "Unknown"), ("lesion_id", "A"), ("patient_id", "C.jpg"),
                             ("reference_standard", "pending"), ("reference_evidence", "N/A")):
            rows = copy.deepcopy(original)
            rows[0][field] = value
            result = check_btxrd_evidence(self.archive, rows)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["missing_evidence_counts"].get(field), 1)

    def test_exact_copy_conflicts_survive_reviewed_status(self):
        self.write_release(duplicate=True)
        result = check_btxrd_evidence(self.archive, self.completed_rows())
        codes = {f["code"] for f in result["findings"]}
        self.assertIn("source_exact_duplicate_label_conflict", codes)
        self.assertIn("exact_duplicate_patient_mapping_conflict", codes)
        self.assertEqual(result["status"], "blocked")

    def test_multiple_lesions_can_differ_but_one_declared_lesion_cannot(self):
        rows = self.completed_rows()
        for row in rows:
            row["patient_id"] = "one-synthetic-patient"
        result = check_btxrd_evidence(self.archive, rows)
        self.assertEqual(result["status"], "declared_evidence_requires_review")
        for row in rows:
            row["lesion_id"] = "one-synthetic-lesion"
        result = check_btxrd_evidence(self.archive, rows)
        self.assertIn("declared_lesion_source_label_conflict", {f["code"] for f in result["findings"]})

    def test_schema_and_empty_source_are_rejected(self):
        rows = self.completed_rows()
        rows[0]["unexpected-private-column"] = "PRIVATE-SYNTHETIC-VALUE"
        with self.assertRaisesRegex(ValueError, "template columns"):
            check_btxrd_evidence(self.archive, rows)
        with ZipFile(self.archive, "w") as z:
            z.writestr("dataset.csv", "image_id,center,tumor,benign,malignant\n")
        with self.assertRaisesRegex(ValueError, "empty source metadata"):
            check_btxrd_evidence(self.archive, [])

    def test_cli_report_has_no_local_paths_or_supplied_reference_values(self):
        path = self.root / "returned.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=EVIDENCE_COLUMNS)
            writer.writeheader()
            writer.writerows(self.completed_rows())
        run = subprocess.run([sys.executable, "-B", "-m", "cancer_workbench", "btxrd-review", "check",
                              str(self.archive), str(path)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["status"], "declared_evidence_requires_review")
        self.assertNotIn(str(self.root), run.stdout)
        self.assertNotIn("PRIVATE-SYNTHETIC", run.stdout)


if __name__ == "__main__":
    unittest.main()
