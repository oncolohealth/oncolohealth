import json
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from cancer_workbench.coordinator import (ChatResult, ProviderError, ScriptedProvider, ToolCall, default_toolbox,
                                          load_profiles, make_provider, run_turn)
from cancer_workbench.registry import load_catalog
from helpers import LocalServer


def _reply(content=None, calls=()):
    return ChatResult(content=content, tool_calls=list(calls), finish_reason="stop", model="scripted", profile="scripted")


class ToolLoopTests(unittest.TestCase):
    def setUp(self):
        self.box = default_toolbox(load_catalog(), {"synthetic-threshold": SyntheticThresholdAdapter()},
                                   extra_models=[SYNTHETIC_MODEL_RECORD])

    def test_observed_result_is_fed_back(self):
        args = json.dumps({"model_id": "synthetic-threshold-model", "task": "synthetic_classification",
                           "modality": "synthetic", "anatomy": "any", "inputs": {"signal": 0.9}})
        prov = ScriptedProvider([_reply(calls=[ToolCall("c1", "run_specialist", args)]), _reply("done")])
        rec = run_turn(prov, self.box, "run it")
        observed = rec.steps[0]["tool_calls"][0]["observed"]["result"]
        self.assertEqual(observed["status"], "ok")
        self.assertTrue(observed["synthetic"])
        tool_msg = prov.calls[1]["messages"][-1]
        self.assertEqual(tool_msg["role"], "tool")
        self.assertEqual(json.loads(tool_msg["content"])["result"]["run_id"], observed["run_id"])

    def test_unknown_tool_and_bad_args_return_errors(self):
        prov = ScriptedProvider([_reply(calls=[ToolCall("a", "make_diagnosis", "{}"), ToolCall("b", "get_record", "{not json")]),
                                 _reply("I could not do that.")])
        rec = run_turn(prov, self.box, "diagnose")
        obs = [c["observed"] for c in rec.steps[0]["tool_calls"]]
        self.assertIn("unknown tool", obs[0]["error"])
        self.assertIn("not valid JSON", obs[1]["error"])

    def test_catalog_only_model_is_rejected_via_tool(self):
        out = self.box.call("run_specialist", json.dumps({"model_id": "monai-brats-mri-segmentation", "task": "brain_tumor_segmentation",
                                                           "modality": "mri", "anatomy": "brain", "inputs": {}}))
        self.assertEqual(out["result"]["status"], "rejected")

    def test_max_steps(self):
        loop = [_reply(calls=[ToolCall(f"c{i}", "search_catalog", "{}")]) for i in range(3)]
        self.assertEqual(run_turn(ScriptedProvider(loop), self.box, "x", max_steps=3).stopped, "max_steps")


class OpenAICompatibleTests(unittest.TestCase):
    """Two profiles pointing at a fake OpenAI-compatible server serving two different models."""

    def setUp(self):
        self.seen = []

        def chat(handler, body):
            self.seen.append({"body": body, "auth": handler.headers.get("Authorization")})
            return 200, json.dumps({"model": body["model"], "choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": f"hello from {body['model']}"}}], "usage": {"total_tokens": 3}}).encode()

        models = json.dumps({"data": [{"id": "model-a"}, {"id": "model-b"}]}).encode()
        self.srv = LocalServer({"/v1/chat/completions": chat, "/v1/models": models})
        self.cfg = Path(tempfile.mkdtemp()) / "coordinator.json"
        self.cfg.write_text(json.dumps({"default_profile": "a", "profiles": {
            "a": {"base_url": self.srv.url + "/v1", "model": "model-a", "api_key_env": "CW_TEST_KEY", "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
            "b": {"base_url": self.srv.url + "/v1", "model": "model-b"},
            "down": {"base_url": "http://127.0.0.1:9/v1", "model": "x", "timeout_s": 2},
            "_comment": {"ignored": True}}}))

    def tearDown(self):
        self.srv.close()

    def test_profiles_hit_their_own_models(self):
        import os
        os.environ["CW_TEST_KEY"] = "secret"
        try:
            ra = make_provider("a", self.cfg).chat([{"role": "user", "content": "hi"}])
            rb = make_provider("b", self.cfg).chat([{"role": "user", "content": "hi"}])
        finally:
            del os.environ["CW_TEST_KEY"]
        self.assertEqual((ra.content, rb.content), ("hello from model-a", "hello from model-b"))
        self.assertEqual(self.seen[0]["body"]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(self.seen[0]["auth"], "Bearer secret")
        self.assertIsNone(self.seen[1]["auth"])

    def test_list_models_and_default_profile(self):
        self.assertEqual(make_provider(path=self.cfg).list_models(), ["model-a", "model-b"])
        self.assertNotIn("_comment", load_profiles(self.cfg)[0])

    def test_unreachable_endpoint_raises_provider_error(self):
        with self.assertRaises(ProviderError):
            make_provider("down", self.cfg).chat([{"role": "user", "content": "hi"}])

    def test_shipped_example_config_loads(self):
        profiles, default = load_profiles()
        self.assertIn(default, profiles)


if __name__ == "__main__":
    unittest.main()
