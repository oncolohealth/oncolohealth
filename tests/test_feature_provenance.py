"""Synthetic files and mocked embeddings. No model weights, medical pixels or inference."""
import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cancer_workbench.adapters import encoder
from cancer_workbench.learning import provenance
from helpers import symlink_or_skip, write_processor_config

ENC = "resnet50-a1-in1k"


class FileFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = self.root / "images"; self.images.mkdir()
        self.models = self.root / "models"; model = self.models / ENC; model.mkdir(parents=True)
        (model / "model.safetensors").write_bytes(b"SYNTHETIC weight bytes, not a model")
        write_processor_config(model, ENC)
        (model / "PROVENANCE.json").write_text(json.dumps({"source": {"revision": "a" * 40}}))
        self.rows = []
        for i in range(6):
            p = self.images / f"S{i}.bin"; p.write_bytes(f"SYNTHETIC image source {i}".encode())
            label = ("normal", "benign")[i % 2]
            self.rows.append({"sample_id": f"S{i}", "file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                              "patient_id": f"P{i}", "duplicate_group": "", "partition": ("train", "val", "test")[i // 2],
                              "label": label, "label_derived": label, "center": "1"})
        patch = mock.patch.object(encoder, "MODELS_DIR", self.models)
        patch.start(); self.addCleanup(patch.stop)


