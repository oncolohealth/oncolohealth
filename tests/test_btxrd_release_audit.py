"""Synthetic archive checks; these tests do not establish medical validity."""

import hashlib
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from cancer_workbench.datasets.release_audit import audit_btxrd_release, prepare_btxrd_evidence_template, SUBTYPES
from cancer_workbench.datasets.audit import audit_dataset

ROOT = Path(__file__).resolve().parents[1]


def manifest_rows(rows):
    labels = {("0", "0", "0"): "normal", ("1", "1", "0"): "benign", ("1", "0", "1"): "malignant"}
    return [{"sample_id": r["image_id"], "patient_id": r["patient_id"], "partition": "unassigned",
             "label": labels.get(tuple(r[k] for k in ("tumor", "benign", "malignant")), ""),
             "sha256": r["sha256"]} for r in rows]


def workbook(rows, *, formula=False):
    stream = io.BytesIO()
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for row_num, row in enumerate(rows, 1):
        sheet += f'<row r="{row_num}">'
        for index, value in enumerate(row):
            col = chr(65 + index)
            if formula and row_num == 2 and index == 0:
                sheet += f'<c r="{col}{row_num}"><f>1+1</f><v>2</v></c>'
            else:
                sheet += f'<c r="{col}{row_num}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
        sheet += '</row>'
    sheet += '</sheetData></worksheet>'
    with ZipFile(stream, "w") as book:
        book.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        book.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return stream.getvalue()


def release(path, *, metadata=None, images=None, extras=None, formula=False):
    rows = metadata or [["image_id", "center", "tumor", "benign", "malignant"],
                        ["A.jpeg", "1", "1", "1", "0"],
                        ["B.jpeg", "1", "0", "0", "0"],
                        ["C.jpg", "2", "1", "0", "1"]]
    with ZipFile(path, "w") as archive:
        archive.writestr("BTXRD/dataset.xlsx", workbook(rows, formula=formula))
        for name, data in (images or {"A.jpeg": b"synthetic-identical", "B.jpeg": b"synthetic-identical",
                                     "C.jpg": b"synthetic-distinct"}).items():
            archive.writestr("BTXRD/images/" + name, data)
        for name in ("A", "C"):
            archive.writestr("BTXRD/Annotations/" + name + ".json",
                             json.dumps({"imagePath": name + (".jpg" if name == "C" else ".jpeg"),
                                         "shapes": [{"shape_type": "polygon", "label": "synthetic"}]}))
        for name, data in (extras or {}).items():
            archive.writestr(name, data)


class ReleaseAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "input.zip"

    def test_archive_joins_conflicting_exact_labels_and_split_leakage(self):
        release(self.path)
        train, val = self.root / "train.xlsx", self.root / "val.xlsx"
        train.write_bytes(workbook([["image_id"], ["A.jpeg"], ["C.jpeg"]]))
        val.write_bytes(workbook([["image_id"], ["B.jpeg"]]))
        digest = hashlib.md5(self.path.read_bytes()).hexdigest()
        result = audit_btxrd_release(self.path, expected_md5=digest, train_list=train, validation_list=val)
        self.assertEqual(result["archive"]["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertTrue(result["archive"]["reference_md5_checked"])
        self.assertEqual(result["class_counts"], {"benign": 1, "normal": 1, "malignant": 1})
        self.assertTrue(all(not v for v in result["joins"].values()))
        self.assertEqual(result["exact_duplicates"]["conflicting_label_groups"], [["A.jpeg", "B.jpeg"]])
        self.assertEqual(result["split_lists"]["exact_duplicate_groups_crossing_lists"], [["A.jpeg", "B.jpeg"]])
        self.assertEqual(result["split_lists"]["extension_mismatch_count"], 1)
        self.assertEqual(result["split_lists"]["train_list_sha256"], hashlib.sha256(train.read_bytes()).hexdigest())
        self.assertIs(result["ready_for_training"], False)
        self.assertIs(result["patient_grouping_verified"], False)
        self.assertNotIn("evidence_rows", result)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_checksum_mismatch_is_rejected(self):
        release(self.path)
        with self.assertRaisesRegex(ValueError, "MD5 does not match"):
            audit_btxrd_release(self.path, expected_md5="0" * 32)

    def test_unsafe_archive_is_rejected_without_extracting(self):
        release(self.path, extras={"../outside.txt": b"synthetic"})
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            audit_btxrd_release(self.path)
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_ambiguous_image_names_are_rejected(self):
        release(self.path, extras={"other/A.jpeg": b"other"})
        with self.assertRaisesRegex(ValueError, "ambiguous image"):
            audit_btxrd_release(self.path)

    def test_duplicate_metadata_ids_are_rejected(self):
        release(self.path, metadata=[["image_id", "center", "tumor", "benign", "malignant"],
                                     ["A", "1", "0", "0", "0"], ["A.jpeg", "1", "0", "0", "0"]])
        with self.assertRaisesRegex(ValueError, "repeats image_id"):
            audit_btxrd_release(self.path)

    def test_formula_cache_is_not_trusted(self):
        release(self.path, formula=True)
        with self.assertRaisesRegex(ValueError, "formulas"):
            audit_btxrd_release(self.path)

    def test_data_beyond_headers_is_not_silently_dropped(self):
        release(self.path, metadata=[["image_id", "center", "tumor", "benign", "malignant"],
                                     ["A.jpeg", "1", "0", "0", "0", "unheaded-value"]])
        with self.assertRaisesRegex(ValueError, "header width"):
            audit_btxrd_release(self.path)

    def test_subtype_label_set_difference_is_reported_without_adjudication(self):
        subtypes = sorted(SUBTYPES)
        row = ["A.jpeg", "1", "1", "1", "0"] + [int(k in {"osteochondroma", "synovial osteochondroma"}) for k in subtypes]
        with ZipFile(self.path, "w") as archive:
            archive.writestr("dataset.xlsx", workbook([["image_id", "center", "tumor", "benign", "malignant"] + subtypes, row]))
            archive.writestr("images/A.jpeg", b"synthetic")
            archive.writestr("Annotations/A.json", json.dumps({"imagePath": "A.jpeg", "shapes": [
                {"shape_type": "polygon", "label": "synovial osteochondroma"}]}))
        result = audit_btxrd_release(self.path)
        self.assertEqual(result["annotations"]["subtype_label_set_mismatch"], [{
            "image_id": "A.jpeg", "metadata_subtypes": ["osteochondroma", "synovial osteochondroma"],
            "annotation_labels": ["synovial osteochondroma"]}])
        self.assertFalse(result["reference_standard_verified"])

    def test_unknown_flags_and_missing_joins_are_findings_not_normal_labels(self):
        release(self.path, metadata=[["image_id", "center", "tumor", "benign", "malignant"],
                                     ["A.jpeg", "1", "unknown", "0", "0"],
                                     ["D.jpeg", "1", "1", "1", "0"]])
        result = audit_btxrd_release(self.path)
        self.assertEqual(result["class_counts"], {"invalid_flags": 1, "benign": 1})
        self.assertEqual(result["joins"]["image_ids_missing_file"], ["D.jpeg"])
        self.assertEqual(result["joins"]["tumor_ids_missing_annotation"], ["D"])

    def test_cli_is_portable_and_does_not_add_local_paths(self):
        release(self.path)
        run = subprocess.run([sys.executable, "-B", "-m", "cancer_workbench", "btxrd-review", "audit", str(self.path)],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["image_count"], 3)
        self.assertNotIn(str(self.root), run.stdout)
        self.assertIs(result["medical_validation_established"], False)

    def test_exif_values_are_never_exported(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("optional Pillow not installed")
        image = Image.new("RGB", (8, 8))
        exif = Image.Exif()
        exif[0x013B] = "PRIVATE-SYNTHETIC-AUTHOR"
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        release(self.path, images={"A.jpeg": buffer.getvalue(), "B.jpeg": buffer.getvalue(),
                                   "C.jpg": buffer.getvalue()})
        result = audit_btxrd_release(self.path, inspect_exif=True)
        self.assertEqual(result["exif"]["tag_presence_counts"]["Artist"], 3)
        self.assertNotIn("PRIVATE-SYNTHETIC-AUTHOR", json.dumps(result))
        self.assertIs(result["exif"]["values_exported"], False)

    def test_evidence_template_has_measured_hashes_and_blank_identity_evidence(self):
        release(self.path)
        rows = prepare_btxrd_evidence_template(self.path)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sha256"], hashlib.sha256(b"synthetic-identical").hexdigest())
        for row in rows:
            for field in ("patient_id", "grouping_reference", "lesion_id", "reference_standard", "reference_evidence"):
                self.assertEqual(row[field], "")
            self.assertEqual(row["review_status"], "unreviewed")
            self.assertNotIn("split", row)
        self.assertIn("exact_duplicate_label_conflict", rows[0]["review_flags"])
        self.assertIn("exact_duplicate_label_conflict", rows[1]["review_flags"])
        self.assertNotIn(str(self.root), json.dumps(rows))

    def test_evidence_template_cannot_bypass_missing_patient_gate(self):
        release(self.path)
        rows = prepare_btxrd_evidence_template(self.path)
        report = audit_dataset({"id": "btxrd", "classes": ["normal", "benign", "malignant"]}, manifest_rows(rows))
        self.assertIs(report["ready_for_training"], False)
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("missing_patient_id", codes)
        self.assertTrue(all(row["partition"] == "unassigned" for row in manifest_rows(rows)))

    def test_evidence_template_does_not_turn_unknown_flags_into_normal(self):
        release(self.path, metadata=[["image_id", "center", "tumor", "benign", "malignant"],
                                     ["A.jpeg", "1", "unknown", "0", "0"]])
        rows = prepare_btxrd_evidence_template(self.path)
        self.assertEqual(rows[0]["tumor"], "")
        self.assertIn("invalid_flags", rows[0]["review_flags"])
        report = audit_dataset({"id": "btxrd", "classes": ["normal", "benign", "malignant"]}, manifest_rows(rows))
        self.assertIs(report["ready_for_training"], False)
        self.assertIn("unknown_label", {finding["code"] for finding in report["findings"]})

    def test_evidence_cli_outputs_csv_with_true_extensions_and_no_paths(self):
        release(self.path)
        run = subprocess.run([sys.executable, "-B", "-m", "cancer_workbench", "btxrd-review", "template", str(self.path)],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        rows = list(csv.DictReader(io.StringIO(run.stdout)))
        self.assertEqual({r["image_id"] for r in rows}, {"A.jpeg", "B.jpeg", "C.jpg"})
        self.assertTrue(all(r["patient_id"] == "" for r in rows))
        self.assertNotIn(str(self.root), run.stdout)

    def test_spreadsheet_formula_like_image_id_is_rejected(self):
        release(self.path, metadata=[["image_id", "center", "tumor", "benign", "malignant"],
                                     ["=1+1.jpeg", "1", "0", "0", "0"]])
        with self.assertRaisesRegex(ValueError, "image_id"):
            prepare_btxrd_evidence_template(self.path)


if __name__ == "__main__":
    unittest.main()
