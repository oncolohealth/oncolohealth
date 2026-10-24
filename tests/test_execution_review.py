"""SYNTHETIC execution-review limits; no model, medical data or workload."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.experiments import workspace


class ExecutionReviewTests(unittest.TestCase):
    def preview(self):
        with mock.patch.object(api.budget, "usage_bytes", return_value=0), mock.patch.object(
                api.budget, "budget_bytes", return_value=100):
            return api.experiment_preview({"synthetic": True, "reuse_path": "transfer_learning",
                                           "planned_bytes": 0, "question": "SYNTHETIC question"})

    def test_passing_draft_keeps_all_execution_requirements_open(self):
        preview = self.preview()
        self.assertEqual(preview["plan"]["state"], "ready_for_review")
        review = preview["execution_review"]
        self.assertFalse(review["execution_authorized"])
        self.assertFalse(review["dispatch_available"])
        self.assertEqual(review["basis"], "current_preview")
        self.assertEqual({r["code"] for r in review["required_review"]},
                         {"protocol", "artifacts", "evidence", "resources", "controls", "authorization"})
        self.assertIn("Synthetic", review["evidence_scope"])

    def test_summary_is_pure_and_record_hash_is_not_medical_authentication(self):
        preview = self.preview()
        preview["synthetic"] = False
        before = copy.deepcopy(preview)
        with mock.patch("builtins.open", side_effect=AssertionError("summary must not read files")):
            review = workspace.execution_review(preview)
        self.assertEqual(preview, before)
        self.assertEqual(review["manifest_sha256"], preview["manifest"]["sha256"])
        self.assertEqual(review["model_revision"], preview["plan"]["model_revision"])
        self.assertIn("source medical files were not checked", review["input_binding"])
        self.assertIn("diagnostic references", review["evidence_scope"])
        self.assertNotIn("ready", review)
        review["draft_blockers"].append("must not mutate the plan")
        self.assertEqual(preview, before)

    def test_blocked_draft_retains_exact_existing_blockers(self):
        preview = self.preview()
        preview["plan"].update(state="blocked", blockers=["dataset audit: missing_patient_id", "planned storage exceeds budget"])
        review = workspace.execution_review(preview)
        self.assertEqual(review["draft_blockers"], preview["plan"]["blockers"])
        self.assertFalse(review["execution_authorized"])

    def test_browser_cannot_supply_execution_review_or_approval(self):
        with self.assertRaises(api.ApiError):
            api.experiment_preview({"synthetic": True, "reuse_path": "transfer_learning", "planned_bytes": 0,
                                    "execution_review": {"execution_authorized": True}})

    def test_save_recomputes_summary_and_marks_snapshot_not_current_files(self):
        preview = self.preview()
        preview["execution_review"] = {"execution_authorized": True, "dispatch_available": True}
        with tempfile.TemporaryDirectory() as folder:
            saved = workspace.save_draft(Path(folder), preview, source_revision="SYNTHETIC source")
            review = saved["draft"]["execution_review"]
            self.assertFalse(review["execution_authorized"])
            self.assertFalse(review["dispatch_available"])
            self.assertEqual(review["basis"], "saved_snapshot")
            self.assertIn("current files have not been rechecked", review["input_binding"])

    def test_legacy_and_forged_saved_summaries_are_recomputed_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved = workspace.save_draft(root, self.preview(), source_revision="SYNTHETIC source")
            path = root / saved["file"]
            original = json.loads(path.read_text())
            for summary in (None, {"basis": "current_preview", "execution_authorized": True,
                                   "dispatch_available": True, "required_review": []}):
                doc = copy.deepcopy(original)
                if summary is None:
                    doc.pop("execution_review")
                else:
                    doc["execution_review"] = summary
                path.write_text(json.dumps(doc))
                before = path.read_bytes()
                with self.subTest(summary=summary):
                    result = workspace.detail(root, saved["key"])["record"]["execution_review"]
                    self.assertFalse(result["execution_authorized"])
                    self.assertFalse(result["dispatch_available"])
                    self.assertEqual(result["basis"], "saved_snapshot")
                    self.assertEqual(len(result["required_review"]), 6)
                    self.assertEqual(path.read_bytes(), before)

    def test_malformed_recorded_blockers_do_not_hide_review_requirements(self):
        preview = self.preview()
        preview["plan"]["blockers"] = None
        review = workspace.execution_review(preview, recorded=True)
        self.assertIn("malformed", review["draft_blockers"][0])
        self.assertEqual(len(review["required_review"]), 6)


if __name__ == "__main__":
    unittest.main()
