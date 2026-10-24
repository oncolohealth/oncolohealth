"""Offline characterization of inspected baseline code; no weights or medical inputs.

Run with a source checkout argument. Tests confirm observed limitations, not fixes.
Only the synthetic pixel checks need Pillow. No dependency or network acquisition.
"""

import argparse
import ast
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_cache_guard(source):
    """Extract the actual cache-rejection expression without running a job."""
    tree = ast.parse(source.read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    candidates = [n.test for n in ast.walk(run) if isinstance(n, ast.If)
                  and any(isinstance(b, ast.Raise) for b in n.body)
                  and "f['preprocessing_hash']" in ast.unparse(n.test)]
    if len(candidates) != 1:
        raise ValueError("Expected one inspected cache guard")
    return compile(ast.Expression(candidates[0]), "<inspected-cache-guard>", "eval")


def pixel_stage(source):
    """Use the source's PIL stage, stopping before tensor creation or inference."""
    fn = copy.deepcopy(next(n for n in ast.parse(source.read_text()).body
                            if isinstance(n, ast.FunctionDef) and n.name == "load_image"))
    body = []
    for node in fn.body:
        if isinstance(node, ast.Import) and any(a.name == "torch" for a in node.names):
            continue
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "t" for t in node.targets):
            break
        body.append(node)
    fn.body = body + [ast.Return(ast.Name(id="canvas", ctx=ast.Load()))]
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    namespace = {"Path": Path, "_variant": ENCODER._variant}
    exec(compile(module, "<inspected-pixel-stage>", "exec"), namespace)
    return namespace["load_image"]


class InputReview(unittest.TestCase):
    def test_pinned_publisher_size_and_normalization_match_source_constants(self):
        rad, res = [r["configuration"] for r in MANIFEST["primary_sources"] if "configuration" in r]
        self.assertEqual(ENCODER.ENCODERS["rad-dino"]["size"], rad["size"]["shortest_edge"])
        self.assertEqual(ENCODER.ENCODERS["rad-dino"]["mean"], rad["image_mean"])
        self.assertEqual(ENCODER.ENCODERS["rad-dino"]["std"], rad["image_std"])
        cfg = res["pretrained_cfg"]
        self.assertEqual(ENCODER.ENCODERS["resnet50-a1-in1k"]["size"], cfg["test_input_size"][-1])
        self.assertEqual(ENCODER.ENCODERS["resnet50-a1-in1k"]["mean"], cfg["mean"])
        self.assertEqual(ENCODER.ENCODERS["resnet50-a1-in1k"]["std"], cfg["std"])

    def test_changed_source_bytes_keep_cache_name_and_pass_existing_guards(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ENCODER, "revision", return_value="a" * 40):
            image = Path(temp) / "synthetic-input.bin"
            image.write_bytes(b"synthetic original pixels")
            before = digest(image)
            name = FEATURES.cache_path("rad-dino", "btxrd", Path(temp))
            cached = {"revision": "a" * 40, "preprocessing_hash": ENCODER.preprocessing_hash("rad-dino")}
            image.write_bytes(b"synthetic replacement pixels")
            self.assertNotEqual(before, digest(image))
            self.assertEqual(name, FEATURES.cache_path("rad-dino", "btxrd", Path(temp)))
            env = {"f": cached, "enc": "rad-dino", "v": "pad", "str": str,
                   "preprocessing_hash": ENCODER.preprocessing_hash, "revision": ENCODER.revision}
            for relative in EXPERIMENTS:
                with self.subTest(experiment=relative):
                    self.assertFalse(eval(source_cache_guard(SOURCE / relative), {"__builtins__": {}}, env))

    def test_existing_guards_do_reject_a_changed_encoder_revision(self):
        with patch.object(ENCODER, "revision", return_value="a" * 40):
            env = {"f": {"revision": "b" * 40, "preprocessing_hash": ENCODER.preprocessing_hash("rad-dino")},
                   "enc": "rad-dino", "v": "pad", "str": str,
                   "preprocessing_hash": ENCODER.preprocessing_hash, "revision": ENCODER.revision}
            for relative in EXPERIMENTS:
                self.assertTrue(eval(source_cache_guard(SOURCE / relative), {"__builtins__": {}}, env))

    def test_custom_model_directory_result_uses_global_provenance(self):
        class SyntheticVector:
            shape = (768,)

            def tolist(self):
                return [0.0] * 768

        with tempfile.TemporaryDirectory() as temp:
            default, custom = Path(temp) / "default", Path(temp) / "custom"
            for root, revision in ((default, "a" * 40), (custom, "b" * 40)):
                folder = root / "rad-dino"
                folder.mkdir(parents=True)
                (folder / "PROVENANCE.json").write_text(json.dumps({"source": {"revision": revision}}))
            adapter = ENCODER.FrozenEncoderAdapter("rad-dino", models_dir=custom)
            with patch.object(ENCODER, "MODELS_DIR", default), patch.object(adapter, "embed", return_value=[SyntheticVector()]):
                result = adapter.run({"image_path": "synthetic-unused.jpeg"})
            self.assertEqual(adapter.root, custom / "rad-dino")
            self.assertEqual(result["revision"], "a" * 40)
            self.assertNotEqual(result["revision"], "b" * 40)

    def test_native_crop_source_pixel_stage_discards_a_synthetic_edge_marker(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Optional Pillow unavailable")
        with tempfile.TemporaryDirectory() as temp:
            image = Image.new("L", (90, 300), 0)
            ImageDraw.Draw(image).rectangle((35, 0, 55, 25), fill=255)
            path = Path(temp) / "synthetic.png"
            image.save(path)
            transform = pixel_stage(SOURCE / "cancer_workbench/adapters/encoder.py")
            padded, cropped = transform(path, 90, "pad"), transform(path, 90, "native_crop")
            self.assertGreater(padded.getextrema()[1], 0)
            self.assertEqual(cropped.getextrema()[1], 0)

    def test_native_crop_source_forces_grayscale_on_synthetic_rgb(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow unavailable")
        rad = MANIFEST["primary_sources"][0]["configuration"]
        self.assertTrue(rad["do_convert_rgb"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.png"
            Image.new("RGB", (90, 90), (255, 0, 0)).save(path)
            result = pixel_stage(SOURCE / "cancer_workbench/adapters/encoder.py")(path, 90, "native_crop")
            self.assertEqual(result.mode, "L")
            self.assertNotEqual(result.convert("RGB").getpixel((45, 45)), (255, 0, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Checkout matching the inspected source fingerprints")
    args = parser.parse_args()
    SOURCE = args.source.resolve()
    MANIFEST = json.loads(Path(__file__).with_name("BTXRD-baseline-input-review.json").read_text())
    for relative, expected in MANIFEST["shared_source_files"].items():
        if digest(SOURCE / relative) != expected:
            parser.error("Source fingerprint changed; review this characterization before reuse")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SOURCE))
    ENCODER = importlib.import_module("cancer_workbench.adapters.encoder")
    FEATURES = importlib.import_module("cancer_workbench.learning.features")
    EXPERIMENTS = ("cancer_workbench/experiments/btxrd_baseline.py",
                   "cancer_workbench/experiments/btxrd_source_shift.py")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InputReview))
    print(json.dumps({"scope": "Synthetic characterization of observed limitations; not regression fixes or medical validation",
                      "discovered": result.testsRun, "passed": result.testsRun - len(result.skipped) - len(result.errors) - len(result.failures),
                      "skipped": len(result.skipped), "failures": len(result.failures), "errors": len(result.errors)}))
    sys.exit(0 if result.wasSuccessful() else 1)
