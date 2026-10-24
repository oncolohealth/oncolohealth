import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from cancer_workbench.acquisition import IntegrityError, download, safe_extract_zip, verify
from helpers import LocalServer

PAYLOAD = b"synthetic-bytes-" * 5000


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.srv = LocalServer({"/f.bin": PAYLOAD})
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.srv.close()

    def test_download_verifies_md5_and_sha256(self):
        dest = download(self.srv.url + "/f.bin", self.tmp / "f.bin", size=len(PAYLOAD),
                        md5=hashlib.md5(PAYLOAD).hexdigest(), sha256=hashlib.sha256(PAYLOAD).hexdigest(), quiet=True)
        self.assertEqual(dest.read_bytes(), PAYLOAD)

    def test_resume_from_partial(self):
        (self.tmp / "f.bin.part").write_bytes(PAYLOAD[:1234])
        dest = download(self.srv.url + "/f.bin", self.tmp / "f.bin", size=len(PAYLOAD),
                        sha256=hashlib.sha256(PAYLOAD).hexdigest(), quiet=True)
        self.assertEqual(dest.read_bytes(), PAYLOAD)

    def test_checksum_mismatch_leaves_nothing(self):
        with self.assertRaises(IntegrityError):
            download(self.srv.url + "/f.bin", self.tmp / "f.bin", md5="0" * 32, quiet=True)
        self.assertFalse((self.tmp / "f.bin").exists())
        self.assertFalse((self.tmp / "f.bin.part").exists())

    def test_verify_reports_size_mismatch(self):
        p = self.tmp / "x"
        p.write_bytes(b"abc")
        self.assertTrue(verify(p, size=4))


class ZipSafetyTests(unittest.TestCase):
    def test_rejects_path_traversal(self):
        tmp = Path(tempfile.mkdtemp())
        z = tmp / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("../escape.txt", "x")
        with self.assertRaises(IntegrityError):
            safe_extract_zip(z, tmp / "out")
        self.assertFalse((tmp / "escape.txt").exists())

    def test_extracts_normal_archive(self):
        tmp = Path(tempfile.mkdtemp())
        z = tmp / "ok.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a/b.txt", "hello")
        safe_extract_zip(z, tmp / "out")
        self.assertEqual((tmp / "out/a/b.txt").read_text(), "hello")


if __name__ == "__main__":
    unittest.main()
