"""SYNTHETIC published-snapshot fixtures; no archive/model execution."""
import copy
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.datasets import readiness
from helpers import symlink_or_skip


class DatasetReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        flags = {k: False for k in ("ready_for_training", "patient_grouping_verified", "reference_standard_verified", "medical_validation_established")}
        audit = {"dataset_id":"btxrd", "archive":{"sha256":"a"*64}, "image_count":3, "annotation_count":2,
                 "class_counts":{"normal":1,"benign":1,"malignant":1},
                 "exact_duplicates":{"pair_count":1,"conflicting_label_groups":[["S0.jpeg","S1.jpeg"]]},
                 "split_lists":{"exact_duplicate_groups_crossing_lists":[["S0.jpeg","S1.jpeg"]],"extension_mismatch_count":1},
                 "annotations":{"subtype_label_set_mismatch":[]}, **flags}
        evidence = {"dataset_id":"btxrd","archive_sha256":"a"*64,"release_image_count":3,
                    "supplied_row_count":3,"matched_image_count":3,"source_binding_verified":True,"status":"blocked",
                    "missing_evidence_counts":{k:3 for k in readiness.MISSING_FIELDS},
                    "cohort_created":False,"supplied_patient_ids_and_reference_values_exported":False, **flags}
        (self.root/readiness.FILES[0]).write_text(json.dumps(audit))
        (self.root/readiness.FILES[1]).write_text(json.dumps(evidence))
        with (self.root/readiness.FILES[2]).open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=readiness.EVIDENCE_COLUMNS,lineterminator="\n");writer.writeheader()
            for i in range(3):
                writer.writerow({"image_id":f"S{i}.jpeg","center":"1","tumor":"1","benign":"1","malignant":"0",
                                 "sha256":hashlib.sha256(f"SYNTHETIC source {i}".encode()).hexdigest(),"review_status":"unreviewed"})
        manifest={"base_commit":"b"*40,"files":[{"path":"docs/research-handoff/"+name,
                   "sha256":hashlib.sha256((self.root/name).read_bytes()).hexdigest(),"bytes":(self.root/name).stat().st_size}
                  for name in readiness.FILES]}
        (self.root/"publication-manifest.json").write_text(json.dumps(manifest))

    def rewrite(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value))
        self.rebind(name)

    def rebind(self, name):
        raw = (self.root / name).read_bytes()
        path = self.root / "publication-manifest.json"
        manifest = json.loads(path.read_text())
        for entry in manifest["files"]:
            if entry["path"] == "docs/research-handoff/" + name:
                entry.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        path.write_text(json.dumps(manifest))

    def evidence(self):
        return json.loads((self.root / readiness.FILES[1]).read_text())

    def test_published_snapshot_is_explicitly_not_current_readiness(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = readiness.summary(self.root)
        self.assertEqual(result["source_kind"], "published_review_snapshot")
        self.assertEqual(result["observations"]["images"], 3)
        self.assertEqual(result["observations"]["conflicting_images"], 2)
        self.assertEqual(result["observations"]["pairs_crossing_original_lists"], 1)
        for key in ("ready_for_training", "execution_authorized", "cohort_created", "medical_validation_established"):
            self.assertIs(result[key], False)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertIn("not a check of your current local files", result["note"])

    def test_checked_out_repository_snapshot_keeps_its_published_bytes(self):
        # On Windows, Git's LF->CRLF conversion used to alter these hash-verified files on checkout,
        # so the real snapshot read as "changed". .gitattributes marks the folder -text.
        result = readiness.summary()
        self.assertEqual(result["source_kind"], "published_review_snapshot")
        self.assertEqual(result["observations"]["images"], 3746)

    def test_changed_or_missing_file_is_not_silently_displayed(self):
        path = self.root / readiness.FILES[0]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(readiness.SnapshotError, "recorded file identity"):
            readiness.summary(self.root)
        path.unlink()
        with self.assertRaises(readiness.SnapshotError):
            readiness.summary(self.root)

    def test_ambiguous_manifest_identity_is_refused(self):
        path = self.root / "publication-manifest.json"; value = json.loads(path.read_text())
        entry = next(e for e in value["files"] if e["path"].endswith(readiness.FILES[0]))
        value["files"].append(copy.deepcopy(entry)); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(readiness.SnapshotError, "ambiguous"):
            readiness.summary(self.root)

    def test_escaping_symlink_and_oversized_file_are_refused(self):
        outside = self.root.parent / (self.root.name + "-outside")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        path = self.root / readiness.FILES[0]; outside.write_bytes(path.read_bytes()); path.unlink()
        with self.subTest("escaping symlink"):
            symlink_or_skip(self, path, outside)
            with self.assertRaises(readiness.SnapshotError):
                readiness.summary(self.root)
        path.unlink(missing_ok=True); path.write_bytes(b" " * (readiness.LIMIT_BYTES + 1))
        with self.assertRaisesRegex(readiness.SnapshotError, "read limit"):
            readiness.summary(self.root)

    def test_report_archive_identity_must_match(self):
        value = self.evidence(); value["archive_sha256"] = "f" * 64
        self.rewrite(readiness.FILES[1], value)
        with self.assertRaisesRegex(readiness.SnapshotError, "different source archives"):
            readiness.summary(self.root)

    def test_report_counts_are_checked_even_if_manifest_was_updated(self):
        for value in (True, -1, 2):
            report = self.evidence(); report["release_image_count"] = value; self.rewrite(readiness.FILES[1], report)
            with self.subTest(value=value), self.assertRaises(readiness.SnapshotError):
                readiness.summary(self.root)

    def test_medical_or_training_promotion_cannot_be_inferred_from_snapshot(self):
        for flag in ("ready_for_training", "patient_grouping_verified", "reference_standard_verified", "medical_validation_established", "cohort_created"):
            value = self.evidence(); value[flag] = True; self.rewrite(readiness.FILES[1], value)
            with self.subTest(flag=flag), self.assertRaises(readiness.SnapshotError):
                readiness.summary(self.root)
            value[flag] = False; self.rewrite(readiness.FILES[1], value)

    def test_missing_evidence_counts_must_be_finite_integer_row_counts(self):
        for value in (-1, True, 4, "3"):
            report = self.evidence(); report["missing_evidence_counts"]["patient_id"] = value; self.rewrite(readiness.FILES[1], report)
            with self.subTest(value=value), self.assertRaises(readiness.SnapshotError):
                readiness.summary(self.root)

    def test_summary_does_not_export_supplied_evidence_values(self):
        report = self.evidence(); report["unexpected_private_patient_values"] = ["PRIVATE-SYNTHETIC-VALUE"]
        self.rewrite(readiness.FILES[1], report)
        result = readiness.summary(self.root)
        self.assertNotIn("PRIVATE-SYNTHETIC", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_template_export_has_only_public_source_fields_and_blank_evidence(self):
        result = readiness.blank_template(self.root)
        rows = list(csv.DictReader(io.StringIO(result["csv"])))
        self.assertEqual(len(rows), 3)
        self.assertEqual(result["sha256"], hashlib.sha256((self.root/readiness.FILES[2]).read_bytes()).hexdigest())
        self.assertTrue(all(all(row[k] == "" for k in readiness.MISSING_FIELDS) for row in rows))
        self.assertTrue(all(row["review_status"] == "unreviewed" for row in rows))
        self.assertIs(result["execution_authorized"], False)

    def test_returned_patient_values_are_never_exported_as_a_blank_template(self):
        path = self.root / readiness.FILES[2]
        raw = path.read_text(); path.write_text(raw.replace(",,,,,,unreviewed,", ",PRIVATE-SYNTHETIC-PATIENT,,,,,reviewed,", 1))
        self.rebind(readiness.FILES[2])
        with self.assertRaisesRegex(readiness.SnapshotError, "blank evidence"):
            readiness.blank_template(self.root)

    def test_duplicate_template_ids_or_row_drift_are_refused(self):
        path = self.root / readiness.FILES[2]; lines = path.read_text().splitlines()
        for bad in ([lines[0], lines[1], lines[1], *lines[3:]], lines[:-1]):
            path.write_text("\n".join(bad) + "\n"); self.rebind(readiness.FILES[2])
            with self.assertRaises(readiness.SnapshotError):
                readiness.blank_template(self.root)

    def test_api_degrades_without_hiding_existing_manifest_audits(self):
        with mock.patch.object(readiness, "HANDOFF_DIR", self.root / "missing"):
            response = api.GET_ROUTES["/api/datasets/btxrd/evidence"]()
            self.assertIs(response["available"], False)
            self.assertIs(response["ready_for_training"], False)
            with self.assertRaises(api.ApiError) as error:
                api.GET_ROUTES["/api/datasets/btxrd/evidence-template"]()
            self.assertEqual(error.exception.status, 409)
            self.assertTrue(api.audit({"synthetic": True})["synthetic"])

    def test_reading_snapshot_imports_no_ml_runtime(self):
        script = ("import sys; from pathlib import Path; from cancer_workbench.datasets.readiness import summary, blank_template; "
                  "summary(Path(sys.argv[1])); blank_template(Path(sys.argv[1])); "
                  "assert not any(p in sys.modules for p in ('torch','numpy','sklearn','transformers'))")
        run = subprocess.run([sys.executable, "-B", "-c", script, str(self.root)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
