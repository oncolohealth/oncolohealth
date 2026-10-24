"""Resolve a catalog `acquisition` block into a concrete list of files to download.

Each resolver queries the publisher's API at fetch time so sizes and checksums
come from the source, not from values typed into the catalog.
"""
from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

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
    approx_size: int | None = None  # download estimate when the publisher gives no exact size
    group: str | None = None  # patient/case the file belongs to, for subset fetches


@dataclasses.dataclass
class Unit:
    """One selectable item of a source (a series, file, image or slide) and the files it needs."""
    id: str
    group: str  # whole groups (patients/cases) are sampled together
    plans: list[FilePlan]
    detail: str = ""

    @property
    def bytes(self) -> int:
        return sum(p.size if p.size is not None else (p.approx_size or 0) for p in self.plans)


def _get_json(url: str, headers: dict[str, str] | None = None):
    with open_url(url, headers) as r:
        return json.load(r)


def _select(names: list[str], include: list[str] | None) -> set[str]:
    if not include:
        return set(names)
    return {n for n in names if any(fnmatch.fnmatch(n, pat) for pat in include)}


def _zenodo_files(acq: dict) -> dict[str, FilePlan]:
    rec = _get_json(f"https://zenodo.org/api/records/{acq['record']}")
    plans = {}
    for f in rec["files"]:
        algo, _, digest = f.get("checksum", "").partition(":")
        plans[f["key"]] = FilePlan(url=f["links"]["self"], relpath=f["key"], size=f["size"], md5=digest if algo == "md5" else None)
    return plans


def resolve_zenodo(acq: dict) -> list[FilePlan]:
    files = _zenodo_files(acq)
    wanted = _select(list(files), acq.get("include"))
    missing = set(acq.get("include") or []) - set(files)
    if missing and not any(any(c in m for c in "*?[") for m in missing):
        raise AccessError(f"zenodo record {acq['record']} has no files {sorted(missing)}")
    return [files[name] for name in sorted(wanted)]


def _figshare_files(acq: dict) -> dict[str, FilePlan]:
    art = _get_json(f"https://api.figshare.com/v2/articles/{acq['article']}/versions/{acq['version']}")
    return {
        f["name"]: FilePlan(
            url=f["download_url"],
            relpath=f["name"],
            size=f["size"],
            md5=f.get("computed_md5") or None,
            extract=bool(acq.get("extract")) and f["name"].endswith(".zip"),
        )
        for f in art["files"]
    }


def resolve_figshare(acq: dict) -> list[FilePlan]:
    files = _figshare_files(acq)
    wanted = _select(list(files), acq.get("include"))
    return [p for name, p in files.items() if name in wanted]


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


def _tcia_series(acq: dict) -> list[dict]:
    return _get_json(f"{TCIA_API}/getSeries?Collection={urllib.parse.quote(acq['collection'])}")


def _tcia_group(acq: dict, patient_id: str) -> str:
    pattern = (acq.get("subset") or {}).get("group_regex")
    m = re.search(pattern, patient_id) if pattern else None
    return m.group(0) if m else patient_id


def _tcia_plan(acq: dict, s: dict) -> FilePlan:
    uid = s["SeriesInstanceUID"]
    raw = int(s.get("FileSize") or 0)  # uncompressed bytes: an upper bound for the zip, about the extracted size
    return FilePlan(
        url=f"{TCIA_API}/getImage?SeriesInstanceUID={uid}",
        relpath=f"{s['PatientID']}/{uid}.zip",
        size=None,  # TCIA reports uncompressed FileSize only; no publisher checksum
        integrity="trust_on_first_use",
        extract=bool(acq.get("extract")),
        approx_size=raw or None,
        group=_tcia_group(acq, s["PatientID"]),
    )


def resolve_tcia(acq: dict) -> list[FilePlan]:
    """Public TCIA collections via the NBIA v1 API. Series are pinned by UID in the catalog."""
    if not acq.get("series"):
        raise AccessError("no series are pinned for this collection; choose a subset of patients first")
    by_uid = {s["SeriesInstanceUID"]: s for s in _tcia_series(acq)}
    plans = []
    for uid in acq["series"]:
        if uid not in by_uid:
            raise AccessError(f"series {uid} not found in TCIA collection {acq['collection']}")
        plans.append(_tcia_plan(acq, by_uid[uid]))
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


def _subset_only(acq: dict) -> list[FilePlan]:
    raise AccessError(f"{acq.get('fetcher')} sources are fetched only as a subset; choose one first")


