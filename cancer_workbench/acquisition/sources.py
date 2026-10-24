"""Resolve a catalog `acquisition` block into a concrete list of files to download.

Each resolver queries the publisher's API at fetch time so sizes and checksums
come from the source, not from values typed into the catalog.
"""
from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import urllib.parse

from .download import open_url


class AccessError(RuntimeError):
    """Raised when a source needs credentials or terms acceptance we do not have."""


@dataclasses.dataclass
class FilePlan:
    url: str
    relpath: str
    size: int | None = None
    md5: str | None = None
    sha256: str | None = None
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    integrity: str = "publisher_checksum"  # or "size_only" / "trust_on_first_use"
    extract: bool = False


def _get_json(url: str, headers: dict[str, str] | None = None):
    with open_url(url, headers) as r:
        return json.load(r)


def _select(names: list[str], include: list[str] | None) -> set[str]:
    if not include:
        return set(names)
    return {n for n in names if any(fnmatch.fnmatch(n, pat) for pat in include)}


def resolve_zenodo(acq: dict) -> list[FilePlan]:
    rec = _get_json(f"https://zenodo.org/api/records/{acq['record']}")
    files = {f["key"]: f for f in rec["files"]}
    wanted = _select(list(files), acq.get("include"))
    missing = set(acq.get("include") or []) - set(files)
    if missing and not any(any(c in m for c in "*?[") for m in missing):
        raise AccessError(f"zenodo record {acq['record']} has no files {sorted(missing)}")
    plans = []
    for name in sorted(wanted):
        f = files[name]
        algo, _, digest = f.get("checksum", "").partition(":")
        plans.append(
            FilePlan(
                url=f["links"]["self"],
                relpath=name,
                size=f["size"],
                md5=digest if algo == "md5" else None,
            )
        )
    return plans


def resolve_figshare(acq: dict) -> list[FilePlan]:
    art = _get_json(f"https://api.figshare.com/v2/articles/{acq['article']}/versions/{acq['version']}")
    wanted = _select([f["name"] for f in art["files"]], acq.get("include"))
    return [
        FilePlan(
            url=f["download_url"],
            relpath=f["name"],
            size=f["size"],
            md5=f.get("computed_md5") or None,
            extract=bool(acq.get("extract")) and f["name"].endswith(".zip"),
        )
        for f in art["files"]
        if f["name"] in wanted
    ]


def _hf_headers(acq: dict) -> dict[str, str]:
    token = os.environ.get("HF_TOKEN")
    if acq.get("gated"):
        if not token:
            raise AccessError(
                f"{acq['repo']} is gated. Accept its terms at https://huggingface.co/{acq['repo']} "
                "with your own account, then export HF_TOKEN (fish: `set -x HF_TOKEN hf_...`)."
            )
    return {"Authorization": f"Bearer {token}"} if token else {}


def resolve_huggingface(acq: dict) -> list[FilePlan]:
    repo, rev = acq["repo"], acq["revision"]
    headers = _hf_headers(acq)
    try:
        info = _get_json(f"https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true", headers)
    except Exception as e:  # urllib HTTPError for 401/403 on gated repos
        raise AccessError(f"cannot read {repo}@{rev}: {e}") from e
    siblings = {s["rfilename"]: s for s in info.get("siblings", [])}
    wanted = _select(list(siblings), acq.get("include"))
    plans = []
    for name in sorted(wanted):
        s = siblings[name]
        lfs = s.get("lfs") or {}
        plans.append(
            FilePlan(
                url=f"https://huggingface.co/{repo}/resolve/{rev}/{urllib.parse.quote(name)}",
                relpath=name,
                size=s.get("size"),
                sha256=lfs.get("sha256"),
                headers=headers,
                integrity="publisher_checksum" if lfs.get("sha256") else "size_only",
            )
        )
    return plans


TCIA_API = "https://services.cancerimagingarchive.net/nbia-api/services/v1"


def resolve_tcia(acq: dict) -> list[FilePlan]:
    """Public TCIA collections via the NBIA v1 API. Series are pinned by UID in the catalog."""
    series = _get_json(f"{TCIA_API}/getSeries?Collection={urllib.parse.quote(acq['collection'])}")
    by_uid = {s["SeriesInstanceUID"]: s for s in series}
    plans = []
    for uid in acq["series"]:
        if uid not in by_uid:
            raise AccessError(f"series {uid} not found in TCIA collection {acq['collection']}")
        s = by_uid[uid]
        plans.append(
            FilePlan(
                url=f"{TCIA_API}/getImage?SeriesInstanceUID={uid}",
                relpath=f"{s['PatientID']}/{uid}.zip",
                size=None,  # TCIA reports uncompressed FileSize only; no publisher checksum
                integrity="trust_on_first_use",
                extract=bool(acq.get("extract")),
            )
        )
    return plans


def resolve_url(acq: dict) -> list[FilePlan]:
    return [
        FilePlan(
            url=f["url"],
            relpath=f["relpath"],
            size=f.get("size"),
            md5=f.get("md5"),
            sha256=f.get("sha256"),
            integrity="publisher_checksum" if (f.get("md5") or f.get("sha256")) else "size_only",
            extract=bool(f.get("extract")),
        )
        for f in acq["files"]
    ]


RESOLVERS = {
    "zenodo": resolve_zenodo,
    "figshare": resolve_figshare,
    "huggingface": resolve_huggingface,
    "tcia": resolve_tcia,
    "url": resolve_url,
}


def resolve(acq: dict) -> list[FilePlan]:
    fetcher = acq.get("fetcher")
    if fetcher not in RESOLVERS:
        raise AccessError(f"no automatic fetcher for {fetcher!r}; see the record's `instructions`")
    return RESOLVERS[fetcher](acq)