class MeasuredIdentityTests(FileFixtures):
    def test_source_order_and_labels_do_not_reassign_feature_identity(self):
        a = provenance.image_sources(self.rows, self.images)
        rows = [dict(r, label="other", patient_id="unreviewed") for r in reversed(self.rows)]
        self.assertEqual(a, provenance.image_sources(rows, self.images))
        self.assertEqual({r["sample_id"] for r in a["samples"]}, {r["sample_id"] for r in self.rows})

    def test_changed_bytes_refuse_a_stale_declared_hash(self):
        (self.images / self.rows[0]["file"]).write_bytes(b"SYNTHETIC changed bytes")
        with self.assertRaisesRegex(ValueError, "Declared image hash mismatch"):
            provenance.image_sources(self.rows, self.images)
        rows = [dict(r, sha256="") for r in self.rows]
        measured = provenance.image_sources(rows, self.images)
        self.assertNotEqual(measured["samples"][0]["sha256"], self.rows[0]["sha256"])

    def test_missing_and_ambiguous_samples_or_hashes_are_refused(self):
        for rows in ([], self.rows + [self.rows[0]], [dict(self.rows[0], sample_id=" ")],
                     [dict(self.rows[0], file="")], [dict(self.rows[0], sha256=0)], [dict(self.rows[0], sha256="bad")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                provenance.image_sources(rows, self.images)

    def test_source_paths_and_external_symlinks_do_not_escape(self):
        outside = self.root / "outside.bin"; outside.write_bytes(b"SYNTHETIC outside")
        for value in (str(outside), "../outside.bin"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                provenance.image_sources([dict(self.rows[0], file=value, sha256="")], self.images)
        with self.subTest(value="linked.bin"):
            symlink_or_skip(self, self.images / "linked.bin", outside)
            with self.assertRaises(ValueError):
                provenance.image_sources([dict(self.rows[0], file="linked.bin", sha256="")], self.images)

    def test_non_regular_source_is_refused_without_opening_it(self):
        with self.assertRaises(ValueError):
            provenance.measured_file(self.images)
        if hasattr(os, "mkfifo"):
            fifo = self.images / "pipe"; os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                provenance.measured_file(fifo)

    def test_weight_bytes_are_measured_even_when_revision_text_is_unchanged(self):
        a = provenance.model_identity(ENC)
        (self.models / ENC / "model.safetensors").write_bytes(b"SYNTHETIC replacement weights")
        b = provenance.model_identity(ENC)
        self.assertEqual(a["revision"], b["revision"])
        self.assertNotEqual(a["sha256"], b["sha256"])

    def test_processor_variant_implementation_and_library_identity_are_bound(self):
        a = provenance.model_identity(ENC)
        self.assertNotEqual(a["sha256"], provenance.model_identity(ENC, "native_crop")["sha256"])
        with mock.patch.object(encoder, "IMPLEMENTATION_SHA256", "d" * 64):
            self.assertNotEqual(a["sha256"], provenance.model_identity(ENC)["sha256"])
        with mock.patch.object(provenance.importlib.metadata, "version", return_value="SYNTHETIC new version"):
            self.assertNotEqual(a["sha256"], provenance.model_identity(ENC)["sha256"])

    def test_actual_dino_config_is_bound_and_missing_model_files_fail(self):
        folder = self.models / "rad-dino"; folder.mkdir()
        (folder / "model.safetensors").write_bytes(b"SYNTHETIC")
        with self.assertRaises(FileNotFoundError):
            provenance.model_identity("rad-dino")
        (folder / "config.json").write_text('{"synthetic":1}')
        with self.assertRaises(FileNotFoundError):
            provenance.model_identity("rad-dino")
        write_processor_config(folder, "rad-dino")
        a = provenance.model_identity("rad-dino")
        (folder / "config.json").write_text('{"synthetic":2}')
        self.assertNotEqual(a["sha256"], provenance.model_identity("rad-dino")["sha256"])

    def test_publisher_processor_file_is_bound_and_must_match_the_constants(self):
        path = self.models / ENC / "config.json"
        a = provenance.model_identity(ENC)
        self.assertEqual(a["publisher_preprocessing"]["size"], encoder.ENCODERS[ENC]["size"])
        value = json.loads(path.read_text()); value["SYNTHETIC_note"] = "same values, new bytes"
        path.write_text(json.dumps(value))
        self.assertNotEqual(a["sha256"], provenance.model_identity(ENC)["sha256"])
        for key, bad in (("mean", [0.5, 0.5, 0.5]), ("test_input_size", [3, 224, 224]), ("interpolation", "bilinear"),
                         ("test_crop_pct", 0.95)):
            changed = copy.deepcopy(value); changed["pretrained_cfg"][key] = bad
            path.write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "disagrees"):
                provenance.model_identity(ENC)
        for raw in ("{not json", "{}", '{"architecture": "resnet50", "pretrained_cfg": []}'):
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Malformed publisher processor"):
                provenance.model_identity(ENC)

    def test_dino_processor_resample_and_crop_are_checked(self):
        folder = self.models / "rad-dino"; folder.mkdir()
        (folder / "model.safetensors").write_bytes(b"SYNTHETIC"); (folder / "config.json").write_text('{"synthetic":1}')
        write_processor_config(folder, "rad-dino")
        path = folder / "preprocessor_config.json"
        value = json.loads(path.read_text())
        self.assertEqual(provenance.model_identity("rad-dino")["publisher_preprocessing"]["mean"], value["image_mean"])
        for key, bad in (("resample", 2), ("crop_size", {"height": 518, "width": 512}), ("do_normalize", False)):
            path.write_text(json.dumps(dict(value, **{key: bad})))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "disagrees"):
                provenance.model_identity("rad-dino")

    def test_model_file_external_symlink_is_refused(self):
        weight = self.models / ENC / "model.safetensors"
        outside = self.root / "outside-model"; outside.write_bytes(b"SYNTHETIC")
        weight.unlink(); symlink_or_skip(self, weight, outside)
        with self.assertRaises(ValueError):
            provenance.model_identity(ENC)

    def test_manifest_parse_and_hash_use_the_same_snapshot_bytes(self):
        raw = b"sample_id,file,label\r\nS0,S0.bin,normal\r\n"
        path = self.root / "manifest.csv"; path.write_bytes(raw)
        rows, sha = provenance.manifest_snapshot(path)
        self.assertEqual(rows[0]["sample_id"], "S0")
        self.assertEqual(sha, hashlib.sha256(raw).hexdigest())
        path.write_text("sample_id,file,file\ns,a,b\n")
        with self.assertRaises(ValueError):
            provenance.manifest_snapshot(path)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy for synthetic feature arrays")
class BoundFeatureTests(FileFixtures):
    def setUp(self):
        super().setUp()
        import numpy as np
        from cancer_workbench.learning import features
        self.np, self.features = np, features
        spec = dict(encoder.ENCODERS[ENC], dim=3)  # SYNTHETIC dimension, no real encoder instantiated
        patch = mock.patch.dict(encoder.ENCODERS, {ENC: spec}); patch.start(); self.addCleanup(patch.stop)
        self.adapter = SimpleNamespace(device="SYNTHETIC", embed=mock.Mock(return_value=np.arange(18, dtype=np.float32).reshape(6, 3)))
        patch = mock.patch.object(encoder, "FrozenEncoderAdapter", return_value=self.adapter); patch.start(); self.addCleanup(patch.stop)
        self.path = self.root / "features.npz"

    def extract(self):
        self.features.extract_features(ENC, self.rows, self.images, self.path, quiet=True)
        return self.features.load_features(self.path)

    def test_bound_cache_round_trip_and_payload_alignment(self):
        f = self.extract()
        bound = provenance.feature_binding(ENC, self.rows, self.images)
        self.features.validate_feature_binding(f, bound)
        self.assertEqual(f["model_fingerprint"], bound["model"]["sha256"])
        self.assertEqual(f["feature_binding_sha256"], bound["sha256"])

    def test_legacy_or_mutated_payload_and_sample_alignment_are_refused(self):
        f = self.extract(); expected = provenance.feature_binding(ENC, self.rows, self.images)
        mutated = copy.deepcopy(f); mutated["features"][0,0] += 1
        wrong_ids = copy.deepcopy(f); wrong_ids["sample_ids"] = wrong_ids["sample_ids"][::-1]
        for bad in ({k:v for k,v in f.items() if k!="source_binding"}, mutated, wrong_ids,
                    dict(f, model_fingerprint="f" * 64), dict(f, source_binding="[]")):
            with self.subTest(keys=bad.keys()), self.assertRaises(ValueError):
                self.features.validate_feature_binding(bad, expected)

    def test_new_bound_filename_does_not_reuse_or_overwrite_legacy_cache(self):
        legacy = self.features.cache_path(ENC, "btxrd", self.root)
        legacy.write_bytes(b"SYNTHETIC legacy file")
        f, path = self.features.ensure_features(ENC, self.rows, self.images, self.root)
        self.assertNotEqual(path, legacy)
        self.assertEqual(legacy.read_bytes(), b"SYNTHETIC legacy file")
        self.features.ensure_features(ENC, self.rows, self.images, self.root)
        self.assertEqual(self.adapter.embed.call_count, 1)

    def test_review_cache_lookup_never_extracts_and_rejects_legacy_or_changed_inputs(self):
        legacy = self.features.cache_path(ENC, "btxrd", self.root)
        legacy.write_bytes(b"SYNTHETIC unbound cache")
        with self.assertRaisesRegex(FileNotFoundError, "Legacy caches"):
            self.features.existing_features(ENC, self.rows, self.images, self.root)
        self.adapter.embed.assert_not_called()
        f, path = self.features.ensure_features(ENC, self.rows, self.images, self.root)
        self.adapter.embed.reset_mock()
        verified, selected = self.features.existing_features(ENC, self.rows, self.images, self.root)
        self.assertEqual(selected, path)
        self.assertEqual(f["feature_binding_sha256"], verified["feature_binding_sha256"])
        (self.images / self.rows[0]["file"]).write_bytes(b"SYNTHETIC replacement")
        with self.assertRaises(ValueError):
            self.features.existing_features(ENC, self.rows, self.images, self.root)
        with self.assertRaises(FileNotFoundError):
            self.features.existing_features(ENC, [dict(r, sha256="") for r in self.rows], self.images, self.root)
        self.adapter.embed.assert_not_called()

    def test_write_failure_preserves_existing_cache_and_cleans_temporary_file(self):
        self.path.write_bytes(b"SYNTHETIC previous cache")
        with mock.patch.object(self.np, "savez", side_effect=OSError("SYNTHETIC write failure")), self.assertRaises(OSError):
            self.extract()
        self.assertEqual(self.path.read_bytes(), b"SYNTHETIC previous cache")
        self.assertFalse(list(self.root.glob(".feature-*")))

    def test_near_duplicate_review_refuses_legacy_or_stale_cache_before_ranking(self):
        from cancer_workbench.datasets import write_manifest
        from cancer_workbench.experiments import btxrd_near_duplicates as near
        manifest = self.root / "manifest.csv"; write_manifest(manifest, self.rows)
        with mock.patch.object(near, "MANIFEST_PATH", manifest), mock.patch.object(near, "RAW_DIR", self.images), \
             mock.patch.object(near, "ENCODERS", [ENC]), mock.patch.object(near, "pair_scores") as rank:
            legacy = self.features.cache_path(ENC, "btxrd", self.root)
            legacy.write_bytes(b"SYNTHETIC old cache")
            with self.assertRaises(FileNotFoundError):
                near.run(top=1, features_dir=self.root, out_dir=self.root/"review")
            self.features.ensure_features(ENC, self.rows, self.images, self.root)
            (self.images / self.rows[0]["file"]).write_bytes(b"SYNTHETIC stale source")
            with self.assertRaisesRegex(ValueError, "Declared image hash mismatch"):
                near.run(top=1, features_dir=self.root, out_dir=self.root/"review")
        rank.assert_not_called()
        self.assertFalse((self.root/"review").exists())

    def test_near_duplicate_pair_count_does_not_emit_self_pairs_or_infinite_scores(self):
        from cancer_workbench.experiments.btxrd_near_duplicates import pair_scores
        f = self.np.ones((3, 2))
        for top in (0, -1, 4, True, 1.5):
            with self.subTest(top=top), self.assertRaises(ValueError):
                pair_scores([f], top)
        pairs, _ = pair_scores([f], 3)
        self.assertEqual(len(pairs), 3)
        self.assertTrue(all(a < b and self.np.isfinite(score) for a,b,score,_ in pairs))

    def test_source_or_model_change_during_extraction_publishes_no_cache(self):
        for target in (self.images / self.rows[0]["file"], self.models / ENC / "model.safetensors"):
            original = target.read_bytes()
            def embed(*args, **kwargs):
                target.write_bytes(b"SYNTHETIC changed during embedding")
                return self.np.ones((6,3), dtype=self.np.float32)
            self.adapter.embed.side_effect = embed
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.features.extract_features(ENC, self.rows, self.images, self.path, quiet=True)
            self.assertFalse(self.path.exists())
            self.assertFalse(list(self.root.glob(".feature-*")))
            target.write_bytes(original)

    def test_bad_embedding_shape_or_values_are_not_published(self):
        for array in (self.np.zeros((5,3)), self.np.zeros((6,2)), self.np.full((6,3), self.np.nan)):
            self.adapter.embed.return_value = array
            with self.subTest(shape=array.shape), self.assertRaises(ValueError):
                self.features.extract_features(ENC, self.rows, self.images, self.path, quiet=True)
            self.assertFalse(self.path.exists())

    def test_both_runners_stop_before_fit_when_source_bytes_change(self):
        from cancer_workbench.datasets import write_manifest
        from cancer_workbench.experiments import btxrd_baseline, btxrd_source_shift
        from cancer_workbench.learning import heads
        self.features.ensure_features(ENC, self.rows, self.images, self.root / "cache")
        manifest = self.root / "manifest.csv"; write_manifest(manifest, self.rows)
        (self.images / self.rows[0]["file"]).write_bytes(b"SYNTHETIC changed")
        for module, kwargs in ((btxrd_baseline, {"protocols":["image_stratified"]}), (btxrd_source_shift, {"variants":["pad"]})):
            with mock.patch.object(module, "MANIFEST_PATH", manifest), mock.patch.object(module, "RAW_DIR", self.images), \
                 mock.patch.object(heads, "train_feature_head") as fit, self.assertRaisesRegex(ValueError, "Declared image hash mismatch"):
                module.run(encoders=[ENC], endpoints=["tumor_vs_normal"], features_dir=self.root/"cache", out_dir=self.root/module.__name__.split('.')[-1], **kwargs)
            fit.assert_not_called()

    def test_measured_source_hashes_are_kept_for_later_arms(self):
        rows = [dict(r, sha256="") for r in self.rows]
        f = self.extract()
        measured = self.features.bound_source_rows(rows, f)
        self.assertTrue(all(provenance.valid_sha(r["sha256"]) for r in measured))
        self.assertTrue(all(r["sha256"] == "" for r in rows))
        (self.images / rows[0]["file"]).write_bytes(b"SYNTHETIC replacement between arms")
        with self.assertRaises(ValueError):
            self.features.ensure_features(ENC, measured, self.images, self.root/"other-arm")

    def test_refit_refuses_changed_sources_and_legacy_metadata_before_fitting(self):
        from cancer_workbench.datasets import btxrd, write_manifest
        from cancer_workbench.experiments import explore
        from cancer_workbench.learning import heads
        cache = self.root / "runs" / "features"
        f, path = self.features.ensure_features(ENC, self.rows, self.images, cache)
        run = self.root / "runs" / "synthetic-run"
        write_manifest(run/"splits"/"image_stratified.csv", self.rows)
        result = {"id":"head", "protocol":"image_stratified", "endpoint":"tumor_vs_normal", "encoder":ENC,
                  "feature_cache":path.name, "feature_binding_sha256":f["feature_binding_sha256"]}
        (self.images/self.rows[0]["file"]).write_bytes(b"SYNTHETIC changed")
        with mock.patch.object(explore,"RUNS_DIR",self.root/"runs"), mock.patch.object(btxrd,"RAW_DIR",self.images), \
             mock.patch.object(heads,"train_feature_head") as fit:
            with self.assertRaises(ValueError):
                explore._refit(run,result)
            with self.assertRaisesRegex(ValueError,"Legacy run"):
                explore._refit(run,{k:v for k,v in result.items() if k!="feature_binding_sha256"})
        fit.assert_not_called()

    def test_source_shift_keeps_the_correct_binding_for_each_variant(self):
        from cancer_workbench.datasets import write_manifest
        from cancer_workbench.experiments import btxrd_source_shift as shift
        from cancer_workbench.learning import heads
        manifest=self.root/"manifest.csv";write_manifest(manifest,self.rows)
        def ensured(enc,rows,root,cache,variant="pad"):
            f=self.features.load_features(self.path)
            f["feature_binding_sha256"]=("b" if variant=="pad" else "c")*64
            return f, Path(cache)/(variant+".npz")
        self.extract()
        def trained(data):
            return SimpleNamespace(C=1.,val_score=.6 if data["encoder"]["feature_binding_sha256"]=="c"*64 else .5)
        with mock.patch.object(shift,"MANIFEST_PATH",manifest), mock.patch.object(shift,"RAW_DIR",self.images), \
             mock.patch.object(shift,"make_split",side_effect=lambda rows,*a,**kw:rows), \
             mock.patch.object(self.features,"ensure_features",side_effect=ensured), \
             mock.patch.object(heads,"train_feature_head",side_effect=trained), mock.patch.object(heads,"head_fingerprint",return_value="d"*64), \
             mock.patch.object(heads,"save_head"), mock.patch.object(shift,"record",return_value={}), \
             mock.patch.object(shift,"summary",return_value="SYNTHETIC metadata fixture"), \
             mock.patch.object(shift,"evaluate",return_value=({}, {}, {"roc_auc":.5,"roc_auc_ci95":None,"sensitivity":.7,"specificity":.8,"positive_class":"tumor"})):
            out=shift.run(encoders=[ENC],endpoints=["tumor_vs_normal"],variants=["pad","native_crop"],out_dir=self.root/"shift",features_dir=self.root/"cache")
        results=json.loads((out/"results.json").read_text())["results"]
        self.assertEqual([(r["variant"],r["feature_cache"],r["feature_binding_sha256"])for r in results],
                         [("pad","pad.npz","b"*64),("native_crop","native_crop.npz","c"*64)])


@unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy for synthetic head arrays")
class SavedHeadIdentityTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from cancer_workbench.learning import heads
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.heads=heads
        self.head=heads.HeadModel(encoder={"encoder_id":ENC,"revision":"a"*40,"preprocessing_hash":"synthetic",
                                          "model_fingerprint":"a"*64,"feature_binding_sha256":"b"*64},
                                  classes=["normal","tumor"],C=1,val_score=.5,mean=np.array([0.]),scale=np.array([1.]),
                                  clf=heads._LinearProbs(np.array([[1.]]),np.array([0.])),train_ids=frozenset({"S0"}),train_patients=frozenset({"P0"}))

    def test_fitted_identity_survives_save_load_and_changes_with_arrays_or_classes(self):
        path=self.root/"head.npz"; before=self.heads.head_fingerprint(self.head)
        self.heads.save_head(self.head,path)
        self.assertEqual(before,self.heads.head_fingerprint(self.heads.load_head(path)))
        changed=copy.deepcopy(self.head);changed.clf.coef_[0,0]+=1
        self.assertNotEqual(before,self.heads.head_fingerprint(changed))
        changed=copy.deepcopy(self.head);changed.classes.reverse()
        self.assertNotEqual(before,self.heads.head_fingerprint(changed))

    def test_head_file_replacement_cannot_reuse_a_cached_head(self):
        from cancer_workbench.experiments import explore
        run=self.root/"synthetic-run";(run/"heads").mkdir(parents=True)
        result={"id":"head","feature_binding_sha256":"b"*64,"head_fingerprint":self.heads.head_fingerprint(self.head)}
        (run/"results.json").write_text(json.dumps({"results":[result]}))
        path=run/"heads"/"head.npz";self.heads.save_head(self.head,path)
        with mock.patch.object(explore,"RUNS_DIR",self.root),mock.patch.dict(explore._HEADS,{},clear=True):
            self.assertEqual(explore.head_for(run.name,"head").classes,["normal","tumor"])
            self.head.mean[0]=1.;self.heads.save_head(self.head,path)
            with self.assertRaisesRegex(ValueError,"Saved head"):
                explore.head_for(run.name,"head")

    def test_legacy_result_is_not_promoted_to_bound_head(self):
        from cancer_workbench.experiments import explore
        run=self.root/"legacy";run.mkdir()
        (run/"results.json").write_text(json.dumps({"results":[{"id":"head"}]}))
        with mock.patch.object(explore,"RUNS_DIR",self.root),mock.patch.object(self.heads,"load_head")as load:
            with self.assertRaisesRegex(ValueError,"Legacy"):
                explore.head_for(run.name,"head")
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
