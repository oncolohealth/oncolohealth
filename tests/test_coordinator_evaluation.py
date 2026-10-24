import copy
import json
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.coordinator.evaluation import evaluate_suite, load_suite, scripted_provider
from cancer_workbench.coordinator.providers import ChatResult, ProviderError, ScriptedProvider


class CoordinatorEvaluationTests(unittest.TestCase):
    def test_smoke_checks_observed_outputs_without_a_reasoning_score(self):
        report = evaluate_suite(load_suite())
        self.assertEqual(report["summary"], {"cases": 8, "pass": 8, "fail": 0, "error": 0,
                                            "trace_pass_rate": None, "reasoning_quality_score": None})
        self.assertTrue(all(c["observed_result_fed_back"] for c in report["cases"]))
        self.assertTrue(all(c["answer_review"] == "unscored" for c in report["cases"]))
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False))["schema_version"], 1)

    def test_a_plausible_answer_without_tool_use_fails(self):
        def factory(case):
            return ScriptedProvider([ChatResult("I checked everything.", [], "stop", "fake", "fake")])
        report = evaluate_suite(load_suite(), mode="live", provider_factory=factory)
        self.assertEqual(report["summary"]["cases"], 6)
        self.assertEqual(report["summary"]["fail"], 6)
        self.assertEqual(report["summary"]["trace_pass_rate"], 0)

    def test_provider_error_retains_partial_tool_trace(self):
        case = load_suite()["cases"][0]

        class FailAfterTool:
            def __init__(self):
                self.source = scripted_provider(case)
                self.n = 0

            def chat(self, *args, **kwargs):
                self.n += 1
                if self.n == 2:
                    raise ProviderError("local fixture unavailable")
                return self.source.chat(*args, **kwargs)

        report = evaluate_suite(load_suite(), mode="live", provider_factory=lambda c: FailAfterTool(), limit=1)
        row = report["cases"][0]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error"]["type"], "ProviderError")
        self.assertEqual(len(row["calls"]), 1)
        self.assertTrue(row["checks"][0]["passed"])
        self.assertTrue(row["observed_result_fed_back"])
        self.assertEqual(report["summary"]["trace_pass_rate"], 0)

    def test_changed_expectation_is_not_scored_as_success(self):
        suite = copy.deepcopy(load_suite())
        suite["cases"][0]["expectations"][0]["equals"] = "invented"
        report = evaluate_suite(suite, limit=1)
        self.assertEqual(report["summary"]["fail"], 1)

    def test_step_limit_is_a_failure_even_if_tool_result_matches(self):
        row = evaluate_suite(load_suite(), max_steps=1, limit=1)["cases"][0]
        self.assertEqual(row["stopped"], "max_steps")
        self.assertEqual(row["status"], "fail")
        self.assertFalse(row["observed_result_fed_back"])

    def test_live_requires_explicit_provider_and_bounded_options(self):
        for kwargs in ({"mode": "live"}, {"max_steps": 0}, {"max_steps": True}, {"limit": 0}, {"limit": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                evaluate_suite(load_suite(), **kwargs)

    def test_invalid_fixture_version_and_duplicate_ids_are_rejected(self):
        suite = load_suite()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            for invalid in (dict(suite, schema_version=2), dict(suite, schema_version=True),
                            dict(suite, suite_id=""), [], dict(suite, cases=[suite["cases"][0]] * 2)):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    load_suite(path)


if __name__ == "__main__":
    unittest.main()
