"""Synthetic records only. No workloads, medical data or provider calls."""
import copy
import dataclasses
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.datasets import write_manifest
from cancer_workbench.experiments import workspace
from cancer_workbench.experiments.records import ExperimentRecord, JobState, REUSE_PATHS
from cancer_workbench.registry.store import Catalog


class DraftApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.runs = self.root / "runs"
        for target, name, value in ((api, "DATA_DIR", self.data), (api, "EXPERIMENTS_DIR", self.runs)):
            p = mock.patch.object(target, name, value)
            p.start(); self.addCleanup(p.stop)
        for name, value in (("usage_bytes", 10), ("budget_bytes", 100)):
            p = mock.patch.object(api.budget, name, return_value=value)
            p.start(); self.addCleanup(p.stop)
        self.body = {"synthetic": True, "reuse_path": "transfer_learning", "planned_bytes": 20,
                     "question": "SYNTHETIC research question"}

    def test_three_paths_preview_without_writing_or_dispatch(self):
        before = copy.deepcopy(self.body)
        for path in REUSE_PATHS:
            result = api.experiment_preview(dict(self.body, reuse_path=path))
            self.assertEqual(result["plan"]["state"], "ready_for_review")
            self.assertFalse(result["plan"]["execution_authorized"])
            self.assertTrue(result["synthetic"])
            self.assertEqual(result["audit"]["rows"], 12)
            self.assertEqual(result["audit"]["findings"], [])
        self.assertEqual(self.body, before)
        self.assertFalse(self.runs.exists())

    def test_saved_draft_survives_fresh_read_and_is_not_an_experiment_record(self):
        with mock.patch("cancer_workbench.experiments.btxrd_baseline._git_revision", return_value="fixture-revision"):
            result = api.experiment_save(self.body)
        detail = workspace.detail(self.runs, result["key"])
        self.assertEqual(detail["kind"], "draft")
        self.assertEqual(detail["record"]["source_revision"], "fixture-revision")
        self.assertFalse(detail["record"]["plan"]["execution_authorized"])
        self.assertEqual(api.experiment_history()["items"][0]["key"], result["key"])
        self.assertEqual(list(self.runs.glob("*/records.json")), [])

    def test_client_cannot_supply_audit_permissions_budget_or_execution_state(self):
        for key in ("audit", "model", "budget", "plan", "reuse_permissions", "execution_authorized"):
            with self.subTest(key=key), self.assertRaises(api.ApiError):
                api.experiment_save(dict(self.body, **{key: {}}))

    def test_invalid_types_and_storage_are_rejected_or_blocked(self):
        for patch in ({"planned_bytes": True}, {"planned_bytes": -1}, {"planned_bytes": 0.5},
                      {"planned_bytes": None}, {"synthetic": "true"}, {"question": []},
                      {"question": "x" * 1001}, {"reuse_path": "auto_train"}):
            with self.subTest(patch=patch), self.assertRaises(api.ApiError):
                api.experiment_preview(dict(self.body, **patch))
        result = api.experiment_preview(dict(self.body, planned_bytes=91))
        self.assertEqual(result["plan"]["state"], "blocked")

    def _real_manifest(self):
        rows = [{"sample_id": f"S{i}", "patient_id": f"P{i}", "partition": p, "label": str(i % 2)}
                for i, p in enumerate(("train", "train", "val", "val", "test", "test"))]
        path = self.data / "fixture-dataset" / "manifest.csv"
        write_manifest(path, rows)
        model = {"id": "fixture-model", "evidence_state": "access_obtained", "acquisition": {"revision": "a" * 40},
                 "reuse_permissions": {"transfer_learning": {"status": "allowed", "evidence": "synthetic fixture review"}}}
        catalog = Catalog([model], [{"id": "fixture-dataset", "unresolved": []}])
        return path, rows, catalog

    def test_save_recomputes_changed_manifest_and_retains_exact_identity(self):
        path, rows, catalog = self._real_manifest()
        body = dict(self.body, synthetic=False, model_id="fixture-model", manifest="fixture-dataset/manifest.csv")
        with mock.patch.object(api, "load_catalog", return_value=catalog):
            first = api.experiment_preview(body)
            self.assertEqual(first["plan"]["state"], "ready_for_review")
            rows[0]["patient_id"] = ""
            write_manifest(path, rows)
            second = api.experiment_save(body)["draft"]
        self.assertEqual(second["plan"]["state"], "blocked")
        self.assertIn("dataset audit: missing_patient_id", second["plan"]["blockers"])
        self.assertNotEqual(first["manifest"]["sha256"], second["manifest"]["sha256"])
        self.assertEqual(second["manifest"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(second["execution_review"]["manifest_sha256"], second["manifest"]["sha256"])
        self.assertEqual(second["execution_review"]["draft_blockers"], second["plan"]["blockers"])
        self.assertEqual(second["execution_review"]["basis"], "saved_snapshot")

    def test_manifest_outside_data_and_malformed_csv_do_not_produce_ready_drafts(self):
        path, rows, catalog = self._real_manifest()
        body = dict(self.body, synthetic=False, model_id="fixture-model", manifest="fixture-dataset/manifest.csv")
        with mock.patch.object(api, "load_catalog", return_value=catalog):
            for rel in ("../../outside.csv", "", None):
                with self.subTest(rel=rel), self.assertRaises(api.ApiError):
                    api.experiment_preview(dict(body, manifest=rel))
            for content in ("foo,bar\n1,2\n", "sample_id,patient_id,partition,label\ns,p,train,0,extra\n",
                            "sample_id,patient_id,partition,label,label\ns,p,train,0,1\n"):
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(api.ApiError):
                    api.experiment_preview(body)

    def test_real_catalog_model_remains_blocked(self):
        path = self.data / "btxrd" / "manifest.csv"
        write_manifest(path, [{"sample_id": "S0", "patient_id": "", "partition": "unassigned", "label": "normal"}])
        result = api.experiment_preview(dict(self.body, synthetic=False, model_id="rad-dino", manifest="btxrd/manifest.csv"))
        self.assertFalse(result["synthetic"])
        self.assertEqual(result["plan"]["state"], "blocked")
        self.assertIn("dataset audit: missing_patient_id", result["plan"]["blockers"])
        self.assertTrue(any("permission" in b for b in result["plan"]["blockers"]))

    def test_ambiguous_identities_and_missing_assigned_labels_are_visible(self):
        path, rows, catalog = self._real_manifest()
        rows[0]["patient_id"] = " P0"
        rows[1]["label"] = ""
        rows[2]["sample_id"] = " "
        write_manifest(path, rows)
        body = dict(self.body, synthetic=False, model_id="fixture-model", manifest="fixture-dataset/manifest.csv")
        with mock.patch.object(api, "load_catalog", return_value=catalog):
            result = api.experiment_preview(body)
        self.assertEqual(result["plan"]["state"], "blocked")
        self.assertTrue({"identity_whitespace", "missing_label", "missing_sample_id"} <= {f["code"] for f in result["audit"]["findings"]})


class WorkspaceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "runs"
        self.root.mkdir()

    def _record(self):
        record = dataclasses.asdict(ExperimentRecord(
            id="fixture-run/comparison-1", path="transfer_learning", task="SYNTHETIC task", cohort="SYNTHETIC cohort",
            split="SYNTHETIC split", model="fixture@revision", source_revision="fixture-revision", environment={"device": "none"},
            preprocessing={}, objective="software fixture", metrics=[], seed_policy="0", execution_scope="SYNTHETIC only",
            state=JobState.COMPLETED, outputs=["predictions/comparison-1.json"], blockers=["unresolved fixture evidence"]))
        folder = self.root / "fixture-run"
        folder.mkdir()
        (folder / "records.json").write_text(json.dumps([record]))
        return record

    def test_existing_experiment_records_preserve_scope_outputs_and_blockers(self):
        expected = self._record()
        listing = workspace.history(self.root)
        self.assertEqual(listing["items"][0]["state"], "completed")
        self.assertIsNone(listing["items"][0]["synthetic"])
        detail = workspace.detail(self.root, listing["items"][0]["key"])
        self.assertEqual(detail["record"], expected)
        self.assertIn("does not establish", detail["note"])

    def test_bad_files_do_not_hide_valid_records(self):
        self._record()
        for name, data in (("bad-json", "{not json"), ("wrong-shape", "{}"), ("nonfinite", '[{"id":NaN}]'),
                           ("nested", "[" * 2000 + "]" * 2000)):
            folder = self.root / name; folder.mkdir()
            (folder / "records.json").write_text(data)
        listing = workspace.history(self.root)
        self.assertEqual(len(listing["items"]), 1)
        self.assertEqual(len(listing["warnings"]), 4)

    def test_path_keys_and_external_symlinks_are_refused(self):
        outside = self.root.parent / "outside"; outside.mkdir()
        (outside / "records.json").write_text("[]")
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        for key in ("run:../outside:0", "run:linked:0", "run:folder:-1", "draft:../../outside", "draft:" + "f" * 31):
            with self.subTest(key=key), self.assertRaises((ValueError, FileNotFoundError)):
                workspace.detail(self.root, key)
        self.assertTrue(workspace.history(self.root)["warnings"])

    def test_history_and_file_limits_are_explicit(self):
        self._record()
        with mock.patch.object(workspace, "MAX_FILE_BYTES", 10):
            listing = workspace.history(self.root)
            self.assertFalse(listing["items"])
            self.assertTrue(listing["warnings"])

    def test_colliding_draft_never_overwrites_and_reserved_fields_are_server_owned(self):
        preview = {"id": "client-id", "kind": "client-kind", "plan": {"state": "blocked", "execution_authorized": False}}
        with mock.patch.object(workspace.uuid, "uuid4", return_value=mock.Mock(hex="a" * 32)):
            result = workspace.save_draft(self.root, preview, source_revision="fixture")
            self.assertEqual(result["draft"]["id"], "a" * 32)
            with self.assertRaises(FileExistsError):
                workspace.save_draft(self.root, preview, source_revision="other")
        self.assertEqual(workspace.detail(self.root, result["key"])["record"]["source_revision"], "fixture")

    def test_authorized_or_malformed_saved_draft_is_refused(self):
        with self.assertRaises(ValueError):
            workspace.save_draft(self.root, {"plan": {"state": "authorized", "execution_authorized": True}}, source_revision="x")
        folder = self.root / "drafts"; folder.mkdir()
        (folder / ("b" * 32 + ".json")).write_text("[]")
        self.assertTrue(workspace.history(self.root)["warnings"])
        with self.assertRaises(ValueError):
            workspace.detail(self.root, "draft:" + "b" * 32)

    def test_recent_draft_remains_visible_when_history_is_capped(self):
        self._record()
        os.utime(self.root / "fixture-run" / "records.json", (1, 1))
        result = workspace.save_draft(self.root, {"plan": {"state": "blocked", "execution_authorized": False}}, source_revision="fixture")
        with mock.patch.object(workspace, "MAX_HISTORY_ITEMS", 1):
            listing = workspace.history(self.root)
        self.assertEqual(listing["items"][0]["key"], result["key"])
        self.assertTrue(listing["warnings"])

    def test_malformed_files_consume_the_aggregate_read_budget(self):
        for name in ("first", "second"):
            folder = self.root / name; folder.mkdir()
            (folder / "records.json").write_text("{broken!!")
        with mock.patch.object(workspace, "MAX_HISTORY_BYTES", 10), mock.patch.object(workspace, "_read_json", wraps=workspace._read_json) as reader:
            listing = workspace.history(self.root)
        self.assertEqual(reader.call_count, 1)
        self.assertTrue(any("byte-preview limit" in w for w in listing["warnings"]))


if __name__ == "__main__":
    unittest.main()
