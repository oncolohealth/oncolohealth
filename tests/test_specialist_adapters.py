"""Installed specialist adapters and the run_specialist path. SYNTHETIC inputs only.

The default tests use temporary folders and never load weights. The opt-in class
(CW_MODEL_TESTS=1, ml extra, fetched weights) runs the real encoders on a
SYNTHETIC uploaded image through the coordinator's own tool call.
"""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cancer_workbench.adapters.installed import (ENCODER_ADAPTERS, SEMANTICS, adapter_status, installed_adapters,
                                                 resolve_image_ref)
from cancer_workbench.coordinator import default_toolbox
from cancer_workbench.registry import load_catalog
from cancer_workbench.routing import route_models

ENABLED = os.environ.get("CW_MODEL_TESTS") == "1"
HAS_ML = all(importlib.util.find_spec(m) for m in ("torch", "timm", "transformers", "safetensors", "PIL", "numpy"))
BONE = {"task": "feature_extraction", "modality": "xray", "anatomy": "bone"}


def _data_dir(root: Path, sha: str | None = None) -> Path:
    """A fake data folder with a one-row BTXRD manifest and one SYNTHETIC upload."""
    data = root / "data"
    images = data / "btxrd" / "BTXRD" / "BTXRD" / "images"
    images.mkdir(parents=True)
    raw = b"SYNTHETIC not really a jpeg"
    (images / "IMG000001.jpeg").write_bytes(raw)
    declared = hashlib.sha256(raw).hexdigest() if sha is None else sha
    (data / "btxrd" / "manifest.csv").write_text(f"sample_id,file,sha256\nIMG000001,images/IMG000001.jpeg,{declared}\n")
    (data / "uploads").mkdir()
    (data / "uploads" / "0123456789abcdef.png").write_bytes(b"SYNTHETIC")
    return data


class ImageRefTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = _data_dir(Path(self.temp.name))

    def test_resolves_btxrd_and_uploads_inside_the_data_folder(self):
        path, rel = resolve_image_ref("btxrd:IMG000001", self.data)
        self.assertEqual(rel, "btxrd/BTXRD/BTXRD/images/IMG000001.jpeg")
        self.assertTrue(path.is_file())
        self.assertEqual(resolve_image_ref("uploads:0123456789abcdef", self.data)[1], "uploads/0123456789abcdef.png")

    def test_refuses_paths_unknown_ids_and_other_schemes(self):
        for ref in ("../../etc/passwd", "/etc/passwd", "btxrd:../x", "btxrd:IMG999999", "uploads:missing", "file:IMG000001", None, 7):
            with self.assertRaises(ValueError, msg=ref):
                resolve_image_ref(ref, self.data)

    def test_refuses_a_file_that_differs_from_its_declared_hash(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        data = _data_dir(other, sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            resolve_image_ref("btxrd:IMG000001", data)


class InstalledAdapterTests(unittest.TestCase):
    def test_missing_weights_are_not_installed(self):
        models = load_catalog().models
        with tempfile.TemporaryDirectory() as empty:
            status = adapter_status(models, Path(empty))
            self.assertEqual(set(status), set(ENCODER_ADAPTERS))
            self.assertTrue(all(not s["installed"] and any("model.safetensors missing" in r for r in s["reasons"])
                                for s in status.values()))
            self.assertEqual(installed_adapters(models, Path(empty)), {})

    def test_router_blocks_named_but_uninstalled_adapters(self):
        models = load_catalog().models
        res = route_models(BONE, models, installed=set())
        blocked = {c["id"]: c["blockers"] for c in res["compatible"] if c["id"] in ("rad-dino", "resnet50-a1-in1k")}
        self.assertEqual(len(blocked), 2)
        self.assertTrue(all(any("not installed in this process" in b for b in bl) for bl in blocked.values()))
        installed = route_models(BONE, models, installed=set(ENCODER_ADAPTERS))
        self.assertEqual({c["id"] for c in installed["compatible"] if c["runnable"]}, {"rad-dino", "resnet50-a1-in1k"})

    def test_run_specialist_without_installed_adapter_is_an_observed_rejection(self):
        box = default_toolbox(load_catalog(), {})
        out = box.call("run_specialist", json.dumps({"model_id": "rad-dino", **BONE, "inputs": {"image": "btxrd:IMG000001"}}))
        env = out["result"]
        self.assertEqual(env["status"], "rejected")
        self.assertEqual(env["errors"], ["adapter 'frozen-encoder:rad-dino' is not installed in this process"])
        self.assertIsNone(env["outputs"])

    def test_app_endpoint_uses_the_tool_path_and_logs_the_envelope(self):
        from cancer_workbench.app import api

        with tempfile.TemporaryDirectory() as log, mock.patch.object(api, "SPECIALIST_LOG", Path(log)), \
                mock.patch.object(api, "installed_adapters", lambda models: {}):
            out = api.specialist_run({"model_id": "resnet50-a1-in1k", **BONE, "inputs": {"image": "btxrd:IMG000001"}})
            self.assertEqual(out["tool"], "run_specialist")
            self.assertEqual(out["result"]["status"], "rejected")
            logged = list(Path(log).glob("*.json"))
            self.assertEqual(len(logged), 1)
            self.assertEqual(json.loads(logged[0].read_text())["result"]["run_id"], out["result"]["run_id"])
            with self.assertRaises(api.ApiError):
                api.specialist_run({"model_id": "rad-dino", "surprise": 1})


class CatalogPromotionTests(unittest.TestCase):
    def test_only_reviewed_encoders_are_runnable_and_reuse_stays_unreviewed(self):
        models = {m["id"]: m for m in load_catalog().models}
        runnable = {i for i, m in models.items() if m["evidence_state"] in ("runnable", "locally_reproduced")}
        self.assertEqual(runnable, {"rad-dino", "resnet50-a1-in1k"})
        for i in runnable:
            m = models[i]
            self.assertEqual(m["adapter"], f"frozen-encoder:{i}")
            self.assertEqual(m["outputs"]["type"], "embedding")
            terms = m["terms_review"]
            self.assertEqual(terms["inference"]["status"], "allowed")
            self.assertTrue(terms["inference"]["evidence"].strip())
            self.assertIn("not", terms["inference"]["scope"].lower())  # states what it is not for
            for path in ("adaptation", "redistribution", "distillation"):
                self.assertEqual(terms[path]["status"], "unreviewed")
            for path in ("transfer_learning", "distillation"):
                self.assertNotEqual(m["reuse_permissions"][path]["status"], "allowed")


@unittest.skipUnless(ENABLED and HAS_ML, "set CW_MODEL_TESTS=1 with the ml extra installed and the weights fetched")
class RealSpecialistTests(unittest.TestCase):
    def test_real_encoders_return_bound_embeddings_through_run_specialist(self):
        from PIL import Image

        from cancer_workbench.adapters.encoder import FrozenEncoderAdapter
        from cancer_workbench.common.paths import MODELS_DIR

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "uploads").mkdir()
            img = data / "uploads" / "00000000000000aa.png"
            Image.linear_gradient("L").resize((640, 480)).save(img)  # SYNTHETIC gradient
            cat = load_catalog()
            box = default_toolbox(cat, installed_adapters(cat.models, data_dir=data))
            for model_id, dim in (("resnet50-a1-in1k", 2048), ("rad-dino", 768)):
                out = box.call("run_specialist", json.dumps({"model_id": model_id, **BONE,
                                                             "inputs": {"image": "uploads:00000000000000aa", "return_vector": True}}))
                env = out["result"]
                self.assertEqual(env["status"], "ok", env["errors"])
                o = env["outputs"]
                self.assertEqual((o["type"], o["dim"], o["semantics"]), ("embedding", dim, SEMANTICS))
                prov = json.loads((MODELS_DIR / model_id / "PROVENANCE.json").read_text())
                weights = next(f for f in prov["files"] if f["path"] == "model.safetensors")
                self.assertEqual(o["encoder"]["weights"]["sha256"], weights["sha256"])
                self.assertEqual(o["input"]["sha256"], hashlib.sha256(img.read_bytes()).hexdigest())
                direct = FrozenEncoderAdapter(model_id).embed([img], batch_size=1)[0]
                self.assertEqual([float(x) for x in direct], o["embedding"])


if __name__ == "__main__":
    unittest.main()
