"""Hosted compatibility tests against local SYNTHETIC HTTP fixtures only."""
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cancer_workbench.coordinator import ProviderError, default_toolbox, make_provider, run_turn
from cancer_workbench.coordinator.providers import OpenAICompatibleProvider
from cancer_workbench.registry import load_catalog
from helpers import LocalServer


class HostedProfileTests(unittest.TestCase):
    def test_tool_round_trip_and_workspace_header(self):
        seen = []

        def reply(handler, body):
            seen.append((dict(handler.headers), body))
            message = ({"role": "assistant", "content": None, "tool_calls": [{"id": "lookup", "type": "function",
                        "function": {"name": "get_record", "arguments": '{"id":"rad-dino"}'}}]}
                       if len(seen) == 1 else {"role": "assistant", "content": "Observed catalog result received."})
            return 200, json.dumps({"model": "synthetic-claude-fixture", "choices": [{"message": message,
                                   "finish_reason": "tool_calls" if len(seen) == 1 else "stop"}]}).encode()

        server = LocalServer({"/v1/chat/completions": reply})
        self.addCleanup(server.close)
        with tempfile.TemporaryDirectory() as folder:
            cfg = Path(folder) / "profiles.json"
            cfg.write_text(json.dumps({"default_profile": "claude-test", "profiles": {"claude-test": {
                "base_url": server.url + "/v1", "model": "synthetic-claude-fixture", "api_key_env": "CW_FIXTURE_KEY",
                "require_api_key": True, "extra_headers_env": {"anthropic-workspace-id": "CW_FIXTURE_WORKSPACE"},
                "default_params": {"max_tokens": 256}}}}))
            with patch.dict(os.environ, {"CW_FIXTURE_KEY": "synthetic-key", "CW_FIXTURE_WORKSPACE": "synthetic-workspace"}):
                record = run_turn(make_provider(path=cfg), default_toolbox(load_catalog()), "Look up RAD-DINO.")
            self.assertNotIn("synthetic-key", cfg.read_text())
        self.assertEqual(record.final, "Observed catalog result received.")
        self.assertEqual(seen[0][0]["Authorization"], "Bearer synthetic-key")
        self.assertEqual(seen[0][0]["Anthropic-Workspace-Id"], "synthetic-workspace")
        self.assertEqual(seen[0][1]["max_tokens"], 256)
        self.assertNotIn("temperature", seen[0][1])
        observed = json.loads(seen[1][1]["messages"][-1]["content"])
        self.assertEqual(observed["result"]["id"], "rad-dino")
        self.assertEqual(observed["result"]["evidence_state"], load_catalog().get("rad-dino")["evidence_state"])

    def test_missing_required_key_stops_before_network(self):
        provider = OpenAICompatibleProvider("fixture", "http://127.0.0.1:9/v1", "synthetic",
                                            api_key_env="CW_ABSENT_FIXTURE_KEY", require_api_key=True)
        with patch.dict(os.environ):
            os.environ.pop("CW_ABSENT_FIXTURE_KEY", None)
            with patch("urllib.request.build_opener") as transport:
                with self.assertRaisesRegex(ProviderError, "missing required credential"):
                    provider.chat([{"role": "user", "content": "synthetic"}])
                transport.assert_not_called()

    def test_optional_workspace_header_is_absent_when_unset(self):
        provider = OpenAICompatibleProvider("fixture", "http://127.0.0.1:9/v1", "synthetic",
                                            extra_headers_env={"anthropic-workspace-id": "CW_ABSENT_WORKSPACE"})
        with patch.dict(os.environ):
            os.environ.pop("CW_ABSENT_WORKSPACE", None)
            self.assertNotIn("anthropic-workspace-id", provider._headers())

    def test_reserved_or_invalid_headers_are_refused(self):
        for mapping in ({"Authorization": "CW_FIXTURE_KEY"}, {"Bad\r\nHeader": "X"}, {"x-test": "bad env"}):
            with self.subTest(mapping=mapping):
                provider = OpenAICompatibleProvider("fixture", "http://127.0.0.1:9/v1", "synthetic", extra_headers_env=mapping)
                with self.assertRaises(ProviderError):
                    provider._headers()
        provider = OpenAICompatibleProvider("fixture", "http://127.0.0.1:9/v1", "synthetic",
                                            extra_headers_env={"x-test": "CW_HEADER_FIXTURE"})
        with patch.dict(os.environ, {"CW_HEADER_FIXTURE": "bad\r\nvalue"}), self.assertRaises(ProviderError):
            provider._headers()

    def test_profile_save_preserves_environment_references(self):
        from cancer_workbench.app import api

        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "coordinator.json"
            cfg = {"profiles": {}, "default_profile": None}
            profile = {"base_url": "https://api.anthropic.com/v1", "model": "synthetic",
                       "api_key_env": "CW_FIXTURE_KEY", "require_api_key": True,
                       "extra_headers_env": {"anthropic-workspace-id": "CW_FIXTURE_WORKSPACE"}}
            with patch.object(api, "_local_config", return_value=(dest, cfg)), patch.object(api, "profiles", return_value={}):
                api.save_profile({"name": "claude-test", "profile": profile})
            saved = json.loads(dest.read_text())["profiles"]["claude-test"]
            self.assertEqual(saved["extra_headers_env"], profile["extra_headers_env"])
            self.assertTrue(saved["require_api_key"])


class RedirectBoundaryTests(unittest.TestCase):
    def redirect_server(self, location):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/v1/models":
                    self.send_response(302)
                    self.send_header("Location", location)
                    self.end_headers()
                else:
                    body = b'{"data":[{"id":"synthetic-model"}]}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1"

    def test_cross_origin_redirect_cannot_receive_credentials(self):
        reached = []
        target = LocalServer({"/stolen": lambda handler, body: (reached.append(dict(handler.headers)) or (200, b'{}'))})
        self.addCleanup(target.close)
        base = self.redirect_server(target.url + "/stolen")
        provider = OpenAICompatibleProvider("fixture", base, "synthetic", api_key_env="CW_REDIRECT_KEY")
        with patch.dict(os.environ, {"CW_REDIRECT_KEY": "synthetic-sensitive-value"}), self.assertRaisesRegex(ProviderError, "another origin"):
            provider.list_models()
        self.assertEqual(reached, [])

    def test_same_origin_redirect_remains_supported(self):
        base = self.redirect_server("/v1/final-models")
        self.assertEqual(OpenAICompatibleProvider("fixture", base, "synthetic").list_models(), ["synthetic-model"])


if __name__ == "__main__":
    unittest.main()