RESOLVERS = {
    "zenodo": resolve_zenodo,
    "figshare": resolve_figshare,
    "huggingface": resolve_huggingface,
    "tcia": resolve_tcia,
    "url": resolve_url,
    "isic": _subset_only,
    "gdc": _subset_only,
    "s3": _subset_only,
}


def resolve(acq: dict) -> list[FilePlan]:
    fetcher = acq.get("fetcher")
    if fetcher not in RESOLVERS:
        raise AccessError(f"no automatic fetcher for {fetcher!r}; see the record's `instructions`")
    return RESOLVERS[fetcher](acq)


# ---------- subset listings ----------
# A lister returns every selectable Unit of a source plus `shared` files fetched with any subset
# (README, license, label tables). Selection itself lives in subsets.py.

@dataclasses.dataclass
class Listing:
    units: list[Unit]
    shared: list[FilePlan] = dataclasses.field(default_factory=list)


def units_tcia(acq: dict, query: str | None = None) -> Listing:
    modalities = set((acq.get("subset") or {}).get("modalities") or [])
    units = []
    for s in sorted(_tcia_series(acq), key=lambda s: (s["PatientID"], s["SeriesInstanceUID"])):
        if modalities and s.get("Modality") not in modalities:
            continue
        plan = _tcia_plan(acq, s)
        detail = " · ".join(str(x) for x in (s.get("Modality"), s.get("SeriesDescription"), f"{s.get('ImageCount', '?')} images") if x)
        units.append(Unit(id=s["SeriesInstanceUID"], group=plan.group, plans=[plan], detail=detail))
    return Listing(units)


def _file_units(files: dict[str, FilePlan], acq: dict) -> Listing:
    names = _select(list(files), (acq.get("subset") or {}).get("candidates"))
    return Listing([Unit(id=n, group=n, plans=[dataclasses.replace(files[n], group=n)]) for n in sorted(names)])


def units_zenodo(acq: dict, query: str | None = None) -> Listing:
    return _file_units(_zenodo_files(acq), acq)


def units_figshare(acq: dict, query: str | None = None) -> Listing:
    return _file_units(_figshare_files(acq), acq)


ISIC_API = "https://api.isic-archive.com/api/v2"


def isic_query(acq: dict, extra: str | None = None) -> str:
    """The catalog query and license filter always apply; a user's extra query can only narrow them."""
    parts = [f"({acq['query']})"] if acq.get("query") else []
    if acq.get("licenses"):
        parts.append("(" + " OR ".join(f"copyright_license:{lic}" for lic in acq["licenses"]) + ")")
    if extra:
        parts.append(f"({extra})")
    return " AND ".join(parts)


def units_isic(acq: dict, query: str | None = None) -> Listing:
    cap = int((acq.get("subset") or {}).get("max_listing", 10000))
    variant = acq.get("variant", "full")
    licenses = set(acq.get("licenses") or [])
    url = f"{ISIC_API}/images/search/?" + urllib.parse.urlencode({"query": isic_query(acq, query), "limit": 100})
    units = []
    while url:
        if not url.startswith(f"{ISIC_API}/"):
            raise AccessError(f"ISIC pagination pointed off the API host: {url}")
        page = _get_json(url)
        if (page.get("count") or 0) > cap:  # only the first page carries a count
            raise AccessError(f"the search matches {page['count']:,} images, over the listing cap of {cap:,}; narrow it with a query")
        for img in page.get("results", []):
            if licenses and img.get("copyright_license") not in licenses:
                continue  # never trust the server-side filter alone
            iid, f = img["isic_id"], img["files"][variant]
            clinical = img.get("metadata", {}).get("clinical", {})
            group = clinical.get("patient_id") or clinical.get("lesion_id") or iid
            ext = os.path.splitext(urllib.parse.urlsplit(f["url"]).path)[1] or ".jpg"
            diagnosis = next((clinical[k] for k in ("diagnosis_3", "diagnosis_2", "diagnosis_1") if clinical.get(k)), "no diagnosis")
            units.append(Unit(id=iid, group=group, detail=f"{diagnosis} · {img.get('copyright_license')}", plans=[
                # The API's size can lag the served file (seen 2026-10-24), so it is only an estimate here.
                FilePlan(url=f["url"], relpath=f"images/{iid}{ext}", approx_size=f.get("size"), integrity="trust_on_first_use", group=group),
                FilePlan(url=f"{ISIC_API}/images/{iid}/", relpath=f"metadata/{iid}.json", integrity="trust_on_first_use",
                         approx_size=4000, group=group),
            ]))
        url = page.get("next")
    return Listing(sorted(units, key=lambda u: u.id))


