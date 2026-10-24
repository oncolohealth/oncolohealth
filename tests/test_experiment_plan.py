"""SYNTHETIC plan records only; no model or workload is executed."""
import copy
import unittest

from cancer_workbench.experiments.plan import plan_experiment


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.model = {"id": "SYNTHETIC", "acquisition": {"revision": "a" * 40},
                      "evidence_state": "locally_reproduced", "inference_permission": "allowed",
                      "adapter": "synthetic", "reuse_permissions": {
                          p: {"status": "allowed", "evidence": "SYNTHETIC reviewed fixture"}
                          for p in ("transfer_learning", "distillation")}}
        self.audit = {"dataset_id": "SYNTHETIC", "rows": 12, "ready_for_training": True, "findings": []}
        self.budget = {"used_bytes": 10, "planned_bytes": 20, "limit_bytes": 30}

    def plan(self, path="transfer_learning", **kwargs):
        return plan_experiment(path, kwargs.get("model", self.model), kwargs.get("audit", self.audit),
                               kwargs.get("budget", self.budget))

    def test_three_paths_are_drafts_and_inputs_unchanged(self):
        before = copy.deepcopy((self.model, self.audit, self.budget))
        for path in ("specialist_tools", "transfer_learning", "distillation"):
            result = self.plan(path)
            self.assertEqual(result["state"], "ready_for_review")
            self.assertFalse(result["execution_authorized"])
        self.assertEqual((self.model, self.audit, self.budget), before)

    def test_unknown_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.plan("auto_train")

    def test_catalog_only_model_cannot_be_planned_for_execution(self):
        result = self.plan("specialist_tools", model=dict(self.model, evidence_state="cataloged", adapter=None))
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(any("adapter" in b for b in result["blockers"]))

    def test_inference_rights_do_not_imply_adaptation_or_distillation_rights(self):
        model = dict(self.model, reuse_permissions={})
        for path in ("transfer_learning", "distillation"):
            self.assertEqual(self.plan(path, model=model)["state"], "blocked")
        model["reuse_permissions"] = {"transfer_learning": {"status": "allowed", "evidence": " "}}
        self.assertEqual(self.plan(model=model)["state"], "blocked")

    def test_mutable_revision_is_blocked(self):
        self.assertEqual(self.plan(model=dict(self.model, acquisition={"revision": "main"}))["state"], "blocked")

    def test_partial_patient_ids_block_even_when_audit_boolean_is_true(self):
        self.audit["findings"] = [{"severity": "warning", "code": "missing_patient_id"}]
        self.assertIn("dataset audit: missing_patient_id", self.plan()["blockers"])

    def test_audit_errors_unresolved_and_missing_audit_block(self):
        for audit in (None, {}, dict(self.audit, rows=0), dict(self.audit, ready_for_training=False),
                      dict(self.audit, findings=[{"severity": "error", "code": "patient_leakage"}]),
                      dict(self.audit, findings=[{"severity": "warning", "code": "unresolved_evidence"}])):
            with self.subTest(audit=audit):
                self.assertEqual(self.plan(audit=audit)["state"], "blocked")

    def test_missing_invalid_and_exceeded_budget_block(self):
        for budget in (None, {}, dict(self.budget, planned_bytes=21), dict(self.budget, used_bytes=-1),
                       dict(self.budget, planned_bytes=float("nan")), dict(self.budget, limit_bytes=True)):
            with self.subTest(budget=budget):
                self.assertEqual(self.plan(budget=budget)["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
