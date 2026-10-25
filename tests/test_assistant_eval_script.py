import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assistant_eval.py"
spec = importlib.util.spec_from_file_location("assistant_eval", SCRIPT)
assistant_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assistant_eval)


class AssistantEvalChecks(unittest.TestCase):
    def test_cases_file_is_well_formed(self):
        cases = assistant_eval.load_cases()
        self.assertGreaterEqual(len(cases), 20)
        known = {"question", "id", "group", "attach", "slow", "expect_tools_any", "expect_tools_all",
                 "forbid_tools", "must_include_any", "must_include_all", "must_not_include"}
        for case in cases:
            self.assertTrue(case["question"].strip(), case["id"])
            self.assertLessEqual(set(case), known, case["id"])

    def test_pass_when_tools_and_phrases_match(self):
        case = {"expect_tools_any": ["route_models", "search_catalog"], "must_include_any": ["rad-dino"],
                "must_not_include": ["you have cancer"]}
        self.assertEqual(assistant_eval.check(case, "Try RAD-DINO.", ["search_catalog"], "answered", None), [])

    def test_reports_each_problem(self):
        case = {"expect_tools_all": ["run_specialist"], "forbid_tools": ["get_record"],
                "must_include_all": ["mit"], "must_not_include": ["you have cancer"]}
        problems = assistant_eval.check(case, "You have cancer.", ["get_record"], "max_steps", None)
        self.assertEqual(problems, ["stopped=max_steps", "did not call run_specialist", "called get_record",
                                    "missing 'mit'", "says 'you have cancer'"])

    def test_error_is_the_only_problem(self):
        self.assertEqual(assistant_eval.check({"must_include_all": ["x"]}, "", [], None, "boom"), ["error: boom"])

    def test_attachments_resolve_reserved_samples(self):
        case = {"attach": [{"sample": "m1", "workflow": True}, {"sample": "m2", "workflow": False}]}
        self.assertEqual(assistant_eval.attachments_for(case, {"m1": "a", "m2": "b"}),
                         [{"input_id": "a", "workflow_id": "m1"}, {"input_id": "b"}])
        with self.assertRaises(KeyError):
            assistant_eval.attachments_for({"attach": [{"sample": "missing"}]}, {})


if __name__ == "__main__":
    unittest.main()
