import unittest

from cancer_workbench.adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter, execute_specialist
from cancer_workbench.common import ResultStatus
from cancer_workbench.registry import load_catalog, validate_model
from cancer_workbench.routing import route_models


class CatalogTests(unittest.TestCase):
    def test_shipped_catalog_is_valid(self):
        self.assertEqual(load_catalog().validate(), [])

    def test_nothing_shipped_is_runnable(self):
        # catalog-only models must never be reported runnable
        cat = load_catalog()
        res = route_models({"task": "feature_extraction", "modality": "xray", "anatomy": "bone"}, cat.models)
        self.assertTrue(res["compatible"])
        self.assertFalse(any(c["runnable"] for c in res["compatible"]))

    def test_runnable_state_requires_adapter(self):
        bad = dict(SYNTHETIC_MODEL_RECORD, adapter=None)
        self.assertTrue(any("requires an adapter" in e for e in validate_model(bad)))


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.models = load_catalog().models

    def test_missing_fields_error(self):
        self.assertIn("error", route_models({"task": "x"}, self.models))

    def test_brain_mri_routes_to_brats_only(self):
        res = route_models({"task": "brain_tumor_segmentation", "modality": "mri", "anatomy": "brain",
                            "input": {"channels": 4, "spatial_dims": 3}}, self.models)
        self.assertEqual([c["id"] for c in res["compatible"]], ["monai-brats-mri-segmentation"])

    def test_wrong_channels_rejected(self):
        res = route_models({"task": "brain_tumor_segmentation", "modality": "mri", "anatomy": "brain",
                            "input": {"channels": 1}}, self.models)
        self.assertEqual(res["compatible"], [])
        brats = next(r for r in res["rejected"] if r["id"] == "monai-brats-mri-segmentation")
        self.assertTrue(any("channels" in x for x in brats["reasons"]))


class ExecuteTests(unittest.TestCase):
    req = {"task": "synthetic_classification", "modality": "synthetic", "anatomy": "any", "inputs": {"signal": 0.8}}

    def test_ok_envelope_is_marked_synthetic(self):
        env = execute_specialist(SYNTHETIC_MODEL_RECORD, self.req, {"synthetic-threshold": SyntheticThresholdAdapter()})
        self.assertEqual(env.status, ResultStatus.OK)
        self.assertTrue(env.synthetic)
        self.assertEqual(env.outputs["scores"], [0.19999999999999996, 0.8])

    def test_catalog_only_model_cannot_execute(self):
        model = load_catalog().get("monai-brats-mri-segmentation")
        env = execute_specialist(model, {"task": "brain_tumor_segmentation", "modality": "mri", "anatomy": "brain"}, {})
        self.assertEqual(env.status, ResultStatus.REJECTED)
        self.assertIsNone(env.outputs)

    def test_missing_adapter_rejected(self):
        env = execute_specialist(SYNTHETIC_MODEL_RECORD, self.req, {})
        self.assertEqual(env.status, ResultStatus.REJECTED)

    def test_invalid_input_rejected(self):
        env = execute_specialist(SYNTHETIC_MODEL_RECORD, dict(self.req, inputs={"signal": 7}),
                                 {"synthetic-threshold": SyntheticThresholdAdapter()})
        self.assertEqual(env.status, ResultStatus.REJECTED)

    def test_adapter_failure_reported(self):
        env = execute_specialist(SYNTHETIC_MODEL_RECORD, self.req, {"synthetic-threshold": SyntheticThresholdAdapter(fail=True)})
        self.assertEqual(env.status, ResultStatus.FAILED)
        self.assertIn("configured to fail", env.errors[0])


if __name__ == "__main__":
    unittest.main()
