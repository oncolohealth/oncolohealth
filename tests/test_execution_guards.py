"""SYNTHETIC regressions for checks before fitting or invoking tool handlers."""
import importlib.util
import json
import unittest
from unittest.mock import Mock, patch

from cancer_workbench.adapters import SYNTHETIC_MODEL_RECORD, execute_specialist
from cancer_workbench.common import ResultStatus
from cancer_workbench.coordinator.tools import Tool, ToolBox

HAS_ML = all(importlib.util.find_spec(m) for m in ("numpy", "sklearn"))


class AdapterValidationFailureTests(unittest.TestCase):
    def test_validation_exception_preserves_failed_envelope(self):
        adapter = Mock(synthetic=True)
        adapter.validate.side_effect = ValueError("unreadable synthetic input")
        request = {"task": "synthetic_classification", "modality": "synthetic", "anatomy": "any",
                   "inputs": {}, "input_refs": ["synthetic:broken"]}
        result = execute_specialist(SYNTHETIC_MODEL_RECORD, request, {"synthetic-threshold": adapter})
        self.assertEqual(result.status, ResultStatus.FAILED)
        self.assertEqual(result.input_refs, request["input_refs"])
        self.assertEqual(result.model_id, SYNTHETIC_MODEL_RECORD["id"])
        self.assertTrue(result.synthetic)
        self.assertIsNone(result.outputs)
        self.assertIn("input validation failed: ValueError", result.errors[0])
        adapter.run.assert_not_called()


class ToolArgumentGuardTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock(return_value={"origin": "synthetic"})
        self.schema = {"type": "object", "properties": {
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
            "kind": {"type": "string", "enum": ["model", "dataset"]},
            "config": {"type": "object", "required": ["ids"], "additionalProperties": False,
                       "properties": {"ids": {"type": "array", "minItems": 1, "maxItems": 2,
                                              "items": {"type": "string", "minLength": 1}}}},
            "payload": {"type": "object"}}, "required": ["count", "kind", "config"]}
        self.box = ToolBox([Tool("guarded", "synthetic handler", self.schema, self.handler)])
        self.args = {"count": 2, "kind": "model", "config": {"ids": ["a"]}}

    def rejected(self, args, message):
        result = self.box.call("guarded", json.dumps(args))
        self.assertIn(message, result["error"])
        self.handler.assert_not_called()

    def test_valid_arguments_reach_handler_unchanged(self):
        self.args["payload"] = {"free": [1, True, None]}
        self.assertEqual(self.box.call("guarded", json.dumps(self.args)), {"result": {"origin": "synthetic"}})
        self.handler.assert_called_once_with(**self.args)

    def test_boolean_and_fraction_do_not_pass_integer(self):
        for value in (True, 1.5, "2", None):
            with self.subTest(value=value):
                self.rejected(dict(self.args, count=value), "arguments.count must have type integer")

    def test_enum_rejected_before_handler(self):
        self.rejected(dict(self.args, kind="anything"), "arguments.kind must be one of")

    def test_nested_item_reports_path(self):
        self.rejected(dict(self.args, config={"ids": [3]}), "arguments.config.ids[0]")

    def test_nested_required_and_unknown_properties(self):
        for config, message in (({}, "missing required"), ({"ids": ["a"], "extra": 1}, "unknown arguments")):
            with self.subTest(config=config):
                self.rejected(dict(self.args, config=config), message)

    def test_bounds_and_lengths(self):
        for count in (0, 6):
            self.rejected(dict(self.args, count=count), "violates")
        for ids in ([], ["a", "b", "c"], [""]):
            self.rejected(dict(self.args, config={"ids": ids}), "violates")

    def test_nonfinite_numbers_in_open_payload_are_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            self.rejected(dict(self.args, payload={"nested": [value]}), "must be finite")

    def test_existing_top_level_closed_contract(self):
        self.rejected(dict(self.args, injected=True), "unknown arguments")

    def test_boolean_does_not_match_numeric_enum(self):
        box = ToolBox([Tool("enum", "synthetic", {"type": "object", "properties": {"x": {"enum": [1]}}}, self.handler)])
        self.assertIn("error", box.call("enum", '{"x": true}'))
        self.handler.assert_not_called()


