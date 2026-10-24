"""Resumable, integrity-checked HTTP downloads using only the standard library."""
from __future__ import annotations

import hashlib
import itertools
import socket
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

CHUNK = 1 << 20
USER_AGENT = "cancer-workbench-fetch/0.1"


class IntegrityError(RuntimeError):
    pass


class _StripAuthOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward credentials (e.g. HF_TOKEN) to a different host after a redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            for h in ("Authorization", "authorization"):
                new.headers.pop(h, None)
                new.unredirected_hdrs.pop(h, None)
        return new


CONNECT_TIMEOUT = 5.0  # per address; the read timeout stays as the caller set it
_preferred_family: int | None = None  # set once one family has failed and the other connected


def _interleave(infos: list[tuple]) -> list[tuple]:
    """Alternate address families (RFC 8305 §4), putting the family that last worked first."""
    by_family: dict[int, list[tuple]] = {}
    for info in infos:
        by_family.setdefault(info[0], []).append(info)
    lists = [by_family[f] for f in sorted(by_family, key=lambda f: f != _preferred_family)]
    return [i for row in itertools.zip_longest(*lists) for i in row if i is not None]


def _create_connection(address, timeout=None, source_address=None, *args, **kwargs):
    """socket.create_connection, but alternating IPv6/IPv4 with a short connect timeout per address.

    Some networks resolve AAAA records but drop IPv6 traffic. Plain create_connection then waits the
    full timeout on every IPv6 address before it tries IPv4: six zenodo.org addresses × 60 s. Once one
    family fails and the other connects, the working family goes first for the rest of the process.
    """
    global _preferred_family
    host, port = address
    if timeout is not None and not isinstance(timeout, (int, float)):  # socket's "use the default" sentinel
        timeout = socket.getdefaulttimeout()
    attempt = CONNECT_TIMEOUT if timeout is None else min(timeout, CONNECT_TIMEOUT)
    failed, last = set(), None
    for family, kind, proto, _, addr in _interleave(socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)):
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(attempt)
            if source_address:
                sock.bind(source_address)
            sock.connect(addr)
        except OSError as e:
            sock.close()
            failed.add(family)
            last = e
            continue
        sock.settimeout(timeout)
        if failed - {family}:
            _preferred_family = family
        return sock
    raise last or OSError(f"getaddrinfo returned no addresses for {host}")


def _with_fallback(conn_class):
    def make(*args, **kwargs):
        conn = conn_class(*args, **kwargs)
        conn._create_connection = _create_connection  # http.client's hook for opening the socket
        return conn
    return make


class _HTTPHandler(urllib.request.HTTPHandler):
    def do_open(self, http_class, req, **kwargs):
        return super().do_open(_with_fallback(http_class), req, **kwargs)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def do_open(self, http_class, req, **kwargs):
        return super().do_open(_with_fallback(http_class), req, **kwargs)


_opener = urllib.request.build_opener(_StripAuthOnCrossHostRedirect, _HTTPHandler, _HTTPSHandler)


def open_url(url: str, headers: dict[str, str] | None = None, timeout: float = 60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return _opener.open(req, timeout=timeout)


def hash_file(path: Path) -> dict[str, str | int]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            md5.update(chunk)
            sha.update(chunk)
            n += len(chunk)
    return {"bytes": n, "md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def verify(path: Path, *, size: int | None = None, md5: str | None = None, sha256: str | None = None) -> list[str]:
    """Return a list of mismatches (empty when the file matches every expectation given)."""
    if not path.exists():
        return [f"{path} missing"]
    if size is not None and path.stat().st_size != size:
        return [f"{path.name}: size {path.stat().st_size} != expected {size}"]
    if md5 is None and sha256 is None:
        return []
    h = hash_file(path)
    errs = []
    if md5 and h["md5"] != md5.lower():
        errs.append(f"{path.name}: md5 {h['md5']} != expected {md5}")
    if sha256 and h["sha256"] != sha256.lower():
        errs.append(f"{path.name}: sha256 {h['sha256']} != expected {sha256}")
    return errs


def download(
    url: str,
    dest: Path,
    *,
    size: int | None = None,
    md5: str | None = None,
    sha256: str | None = None,
    headers: dict[str, str] | None = None,
    quiet: bool = False,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download `url` to `dest`, resuming a partial `.part` file, then verify it.

    Raises IntegrityError (and keeps nothing at `dest`) when verification fails.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not verify(dest, size=size, md5=md5, sha256=sha256):
        if not quiet:
            print(f"  ok (cached) {dest.name}", file=sys.stderr)
        return dest

    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    if size is not None and start > size:
        part.unlink()
        start = 0
    hdrs = dict(headers or {})
    if start:
        hdrs["Range"] = f"bytes={start}-"

    with open_url(url, hdrs) as resp:
        if start and resp.status != 206:
            start = 0  # server ignored Range; restart
        total = size or (int(resp.headers.get("Content-Length", 0)) + start) or None
        done = start
        with open(part, "ab" if start else "wb") as f:
            while chunk := resp.read(CHUNK):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
                if not quiet and total:
                    print(f"\r  {dest.name}: {done / 1e6:,.0f}/{total / 1e6:,.0f} MB", end="", file=sys.stderr)
    if not quiet:
        print(file=sys.stderr)

    errs = verify(part, size=size, md5=md5, sha256=sha256)
    if errs:
        part.unlink(missing_ok=True)
        raise IntegrityError("; ".join(errs))
    part.replace(dest)
    return dest


def safe_extract_zip(archive: Path, out_dir: Path, *, max_total_bytes: int = 50 * 10**9) -> list[str]:
    """Extract a zip, refusing absolute paths, `..` traversal, symlinks and zip bombs."""
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if sum(i.file_size for i in infos) > max_total_bytes:
            raise IntegrityError(f"{archive.name}: uncompressed size exceeds {max_total_bytes} bytes")
        for info in infos:
            target = (out_dir / info.filename).resolve()
            if not target.is_relative_to(out_dir):
                raise IntegrityError(f"{archive.name}: unsafe member path {info.filename!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise IntegrityError(f"{archive.name}: symlink member {info.filename!r}")
            zf.extract(info, out_dir)
            names.append(info.filename)
    return names
