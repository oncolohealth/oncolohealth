import hashlib
import importlib
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from cancer_workbench.acquisition import IntegrityError, budget, download, safe_extract_zip, verify
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


dl = importlib.import_module("cancer_workbench.acquisition.download")  # the package exports a function of the same name
V6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0))
V6B = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::2", 443, 0, 0))
V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))


class FakeSocket:
    """SYNTHETIC socket: IPv6 connects time out, IPv4 connects succeed. Records every attempt."""
    log: list = []

    def __init__(self, family, kind, proto):
        self.family, self.timeouts = family, []

    def settimeout(self, t):
        self.timeouts.append(t)

    def connect(self, addr):
        FakeSocket.log.append((addr[0], self.timeouts[-1]))
        if self.family == socket.AF_INET6:
            raise TimeoutError("timed out")

    def close(self):
        pass


class AddressFallbackTests(unittest.TestCase):
    def setUp(self):
        FakeSocket.log = []
        self.patches = [mock.patch.object(dl, "_preferred_family", None), mock.patch.object(dl.socket, "socket", FakeSocket),
                        mock.patch.object(dl.socket, "getaddrinfo", return_value=[V6, V6B, V4])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_dead_ipv6_costs_one_short_attempt_then_ipv4_goes_first(self):
        sock = dl._create_connection(("zenodo.example", 443), 60)
        self.assertEqual(FakeSocket.log, [("2001:db8::1", dl.CONNECT_TIMEOUT), ("192.0.2.1", dl.CONNECT_TIMEOUT)])
        self.assertEqual(sock.timeouts[-1], 60)  # reads keep the caller's timeout
        FakeSocket.log = []
        dl._create_connection(("other.example", 443), 60)
        self.assertEqual(FakeSocket.log, [("192.0.2.1", dl.CONNECT_TIMEOUT)])

    def test_raises_the_last_error_when_nothing_connects(self):
        with mock.patch.object(dl.socket, "getaddrinfo", return_value=[V6, V6B]), self.assertRaises(TimeoutError):
            dl._create_connection(("v6only.example", 443), 2)
        self.assertEqual(FakeSocket.log, [("2001:db8::1", 2), ("2001:db8::2", 2)])
        self.assertIsNone(dl._preferred_family)


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



class BudgetTests(unittest.TestCase):
    def test_storage_is_unlimited_unless_a_cap_is_set(self):
        with mock.patch.object(budget, "usage_bytes", return_value=10**15):
            with mock.patch.dict("os.environ", {"CW_STORAGE_BUDGET_GB": ""}):
                self.assertEqual(budget.check(10**15), (True, 10**15, None))
            with mock.patch.dict("os.environ", {"CW_STORAGE_BUDGET_GB": "40"}):
                self.assertEqual(budget.check(1), (False, 10**15, 40 * 10**9))


if __name__ == "__main__":
    unittest.main()
