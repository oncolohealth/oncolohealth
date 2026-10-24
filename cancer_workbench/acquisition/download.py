"""Resumable, integrity-checked HTTP downloads using only the standard library."""
from __future__ import annotations

import hashlib
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


_opener = urllib.request.build_opener(_StripAuthOnCrossHostRedirect)


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
