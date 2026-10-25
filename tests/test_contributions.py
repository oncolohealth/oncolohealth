import tempfile
import unittest
from pathlib import Path

from cancer_workbench.registry import load_catalog
from cancer_workbench.registry.contrib import SCHEMA, accept, check, pending, to_record


def model_submission(**over):
    sub = {
        "schema": SCHEMA, "type": "model", "name": "Example Lung Nodule Net",
        "summary": "Nodule detector trained on public CT.", "link": "https://zenodo.org/records/123/files/model.zip",
        "citation": "https://doi.org/10.5281/zenodo.123", "license_id": "apache-2.0", "commercial": True,
        "access": "open", "modality": "ct", "anatomy": "lung", "model_kind": "specialist",
        "tasks": "detection", "outputs": "boxes", "contributor_name": "A. Researcher",
        "rights_confirmed": True, "contains_identifiable_data": False,
    }
    sub.update(over)
    return sub


def dataset_submission(**over):
    sub = model_submission(type="dataset", name="Example Bone X-rays", patient_ids="partial", images="1200")
    for key in ("model_kind", "tasks", "outputs"):
        sub.pop(key)
    sub.update(over)
    return sub


class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.cat = load_catalog()

    def tearDown(self):
        self.tmp.cleanup()

    def test_model_becomes_a_cataloged_record_held_for_review(self):
        rec, errs = accept(model_submission(), self.cat, self.out)
        self.assertEqual(errs, [])
        self.assertEqual(rec["id"], "contrib-example-lung-nodule-net")
        self.assertEqual(rec["evidence_state"], "cataloged")
        self.assertEqual(rec["inference_permission"], "unreviewed")
        self.assertIsNone(rec["adapter"])
        self.assertEqual(rec["acquisition"]["tier"], "manual")
        self.assertEqual(rec["contribution"]["review"], "pending")
        self.assertEqual([r["id"] for r in pending(self.out)], [rec["id"]])

    def test_dataset_records_contributor_reported_counts_and_patient_grouping(self):
        rec, errs = accept(dataset_submission(), self.cat, self.out)
        self.assertEqual(errs, [])
        self.assertEqual(rec["counts"], {"status": "contributor-reported", "images": 1200})
        self.assertEqual(rec["labels"]["patient_ids"], "partial")
        self.assertTrue(rec["unresolved"])

    def test_unsafe_or_incomplete_submissions_are_refused(self):
        cases = {
            "link": model_submission(link="http://example.org/model.zip"),
            "rights": model_submission(rights_confirmed=False),
            "identifiable": model_submission(contains_identifiable_data=True),
            "access": model_submission(access="whatever"),
            "kind": model_submission(model_kind="robot"),
            "patient": dataset_submission(patient_ids="maybe"),
            "local path": model_submission(link="https://"),
        }
        for name, sub in cases.items():
            with self.subTest(name):
                self.assertTrue(check(sub))
                self.assertEqual(accept(sub, self.cat, self.out), (None, check(sub)))
        self.assertEqual(pending(self.out), [])

    def test_duplicate_contribution_is_refused(self):
        accept(model_submission(), self.cat, self.out)
        rec, errs = accept(model_submission(), self.cat, self.out)
        self.assertIsNone(rec)
        self.assertTrue(any("already" in e for e in errs))

    def test_record_never_claims_more_than_cataloged(self):
        rec = to_record(model_submission(evidence_state="externally_evaluated", inference_permission="allowed"))
        self.assertEqual((rec["evidence_state"], rec["inference_permission"]), ("cataloged", "unreviewed"))


if __name__ == "__main__":
    unittest.main()
