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


PNG_1PX = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def _synthetic_run(root: Path) -> str:
    """SYNTHETIC baseline run: 4 rows, one per partition, binary endpoint with a stored val threshold."""
    run = root / "btxrd-baseline-test"
    split = [{"sample_id": f"S{i}", "patient_id": "", "duplicate_group": "", "partition": p, "label": l, "label_derived": l,
              "file": "", "sha256": ""} for i, (p, l) in enumerate([("train", "malignant"), ("val", "benign"), ("test", "malignant"), ("test", "")])]
    from cancer_workbench.datasets import write_manifest

    write_manifest(run / "splits" / "image_stratified.csv", split)
    (run / "predictions").mkdir()
    (run / "predictions" / "r.json").write_text(json.dumps({
        "val": {"sample_ids": ["S1"], "y_true": [0], "probs": [[0.3, 0.7]]},
        "test": {"sample_ids": ["S2"], "y_true": [0], "probs": [[0.45, 0.55]]}}))
    (run / "results.json").write_text(json.dumps({"label": "EXPLORATORY", "results": [
        {"id": "r", "protocol": "image_stratified", "endpoint": "tumor_vs_normal", "encoder": "rad-dino", "counts": {},
         "test": {"roc_auc": 0.5, "threshold": 0.6}}]}))
    return run.name


class ImageApiTests(unittest.TestCase):
    def setUp(self):
        from unittest import mock

        self.tmp = Path(tempfile.mkdtemp())
        for target, value in ((api, "UPLOADS_DIR"), (api.explore, "RUNS_DIR")):
            p = mock.patch.object(target, value, self.tmp / value.lower())
            p.start()
            self.addCleanup(p.stop)

    def test_upload_checks_type_and_stores_by_hash(self):
        import base64

        with self.assertRaises(api.ApiError):
            api.upload({"name": "x.txt", "data": base64.b64encode(b"hello").decode()})
        meta = api.upload({"name": "dot.png", "data": base64.b64encode(PNG_1PX).decode()})
        self.assertEqual(meta["file"], meta["id"] + ".png")
        self.assertEqual([u["original_name"] for u in api.uploads()["uploads"]], ["dot.png"])
        self.assertEqual(api.media_file(f"uploads/{meta['file']}")[1], "image/png")
        api.delete_upload({"id": meta["id"]})
        self.assertEqual(api.uploads()["uploads"], [])

    def test_media_stays_inside_its_root(self):
        (self.tmp / "uploads_dir").mkdir()
        for rel in ("uploads/../../etc/passwd", "uploads/../uploads_dir", "nosuchset/a.png", "uploads/"):
            with self.assertRaises(api.ApiError):
                api.media_file(rel)

    def test_review_applies_the_val_threshold(self):
        name = _synthetic_run(api.explore.RUNS_DIR)
        rows = api.run_review({"run": name, "result": "r"})["rows"]
        self.assertEqual(rows["S2"]["pred"], "normal")  # P(tumor) 0.55 < threshold 0.6
        self.assertFalse(rows["S2"]["correct"])
        self.assertTrue(rows["S1"]["correct"])  # benign maps to tumor; 0.7 >= 0.6
        self.assertEqual(rows["S3"]["partition"], "excluded")
        self.assertNotIn("probs", rows["S0"])
        with self.assertRaises(api.ApiError):
            api.run_review({"run": "../" + name, "result": "r"})

    def test_live_score_needs_ml_extra(self):
        from unittest import mock

        with mock.patch.object(api, "_ml_missing", return_value=["torch"]), self.assertRaises(api.ApiError) as cm:
            api.live_score({"run": "x", "result": "y", "items": []})
        self.assertEqual(cm.exception.status, 409)


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

    def test_scoring_recovery_requires_token_and_unknown_job_is_404(self):
        from unittest import mock
        from cancer_workbench.app.scoring import ScoringJobs

        with mock.patch.object(api, "SCORES", ScoringJobs()):
            self.assertEqual(self._get("/api/score/current")[0], 403)
            self.assertEqual(self._get("/api/score/jobs/unknown")[0], 403)
            status, body = self._get("/api/score/current", {"X-CW-Token": "tok"})
            self.assertEqual((status, json.loads(body)), (200, {"job": None}))
            status, body = self._get("/api/score/jobs/unknown", {"X-CW-Token": "tok"})
            self.assertEqual(status, 404)
            self.assertIn("expired", json.loads(body)["error"])

    def test_foreign_host_rejected(self):
        self.assertEqual(self._get("/", {"Host": "attacker.example:80"})[0], 421)

    def test_media_requires_token(self):
        self.assertEqual(self._get("/media/btxrd/images/x.jpeg")[0], 403)
        self.assertEqual(self._get("/media/btxrd/../../etc/passwd?t=tok")[0], 404)

    def test_page_carries_token(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b'content="tok"', body)


if __name__ == "__main__":
    unittest.main()
