"""Opt-in checks against the real local RAD-DINO and ResNet-50 files. Set CW_MODEL_TESTS=1 to run.

They load the actual weights (about 450 MB) and feed only SYNTHETIC images, never
medical pixels. Passing establishes byte identity with the recorded publisher
checksums, complete weight loading, publisher-processor agreement and stable
embeddings. It says nothing about medical validity.
"""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.adapters import encoder

ENABLED = os.environ.get("CW_MODEL_TESTS") == "1"
HAS_ML = all(importlib.util.find_spec(m) for m in ("torch", "timm", "transformers", "safetensors", "PIL", "numpy"))
# Synthetic shapes cover odd/even crop margins, portrait/landscape and an already-square input.
SHAPES = ((700, 500), (500, 701), (1000, 763), (288, 288), (517, 1333), (2000, 1999))


def synthetic_image(path: Path, width: int, height: int) -> Path:
    from PIL import Image, ImageDraw

    im = Image.linear_gradient("L").resize((width, height))  # SYNTHETIC gradient with sharp-edged shapes
    draw = ImageDraw.Draw(im)
    draw.ellipse((width // 4, height // 5, width * 2 // 3, height * 3 // 4), fill=230)
    draw.rectangle((width // 10, height * 3 // 5, width // 4, height * 9 // 10), fill=20)
    im.save(path)
    return path


@unittest.skipUnless(ENABLED and HAS_ML, "set CW_MODEL_TESTS=1 with the ml extra installed and the weights fetched")
class RealModelFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.images = [synthetic_image(Path(cls.temp.name) / f"s{w}x{h}.png", w, h) for w, h in SHAPES]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def root(self, encoder_id: str) -> Path:
        root = encoder.MODELS_DIR / encoder_id
        if not (root / "model.safetensors").is_file():
            self.fail(f"{root}/model.safetensors is missing; fetch {encoder_id} before running these checks")
        return root

    def test_every_file_matches_its_recorded_publisher_checksum(self):
        for encoder_id in encoder.ENCODERS:
            prov = json.loads((self.root(encoder_id) / "PROVENANCE.json").read_text())
            weights = next(f for f in prov["files"] if f["path"] == "model.safetensors")
            self.assertEqual(weights["integrity"], "publisher_checksum")
            for f in prov["files"]:
                with self.subTest(encoder=encoder_id, file=f["path"]):
                    data = (self.root(encoder_id) / f["path"]).read_bytes()
                    self.assertEqual(len(data), f["bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), f["sha256"])

    def test_weights_load_completely(self):
        import safetensors.torch
        from transformers import Dinov2Model

        _, info = Dinov2Model.from_pretrained(self.root("rad-dino"), local_files_only=True, use_safetensors=True,
                                              output_loading_info=True)
        for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"):
            self.assertIn(key, info)  # a renamed key must not pass silently
            self.assertFalse(info[key], f"RAD-DINO {key}: {info[key]}")
        stored = set(safetensors.torch.load_file(self.root("resnet50-a1-in1k") / "model.safetensors"))
        model = encoder._load_model("resnet50-a1-in1k", self.root("resnet50-a1-in1k"))  # strict=True inside
        self.assertEqual(stored - set(model.state_dict()), {"fc.weight", "fc.bias"})  # only the dropped classifier

    def test_native_crop_matches_the_publisher_processors(self):
        import timm
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor

        hf = AutoImageProcessor.from_pretrained(self.root("rad-dino"), local_files_only=True)
        cfg = json.loads((self.root("resnet50-a1-in1k") / "config.json").read_text())["pretrained_cfg"]
        tf = timm.data.create_transform(**timm.data.resolve_data_config({}, pretrained_cfg=cfg, use_test_size=True))
        publisher = {"rad-dino": lambda im: hf(images=im, return_tensors="pt")["pixel_values"][0], "resnet50-a1-in1k": tf}
        # transformers rescales after its own uint8 resize, so allow one 8-bit level; torchvision matches exactly
        tolerance = {"rad-dino": 1.01 / 255 / encoder.ENCODERS["rad-dino"]["std"][0], "resnet50-a1-in1k": 1e-6}
        for encoder_id, spec in encoder.ENCODERS.items():
            mean, std = torch.tensor(spec["mean"]).view(3, 1, 1), torch.tensor(spec["std"]).view(3, 1, 1)
            for path in self.images:
                with self.subTest(encoder=encoder_id, image=path.name), Image.open(path) as im:
                    ours = (encoder.load_image(path, spec["size"], "native_crop", spec["crop_offset"]) - mean) / std
                    theirs = publisher[encoder_id](im.convert("RGB"))
                    self.assertEqual(tuple(ours.shape), tuple(theirs.shape))
                    self.assertLessEqual(float((ours - theirs).abs().max()), tolerance[encoder_id])

    def test_embeddings_are_finite_repeatable_and_device_consistent(self):
        import numpy as np
        import torch

        for encoder_id, spec in encoder.ENCODERS.items():
            self.root(encoder_id)
            cpu = encoder.FrozenEncoderAdapter(encoder_id, device="cpu")
            a, b = cpu.embed(self.images[:2], batch_size=2), cpu.embed(self.images[:2], batch_size=1)
            with self.subTest(encoder=encoder_id, device="cpu"):
                self.assertEqual(a.shape, (2, spec["dim"]))
                self.assertTrue(np.isfinite(a).all())
                np.testing.assert_allclose(a, b, rtol=1e-4, atol=1e-4)  # batch size must not change features
            if torch.backends.mps.is_available():
                mps = encoder.FrozenEncoderAdapter(encoder_id, device="mps").embed(self.images[:2], batch_size=2)
                cosine = (a * mps).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(mps, axis=1))
                with self.subTest(encoder=encoder_id, device="mps"):
                    self.assertGreater(float(cosine.min()), 0.9999)


if __name__ == "__main__":
    unittest.main()
