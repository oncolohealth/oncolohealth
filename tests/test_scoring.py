"""SYNTHETIC checks for asynchronous scoring and observed per-image progress."""
import copy
import hashlib
import importlib.util
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.app.scoring import ScoringJobs
from cancer_workbench.experiments import explore


def finished(jobs, job_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job["state"] != "running":
            return job
        time.sleep(0.005)
    raise AssertionError("Synthetic scoring worker did not finish")


class ScoringJobTests(unittest.TestCase):
    def test_observed_progress_is_isolated_and_second_batch_is_refused(self):
        jobs, ready, release = ScoringJobs(), threading.Event(), threading.Event()

        def work(update):
            items = [{"key": "synthetic:first", "refused": "Training image"}]
            update({"stage": "scoring", "done": 1, "current": "synthetic:second", "items": items})
            ready.set()
            if not release.wait(3):
                raise AssertionError("Test did not release the worker")
            items.append({"key": "synthetic:second", "probs": [0.2, 0.8]})
            return {"items": items}

        self.assertIsNone(jobs.current())
        started = jobs.start("synthetic", "head", 2, work, keys=["synthetic:first", "synthetic:second"])
        try:
            self.assertTrue(ready.wait(3))
            recovered = jobs.current()
            self.assertEqual(recovered["id"], started["id"])
            self.assertEqual(recovered["keys"], ["synthetic:first", "synthetic:second"])
            recovered["keys"].clear()
            self.assertEqual(len(jobs.current()["keys"]), 2)
            progress = jobs.get(started["id"])
            self.assertEqual((progress["done"], progress["current"]), (1, "synthetic:second"))
            progress["items"][0]["refused"] = "changed by caller"
            self.assertEqual(jobs.get(started["id"])["items"][0]["refused"], "Training image")
            with self.assertRaisesRegex(ValueError, "already running"):
                jobs.start("synthetic", "head", 1, work)
        finally:
            release.set()
        done = finished(jobs, started["id"])
        self.assertEqual((done["state"], done["done"], len(done["response"]["items"])), ("done", 2, 2))
        self.assertEqual(jobs.current(), done)

    def test_failure_preserves_completed_items(self):
        jobs = ScoringJobs()

        def work(update):
            update({"done": 1, "items": [{"key": "synthetic:first", "error": "Unreadable image"}]})
            raise RuntimeError("Synthetic classifier failure")

        job = jobs.start("synthetic", "head", 2, work)
        failed = finished(jobs, job["id"])
        self.assertEqual((failed["state"], failed["done"]), ("failed", 1))
        self.assertEqual(failed["items"][0]["error"], "Unreadable image")
        self.assertEqual(failed["error"], "Synthetic classifier failure")
        self.assertIsNone(failed["response"])

    def test_history_is_bounded_and_unknown_ids_are_explicit(self):
        jobs = ScoringJobs()
        first = None
        for _ in range(9):
            job = jobs.start("synthetic", "head", 1, lambda update: {"items": []})
            first = first or job["id"]
            finished(jobs, job["id"])
        with self.assertRaisesRegex(KeyError, "expired"):
            jobs.get(first)
        with mock.patch.object(api, "SCORES", jobs), self.assertRaises(api.ApiError) as caught:
            api.score_job("unknown")
        self.assertEqual(caught.exception.status, 404)


class ScoringApiTests(unittest.TestCase):
    def test_rejects_invalid_selection_before_work_starts(self):
        with mock.patch.object(api, "_ml_missing", return_value=[]), mock.patch.object(api.explore, "score") as score:
            for items in ([], [{}] * 25, "not a list", [None]):
                with self.subTest(items=items), self.assertRaises(api.ApiError):
                    api.start_score({"run": "synthetic", "result": "head", "items": items})
            score.assert_not_called()

    def test_start_resolves_images_and_passes_progress_to_scorer(self):
        jobs = ScoringJobs()
        body = {"run": "synthetic", "result": "head", "items": [{"set": "btxrd", "id": "S1"}]}

        def score(run, result, items, progress):
            self.assertEqual((run, result), ("synthetic", "head"))
            self.assertEqual(items[0]["key"], "btxrd:S1")
            self.assertEqual(items[0]["sample_id"], "S1")
            self.assertEqual(items[0]["path"], str(api.IMAGE_SETS["btxrd"]["root"] / "synthetic.png"))
            progress({"done": 1, "items": [{"key": "btxrd:S1", "refused": "Synthetic training image"}]})
            return {"items": [{"key": "btxrd:S1", "refused": "Synthetic training image"}]}

        with mock.patch.object(api, "SCORES", jobs), mock.patch.object(api, "_ml_missing", return_value=[]), \
                mock.patch.object(api, "read_manifest", return_value=[{"sample_id": "S1", "file": "synthetic.png"}]), \
                mock.patch.object(api.explore, "review"), mock.patch.object(api.explore, "score", side_effect=score):
            started = api.start_score(body)
            done = finished(jobs, started["id"])
            self.assertEqual(done["state"], "done", done["error"])
            self.assertIn("refused", done["items"][0])
            restored = api.GET_ROUTES["/api/score/current"]()["job"]
            self.assertEqual(restored["keys"], ["btxrd:S1"])
            self.assertEqual(restored["id"], started["id"])


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Optional ML extra is not installed")
class ScoringProgressTests(unittest.TestCase):
    def image_fixture(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "synthetic.bin"
        path.write_bytes(b"SYNTHETIC bytes, not an image")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_each_success_refusal_and_error_advances_progress(self):
        import numpy as np
        from cancer_workbench.adapters import encoder
        from cancer_workbench.learning import provenance
        path, source_sha = self.image_fixture()

        view = {"run": "synthetic", "result": "head", "encoder": "rad-dino", "variant": "pad", "classes": ["normal", "tumor"],
                "threshold": 0.6, "positive_class": "tumor", "label": "SYNTHETIC", "rows": {
                    "train": {"partition": "train", "label": "tumor"},
                    "val": {"partition": "val", "label": "tumor", "sha256": source_sha}}}
        head = SimpleNamespace(encoder={"encoder_id": "rad-dino", "revision": "synthetic", "preprocessing_hash": "synthetic",
                                        "model_fingerprint": "a" * 64, "feature_binding_sha256": "b" * 64}, classes=["normal", "tumor"],
                               train_ids={"train"}, mean=np.array([0.]), scale=np.array([1.]),
                               clf=SimpleNamespace(predict_proba=lambda features: np.array([[0.3, 0.7]])))
        adapter = SimpleNamespace(device="synthetic", embed=mock.Mock(side_effect=[np.array([[1.]]), ValueError("Bad synthetic image")]))
        items = [{"key": key, "sample_id": key, "path": path} for key in ("train", "val", "broken")]
        events = []
        with mock.patch.object(explore, "review", return_value=view), mock.patch.object(explore, "head_for", return_value=head), \
                mock.patch.dict(explore._ENCODERS, {("rad-dino", "pad", "a" * 64): adapter}, clear=True), \
                mock.patch.object(provenance, "model_identity", return_value={"revision":"synthetic", "preprocessing_hash":"synthetic", "sha256":"a" * 64}):
            result = explore.score("synthetic", "head", items, progress=lambda event: events.append(copy.deepcopy(event)))
        self.assertEqual([e["stage"] for e in events[:2]], ["preparing", "head"])
        self.assertEqual([e["done"] for e in events if e["stage"] == "scoring"], [0, 1, 1, 2, 2, 3])
        self.assertEqual([e["current"] for e in events if e["current"]], ["train", "val", "broken"])
        self.assertIn("refused", result["items"][0])
        self.assertTrue(result["items"][1]["correct"])
        self.assertIn("Validation image", result["items"][1]["notes"][0])
        self.assertIn("error", result["items"][2])
        self.assertEqual(events[-1]["items"], result["items"])
        self.assertEqual(events[-1]["metadata"]["device"], "synthetic")

    def test_variant_heads_score_with_their_own_preprocessing(self):
        import numpy as np
        from cancer_workbench.adapters import encoder
        from cancer_workbench.learning import provenance
        path, _ = self.image_fixture()

        view = {"run": "synthetic", "result": "head", "encoder": "rad-dino", "variant": "native_crop", "classes": ["normal", "tumor"],
                "threshold": 0.5, "positive_class": "tumor", "label": "SYNTHETIC", "rows": {}}
        head = lambda variant: SimpleNamespace(
            encoder={"encoder_id": "rad-dino", "revision": "synthetic", "preprocessing_hash": f"hash-{variant}",
                     "model_fingerprint": "a" * 64, "feature_binding_sha256": "b" * 64}, classes=["normal", "tumor"],
            train_ids=set(), mean=np.array([0.]), scale=np.array([1.]),
            clf=SimpleNamespace(predict_proba=lambda features: np.array([[0.2, 0.8]])))
        crop = SimpleNamespace(device="synthetic", embed=mock.Mock(return_value=np.array([[1.]])))
        pad = SimpleNamespace(device="synthetic", embed=mock.Mock(return_value=np.array([[1.]])))
        items = [{"key": "upload", "sample_id": None, "path": path}]
        with mock.patch.object(explore, "review", return_value=view), \
                mock.patch.dict(explore._ENCODERS, {("rad-dino", "native_crop", "a" * 64): crop, ("rad-dino", "pad", "a" * 64): pad}, clear=True), \
                mock.patch.object(provenance, "model_identity", side_effect=lambda enc, variant="pad": {"revision":"synthetic", "preprocessing_hash":f"hash-{variant}", "sha256":"a" * 64}):
            with mock.patch.object(explore, "head_for", return_value=head("native_crop")):
                result = explore.score("synthetic", "head", items)
            with mock.patch.object(explore, "head_for", return_value=head("pad")), self.assertRaises(ValueError):
                explore.score("synthetic", "head", items)  # SYNTHETIC: a pad head under a native_crop result
        self.assertEqual((result["variant"], result["items"][0]["pred"]), ("native_crop", "tumor"))
        crop.embed.assert_called_once()
        pad.embed.assert_not_called()


class RunListTests(unittest.TestCase):
    def test_runs_list_the_preprocessing_variant(self):
        import json
        import tempfile

        test = {"n": 1, "roc_auc": 0.5}
        results = [{"id": f"source_holdout.tumor_vs_normal.rad-dino.{v}", "protocol": "source_holdout", "endpoint": "tumor_vs_normal",
                    "encoder": "rad-dino", "counts": {}, "variant": v, "selected": v == "native_crop", "test": test}
                   for v in ("pad", "native_crop")]
        with tempfile.TemporaryDirectory() as d:  # SYNTHETIC run folders
            for name, res in (("synthetic-shift", results), ("synthetic-baseline", [dict(results[0], variant=None)])):
                (Path(d) / name).mkdir()
                (Path(d) / name / "results.json").write_text(json.dumps({"label": "SYNTHETIC", "results": res}))
            with mock.patch.object(explore, "RUNS_DIR", Path(d)):
                runs = {r["id"]: r for r in explore.list_runs()}
        self.assertEqual([(r["variant"], r["selected"]) for r in runs["synthetic-shift"]["results"]],
                         [("pad", False), ("native_crop", True)])
        self.assertIsNone(runs["synthetic-baseline"]["results"][0]["variant"])
        self.assertFalse(runs["synthetic-baseline"]["results"][0]["has_binding"])


@unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy for synthetic scoring fixtures")
class ScoringIdentityTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.bin"
        self.path.write_bytes(b"SYNTHETIC bytes, no pixels")
        self.model = {"revision":"synthetic", "preprocessing_hash":"synthetic", "sha256":"c" * 64}
        self.head = SimpleNamespace(encoder={"encoder_id":"rad-dino","revision":"synthetic","preprocessing_hash":"synthetic",
                                            "model_fingerprint":"c" * 64,"feature_binding_sha256":"b" * 64},
                                    classes=["normal","tumor"],train_ids=set(),mean=np.array([0.]),scale=np.array([1.]),
                                    clf=SimpleNamespace(predict_proba=lambda x: np.array([[.2,.8]])))
        self.view = {"run":"synthetic","result":"head","encoder":"rad-dino","variant":"pad","classes":["normal","tumor"],
                     "threshold":.5,"positive_class":"tumor","label":"SYNTHETIC","rows":{}}
        self.adapter = SimpleNamespace(device="SYNTHETIC",embed=mock.Mock(return_value=np.array([[1.]])))
        self.items = [{"key":"upload","sample_id":None,"path":self.path}]
        from cancer_workbench.adapters import encoder
        from cancer_workbench.learning import provenance
        patches = [mock.patch.object(explore,"review",return_value=self.view),mock.patch.object(explore,"head_for",return_value=self.head),
                   mock.patch.object(provenance,"model_identity",return_value=self.model),
                   mock.patch.dict(explore._ENCODERS,{},clear=True),mock.patch.object(encoder,"FrozenEncoderAdapter",return_value=self.adapter)]
        self.patches = []
        for patch in patches:
            self.patches.append(patch.start()); self.addCleanup(patch.stop)

    def test_legacy_head_stops_before_model_loading_or_embedding(self):
        del self.head.encoder["model_fingerprint"]
        with self.assertRaisesRegex(ValueError,"Legacy head"):
            explore.score("synthetic","head",self.items)
        self.patches[2].assert_not_called()
        self.adapter.embed.assert_not_called()

    def test_class_order_mismatch_stops_before_embedding(self):
        self.head.classes.reverse()
        with self.assertRaises(ValueError):
            explore.score("synthetic","head",self.items)
        self.adapter.embed.assert_not_called()

    def test_replacement_model_cannot_reuse_the_previous_loaded_adapter(self):
        old = SimpleNamespace(embed=mock.Mock())
        explore._ENCODERS[("rad-dino","pad","a"*64)] = old
        result = explore.score("synthetic","head",self.items)
        old.embed.assert_not_called()
        self.adapter.embed.assert_called_once()
        self.assertNotIn(("rad-dino","pad","a"*64),explore._ENCODERS)
        self.assertEqual(result["model_fingerprint"],"c"*64)

    def test_unmeasured_or_changed_run_image_is_refused_before_embedding(self):
        self.items[0]["sample_id"]="S0"
        for sha in (None,"f"*64):
            self.view["rows"]["S0"]={"partition":"test","label":"tumor","sha256":sha}
            result=explore.score("synthetic","head",self.items)
            self.assertIn("refused",result["items"][0])
            self.assertNotIn("probs",result["items"][0])
            self.assertEqual(result["items"][0]["source_sha256"],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.adapter.embed.assert_not_called()

    def test_image_change_during_embedding_preserves_an_error_instead_of_scores(self):
        def embed(*a,**kw):
            self.path.write_bytes(b"SYNTHETIC replacement while embedding")
            return self.np.array([[1.]])
        self.adapter.embed.side_effect=embed
        result=explore.score("synthetic","head",self.items)
        self.assertIn("changed during scoring",result["items"][0]["error"])
        self.assertNotIn("probs",result["items"][0])

    def test_model_change_during_batch_prevents_completed_response(self):
        self.patches[2].side_effect=[self.model,dict(self.model,sha256="d"*64)]
        with self.assertRaisesRegex(ValueError,"Model inputs changed"):
            explore.score("synthetic","head",self.items)
