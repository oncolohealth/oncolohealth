"""Curriculum capture and admission. SYNTHETIC adapters and scenarios; no model weights."""
import json
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from cancer_workbench.coordinator import default_toolbox
from cancer_workbench.curriculum import export_curriculum
from cancer_workbench.curriculum.capture import capture, capture_one, load_scenarios
from cancer_workbench.registry import load_catalog

RUN = {"name": "run_specialist", "arguments": {"model_id": SYNTHETIC_MODEL_RECORD["id"], "task": SYNTHETIC_MODEL_RECORD["tasks"][0],
                                               "modality": SYNTHETIC_MODEL_RECORD["modality"][0], "anatomy": "any", "inputs": {"score": 0.7}}}


def _box():
    return default_toolbox(load_catalog(), {"synthetic-threshold": SyntheticThresholdAdapter()}, extra_models=[SYNTHETIC_MODEL_RECORD])


def _scenario(**kw):
    sc = {"id": "s1", "family": "f", "lineage_group": "g1", "split": "train_candidate", "user": "SYNTHETIC request",
          "turns": [[{"name": "search_catalog", "arguments": {"query": "zzz-no-match"}}], [RUN]]}
    return dict(sc, **kw)


class CaptureTests(unittest.TestCase):
    def test_capture_records_observed_calls_and_tracks_response_freshness(self):
        box = _box()
        first = capture_one(_scenario(), box)
        self.assertEqual(first["state"], "needs_response")
        self.assertEqual([c["call_id"] for c in first["calls"]], ["s1.t0.c0", "s1.t1.c0"])
        self.assertEqual(first["calls"][0]["observed"], {"result": []})
        self.assertTrue(first["calls"][0]["result_id"].startswith("sha256:"))
        env = first["calls"][1]["observed"]["result"]
        self.assertEqual(first["calls"][1]["result_id"], env["run_id"])
        self.assertTrue(env["synthetic"])
        self.assertEqual(first["calls"][1]["schema"]["function"]["name"], "run_specialist")
        self.assertEqual(first["review"]["status"], "pending")
        self.assertFalse(first["admitted_to_training"])
        self.assertNotIn("reasoning", json.dumps(first["messages"]))

        unattributed = capture_one(_scenario(response="SYNTHETIC answer", response_for=first["observed_digest"]), box)
        self.assertEqual(unattributed["state"], "needs_response")  # a response must name its author
        stale = capture_one(_scenario(response="SYNTHETIC answer", response_author="SYNTHETIC person", response_for="0" * 64), box)
        self.assertEqual(stale["state"], "stale_response")
        fresh = capture_one(_scenario(response="SYNTHETIC answer", response_author="SYNTHETIC person",
                                      response_for=first["observed_digest"]), box)
        self.assertEqual(fresh["state"], "pending_review")  # run ids and times differ; the digest ignores them
        self.assertIn("Response author: SYNTHETIC person", fresh["review"]["rights_notes"])
        self.assertEqual(fresh["messages"][-1], {"role": "assistant", "content": "SYNTHETIC answer"})

    def test_scenarios_refuse_lineage_groups_spanning_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenarios.json"
            path.write_text(json.dumps({"scenarios": [_scenario(), _scenario(id="s2", split="evaluation_reserved")]}))
            with self.assertRaisesRegex(ValueError, "span splits"):
                load_scenarios(path, Path(tmp) / "none.json")

    def test_capture_writes_manifest_with_sources_and_no_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = capture([_scenario()], Path(tmp), toolbox=_box())
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual((manifest["candidates"], manifest["tool_calls"]), (1, 2))
            self.assertIn("catalog/models.json", manifest["sources"]["files"])
            self.assertIn("none", manifest["admission"])


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.rec = capture_one(_scenario(response="SYNTHETIC answer", response_author="SYNTHETIC person"), _box())
        self.rec["state"] = "pending_review"

    def test_pending_candidates_are_never_exported(self):
        self.assertEqual(export_curriculum([self.rec]), [])

    def test_only_reviewed_cleared_train_candidates_are_exported(self):
        self.rec["review"].update(status="reviewed", rights_status="cleared")
        self.assertEqual(len(export_curriculum([self.rec])), 1)
        for split in ("development", "evaluation_reserved"):
            self.assertEqual(export_curriculum([dict(self.rec, split=split)]), [])
        self.assertEqual(export_curriculum([dict(self.rec, state="stale_response")]), [])
        self.assertEqual(export_curriculum([dict(self.rec, response_author=None)]), [])


if __name__ == "__main__":
    unittest.main()
