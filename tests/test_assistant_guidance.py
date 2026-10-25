import copy
import unittest
from unittest import mock

from cancer_workbench.app import api
from cancer_workbench.app.assistant import guided_history
from cancer_workbench.coordinator import ChatResult, ScriptedProvider


class AssistantGuidanceTests(unittest.TestCase):
    def test_existing_conversation_refreshes_context_without_mutating_history(self):
        source = [{"role": "system", "content": "Original instructions"},
                  {"role": "user", "content": "Earlier question"}]
        before = copy.deepcopy(source)
        once = guided_history(source, synthetic=True)
        twice = guided_history(once, synthetic=False)
        self.assertEqual(source, before)
        self.assertEqual(twice[1:], source[1:])
        self.assertTrue(twice[0]["content"].startswith("Original instructions"))
        self.assertEqual(twice[0]["content"].count("Current workbench interface:"), 1)
        self.assertIn("synthetic test specialist is disabled", twice[0]["content"])
        self.assertNotIn("specialist is enabled", twice[0]["content"])

    def test_app_request_supplies_current_interface_limits_to_provider(self):
        provider = ScriptedProvider([ChatResult("Use Images for JPEG/PNG.", [], "stop", "test", "test")], profile="test")
        provider.model = "test"
        with mock.patch.object(api, "make_provider", return_value=provider), mock.patch.object(api.research, "tool_registration", return_value=([], {})):
            result = api.ask({"question": "What should I upload?", "profiles": ["test"]})
        prompt = provider.calls[0]["messages"][0]["content"]
        self.assertIn("no image, MRI or blood-report attachment path", prompt)
        self.assertIn("registers no medical specialist adapters", prompt)
        self.assertIn("DICOM/NIfTI", prompt)
        self.assertEqual(result["results"][0]["final"], "Use Images for JPEG/PNG.")

    def test_synthetic_demo_is_identified_without_promoting_medical_tools(self):
        provider = ScriptedProvider([ChatResult("Synthetic only.", [], "stop", "test", "test")], profile="test")
        provider.model = "test"
        with mock.patch.object(api, "make_provider", return_value=provider), mock.patch.object(api.research, "tool_registration", return_value=([], {})):
            api.ask({"question": "What can run?", "profiles": ["test"], "synthetic_demo": True})
        prompt = provider.calls[0]["messages"][0]["content"]
        self.assertIn("fake test outputs only", prompt)
        self.assertIn("registers no medical specialist adapters", prompt)


if __name__ == "__main__":
    unittest.main()
