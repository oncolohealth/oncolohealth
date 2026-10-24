import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from cancer_workbench.app import api, progress_md
from cancer_workbench.app.server import make_handler

SAMPLE = """# PROGRESS

| WS | Focus | Module(s) | Depends on | Owner |
|---|---|---|---|---|
| A | Dataset curator | `datasets/` | none | |

## Phase 0
- [x] done thing
- [ ] open thing
- [ ] 🔒 blocked thing
"""


class ProgressFileTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "PROGRESS.md"
        self.path.write_text(SAMPLE)

    def test_parse_and_toggle(self):
        p = progress_md.parse(self.path)
        items = p["sections"][0]["items"]
        self.assertEqual([i["mark"] for i in items], ["x", " ", " "])
        self.assertTrue(items[2]["blocked"])
        progress_md.set_mark(items[1]["line"], items[1]["text"], "~", self.path)
        self.assertIn("- [~] open thing", self.path.read_text())

    def test_stale_edit_refused(self):
        items = progress_md.parse(self.path)["sections"][0]["items"]
        with self.assertRaises(ValueError):
            progress_md.set_mark(items[1]["line"], "something else", "x", self.path)

    def test_claim_owner(self):
        row = progress_md.parse(self.path)["owners"][0]
        progress_md.set_owner(row["line"], "A", "Sam", self.path)
        self.assertEqual(progress_md.parse(self.path)["owners"][0]["owner"], "Sam")


class ApiTests(unittest.TestCase):
    def test_synthetic_audit_finds_planted_leak(self):
        rep = api.audit({"synthetic": True})
        codes = {f["code"] for f in rep["findings"]}
        self.assertTrue(rep["synthetic"])
        self.assertIn("patient_leakage", codes)
        self.assertFalse(rep["ready_for_training"])

    def test_grouped_split_removes_leak(self):
        rep = api.split({"synthetic": True, "fractions": {"train": 0.7, "val": 0.15, "test": 0.15}, "seed": "1"})
        self.assertNotIn("patient_leakage", {f["code"] for f in rep["findings"]})

    def test_synthetic_split_cannot_be_saved(self):
        with self.assertRaises(api.ApiError):
            api.split({"synthetic": True, "fractions": {"train": 1}, "save": True})

    def test_manifest_path_must_stay_in_data_dir(self):
        with self.assertRaises(api.ApiError):
            api.audit({"path": "../../etc/passwd.csv"})

    def test_profile_rejects_inline_key(self):
        with self.assertRaises(api.ApiError):
            api.save_profile({"name": "x", "profile": {"base_url": "http://h/v1", "model": "m", "api_key": "sk-123"}})


class ServerGuardTests(unittest.TestCase):
    def setUp(self):
        import http.server
        import threading

        ref = {"port": 0}
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler("tok", ref))
        ref["port"] = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{ref['port']}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_api_requires_token(self):
        self.assertEqual(self._get("/api/storage")[0], 403)
        status, body = self._get("/api/storage", {"X-CW-Token": "tok"})
        self.assertEqual(status, 200)
        self.assertIn("budget", json.loads(body))

    def test_foreign_host_rejected(self):
        self.assertEqual(self._get("/", {"Host": "attacker.example:80"})[0], 421)

    def test_page_carries_token(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b'content="tok"', body)


if __name__ == "__main__":
    unittest.main()