@unittest.skipUnless(HAS_ML, "needs numpy and scikit-learn")
class HeadInputGuardTests(unittest.TestCase):
    def data(self):
        import numpy as np

        return {"features": np.array([[0., 1.], [1., 0.], [0., 2.], [2., 0.], [0., 3.], [3., 0.]]),
                "labels": np.array(["n", "p"] * 3), "classes": ["n", "p"],
                "partitions": np.array(["train", "train", "val", "val", "test", "test"]),
                "sample_ids": np.array(["a", "b", "c", "d", "e", "f"]),
                "patient_ids": np.array([""] * 6),
                "encoder": {"encoder_id": "synthetic", "revision": "0", "preprocessing_hash": "0"}}

    def rejected_before_fit(self, data, message, **options):
        from cancer_workbench.learning.heads import train_feature_head

        with patch("sklearn.linear_model.LogisticRegression") as learner:
            with self.assertRaisesRegex(ValueError, message):
                train_feature_head(data, **options)
            learner.assert_not_called()

    def test_sample_identity_overlap_blocks_selection(self):
        data = self.data()
        data["sample_ids"][2] = data["sample_ids"][0]
        self.rejected_before_fit(data, "sample_ids must be unique")

    def test_patient_and_duplicate_overlap_blocks_selection(self):
        import numpy as np

        for key in ("patient_ids", "duplicate_groups", "image_hashes"):
            data = self.data()
            data[key] = np.array(["same", "", "same", "", "", ""])
            with self.subTest(key=key):
                self.rejected_before_fit(data, key + " overlap")

    def test_validation_class_coverage_blocks_selection(self):
        data = self.data()
        data["labels"][3] = "n"
        self.rejected_before_fit(data, "val rows do not cover every class")

    def test_invalid_shapes_lengths_and_numeric_values(self):
        import numpy as np

        changes = [
            ("features", np.ones(6), "N x D"), ("features", np.ones((6, 0)), "N x D"),
            ("features", np.ones((6, 2), dtype=complex), "real numeric"),
            ("features", np.full((6, 2), np.nan), "finite"),
            ("features", np.full((6, 2), np.inf), "finite"),
            ("labels", np.array(["n"]), "aligned"),
            ("sample_ids", np.array([["a"]] * 6), "one-dimensional"),
            ("patient_ids", np.array([None] * 6), "strings"),
            ("classes", ["n", "n"], "unique"),
            ("encoder", {"encoder_id": "synthetic"}, "encoder must declare"),
            ("partitions", np.array(["train", "train", "unassigned", "val", "test", "test"]), "partitions must"),
        ]
        for key, value, message in changes:
            with self.subTest(key=key, message=message):
                self.rejected_before_fit(dict(self.data(), **{key: value}), message)

    def test_invalid_regularization_grid_blocks_fitting(self):
        for grid in (None, 1.0, [], [0], [-1], [True], [float("nan")], [float("inf")], ["1"]):
            with self.subTest(grid=grid):
                self.rejected_before_fit(self.data(), "c_grid", c_grid=grid)

    def test_repeated_known_group_within_one_partition_is_allowed(self):
        import numpy as np

        from cancer_workbench.learning.heads import evaluate_head, train_feature_head

        data = self.data()
        data["patient_ids"] = np.array(["train-a", "train-a", "val-a", "val-a", "", ""])
        head = train_feature_head(data, c_grid=[1.0])
        self.assertEqual(evaluate_head(head, data)["sample_ids"], ["e", "f"])

    def test_manifest_identity_metadata_reaches_head_inputs(self):
        import numpy as np

        from cancer_workbench.experiments.btxrd_baseline import head_inputs

        rows = [{"sample_id": "a", "label": "normal", "partition": "train", "patient_id": "",
                 "duplicate_group": "dup", "sha256": "hash"}]
        features = {"features": np.ones((1, 2)), "encoder_id": "synthetic", "revision": "0", "preprocessing_hash": "0"}
        inputs = head_inputs(rows, features, {"a": 0}, "three_class")
        self.assertEqual(inputs["duplicate_groups"].tolist(), ["dup"])
        self.assertEqual(inputs["image_hashes"].tolist(), ["hash"])


if __name__ == "__main__":
    unittest.main()