GDC_API = "https://api.gdc.cancer.gov"
_GDC_FIELDS = "file_id,file_name,file_size,md5sum,access,data_format,experimental_strategy,cases.submitter_id"


def _gdc_open_only(filters: dict) -> bool:
    return any(c.get("op") == "=" and c.get("content", {}).get("field") == "access" and c["content"].get("value") == "open"
               for c in filters.get("content", []))


def units_gdc(acq: dict, query: str | None = None) -> Listing:
    if not _gdc_open_only(acq.get("filters", {})):
        raise AccessError("GDC filters must restrict to access = open; controlled data needs dbGaP approval")
    params = {"filters": json.dumps(acq["filters"]), "fields": _GDC_FIELDS, "size": 10000, "format": "json"}
    data = _get_json(f"{GDC_API}/files?{urllib.parse.urlencode(params)}")["data"]
    hits = data["hits"]
    if data.get("pagination", {}).get("total", len(hits)) > len(hits):
        raise AccessError("the GDC query matches more than 10,000 files; narrow its filters")
    units = []
    for h in sorted(hits, key=lambda h: h["file_name"]):
        if h.get("access") != "open":
            continue
        cases = sorted({c["submitter_id"] for c in h.get("cases", [])}) or ["unknown-case"]
        group = "+".join(cases)
        units.append(Unit(id=h["file_name"], group=group, detail=" · ".join(x for x in (h.get("experimental_strategy"), h.get("data_format")) if x),
                          plans=[FilePlan(url=f"{GDC_API}/data/{h['file_id']}", relpath=f"{group}/{h['file_name']}",
                                          size=h["file_size"], md5=h.get("md5sum"), group=group,
                                          integrity="publisher_checksum" if h.get("md5sum") else "size_only")]))
    return Listing(units)


_S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def _s3_base(acq: dict) -> str:
    return f"https://{acq['bucket']}.s3.{acq['region']}.amazonaws.com"


def _s3_list(acq: dict) -> dict[str, int]:
    """Every key under acq['prefix'] -> size, via anonymous ListObjectsV2."""
    out, token = {}, None
    while True:
        q = {"list-type": "2", "prefix": acq["prefix"], **({"continuation-token": token} if token else {})}
        with open_url(f"{_s3_base(acq)}/?{urllib.parse.urlencode(q)}") as r:
            root = ET.parse(r).getroot()
        for c in root.findall("s3:Contents", _S3_NS):
            out[c.findtext("s3:Key", namespaces=_S3_NS)] = int(c.findtext("s3:Size", namespaces=_S3_NS))
        token = root.findtext("s3:NextContinuationToken", namespaces=_S3_NS)
        if root.findtext("s3:IsTruncated", namespaces=_S3_NS) != "true" or not token:
            return out


def units_s3(acq: dict, query: str | None = None) -> Listing:
    keys = _s3_list(acq)
    prefix = acq["prefix"]
    md5s = {}
    if acq.get("checksums"):
        with open_url(f"{_s3_base(acq)}/{urllib.parse.quote(prefix + acq['checksums'])}") as r:
            for line in r.read().decode().splitlines():
                digest, _, rel = line.strip().partition(" ")
                if rel:
                    md5s[rel.lstrip("*")] = digest

    def plan(rel: str, group: str | None) -> FilePlan:
        return FilePlan(url=f"{_s3_base(acq)}/{urllib.parse.quote(prefix + rel)}", relpath=rel, size=keys[prefix + rel],
                        md5=md5s.get(rel), group=group, integrity="publisher_checksum" if rel in md5s else "size_only")

    units = []
    for key in sorted(keys):
        rel = key[len(prefix):]
        if not rel.startswith(acq["units_prefix"]) or rel.endswith("/"):
            continue
        stem = os.path.splitext(os.path.basename(rel))[0]
        extra = [c.format(stem=stem) for c in acq.get("companions", [])]
        units.append(Unit(id=stem, group=stem, plans=[plan(rel, stem)] + [plan(e, stem) for e in extra if prefix + e in keys],
                          detail=f"{1 + sum(prefix + e in keys for e in extra)} files"))
    shared = [plan(rel, None) for rel in acq.get("shared", []) if prefix + rel in keys]
    return Listing(units, shared)


LISTERS = {"tcia": units_tcia, "zenodo": units_zenodo, "figshare": units_figshare,
           "isic": units_isic, "gdc": units_gdc, "s3": units_s3}
