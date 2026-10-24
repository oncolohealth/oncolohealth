"""SYNTHETIC provenance and mocked embeddings. No ML dependency or inference."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cancer_workbench.adapters import encoder
from helpers import write_processor_config


class _Vector:
    shape = (2,)

    def tolist(self):
        return [0.1, 0.2]


class EncoderProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.default = self.root / "default"
        self.custom = self.root / "custom"
        self.write(self.default, {"source": {"revision": "default-fixture"}})
        self.write(self.custom, {"source": {"revision": "custom-fixture"}})

    def write(self, base, value):
        folder = base / "rad-dino"; folder.mkdir(parents=True, exist_ok=True)
        (folder / "PROVENANCE.json").write_text(json.dumps(value))
        (folder / "model.safetensors").write_bytes(b"SYNTHETIC bytes, not real model weights")
        (folder / "config.json").write_text('{"synthetic":true}')
        write_processor_config(folder, "rad-dino")

    def test_old_helper_call_and_explicit_custom_folder_are_distinct(self):
        with mock.patch.object(encoder, "MODELS_DIR", self.default):
            self.assertEqual(encoder.revision("rad-dino"), "default-fixture")
            self.assertEqual(encoder.revision("rad-dino", self.custom), "custom-fixture")

    def test_custom_run_reports_the_loading_folder(self):
        adapter = encoder.FrozenEncoderAdapter("rad-dino", models_dir=self.custom)
        with mock.patch.object(encoder, "MODELS_DIR", self.default), mock.patch.object(adapter, "embed", return_value=[_Vector()]) as embed:
            result = adapter.run({"image_path": "SYNTHETIC-unused"})
        self.assertEqual(result["revision"], "custom-fixture")
        self.assertEqual(embed.call_count, 1)

    def test_missing_custom_provenance_stays_unknown(self):
        (self.custom / "rad-dino" / "PROVENANCE.json").unlink()
        adapter = encoder.FrozenEncoderAdapter("rad-dino", models_dir=self.custom)
        with mock.patch.object(encoder, "MODELS_DIR", self.default), mock.patch.object(adapter, "embed", return_value=[_Vector()]):
            self.assertIsNone(adapter.run({"image_path": "SYNTHETIC-unused"})["revision"])

    def test_malformed_custom_json_stops_before_embedding(self):
        (self.custom / "rad-dino" / "PROVENANCE.json").write_text("{not json")
        adapter = encoder.FrozenEncoderAdapter("rad-dino", models_dir=self.custom)
        with mock.patch.object(adapter, "embed") as embed, self.assertRaises(ValueError):
            adapter.run({"image_path": "SYNTHETIC-unused"})
        embed.assert_not_called()

    def test_malformed_shapes_and_revision_types_are_refused(self):
        for value in ([], {}, {"source": []}, {"source": {"revision": 12}}, {"source": {"revision": " "}}):
            self.write(self.custom, value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                encoder.revision("rad-dino", self.custom)

    def test_default_constructor_resolves_the_current_default_root(self):
        with mock.patch.object(encoder, "MODELS_DIR", self.default):
            adapter = encoder.FrozenEncoderAdapter("rad-dino")
        self.assertEqual(adapter.root, self.default / "rad-dino")

    def test_cached_model_cannot_be_relabelled_with_new_folder_metadata(self):
        from cancer_workbench.learning.provenance import model_identity
        adapter = encoder.FrozenEncoderAdapter("rad-dino", models_dir=self.custom)
        adapter._model = object()  # SYNTHETIC stand-in for an already loaded model
        adapter._loaded_identity = model_identity("rad-dino", models_dir=self.custom)
        self.write(self.custom, {"source": {"revision": "replacement-fixture"}})
        with mock.patch.object(adapter, "embed") as embed, self.assertRaisesRegex(ValueError,"Loaded encoder identity"):
            adapter.run({"image_path":"SYNTHETIC-unused"})
        embed.assert_not_called()

    def test_file_change_during_mock_embedding_publishes_no_result(self):
        adapter = encoder.FrozenEncoderAdapter("rad-dino", models_dir=self.custom)
        def embed(*a,**kw):
            (self.custom/"rad-dino"/"model.safetensors").write_bytes(b"SYNTHETIC replaced while embedding")
            return [_Vector()]
        with mock.patch.object(adapter,"embed",side_effect=embed),self.assertRaisesRegex(ValueError,"changed during embedding"):
            adapter.run({"image_path":"SYNTHETIC-unused"})


if __name__ == "__main__":
    unittest.main()
