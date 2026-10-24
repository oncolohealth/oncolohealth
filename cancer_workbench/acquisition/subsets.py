"""Fetch part of a source: whole groups (patients, cases, slides) drawn with a fixed seed, or named ids.

A catalog record opts in with an `acquisition.subset` block:

    {"unit": "patient" | "file" | "image" | "slide",
     "required": true,            # no default download; a subset must be chosen
     "modalities": ["CT"],        # TCIA only: series modalities to offer
     "group_regex": "P_\\d{5}",   # TCIA only: patient group taken from PatientID
     "candidates": ["x*.npz"],    # Zenodo/figshare only: files on offer
     "max_listing": 10000,        # ISIC only: refuse searches that match more images
     "query": true}               # the user may add a search that narrows the catalog query (ISIC)

A selection is `{"mode": "sample", "count": N, "seed": S}` or `{"mode": "ids", "ids": [...]}`,
optionally with `"query"`. Sampling shuffles every group with `random.Random(seed)` and takes the
first N groups that are not already on disk, so asking for N more continues the same order.
The chosen groups, the seed and a hash of the listing are recorded in PROVENANCE.json.
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import random
import time
from pathlib import Path

from .sources import LISTERS, AccessError, FilePlan, Listing, Unit

CACHE_SECONDS = 900
MAX_COUNT = 100_000
MAX_IDS = 20_000
MAX_QUERY = 500
_cache: dict[str, tuple[float, Listing]] = {}


@dataclasses.dataclass
class Selection:
    mode: str
    count: int | None = None
    seed: int = 0
    ids: list[str] = dataclasses.field(default_factory=list)
    query: str | None = None

    def describe(self) -> dict:
        out = {"mode": self.mode}
        if self.mode == "sample":
            out.update(count=self.count, seed=self.seed)
        else:
            out["ids"] = list(self.ids)
        if self.query:
            out["query"] = self.query
        return out


def _int(v, name: str, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{name} must be a whole number from {lo} to {hi:,}")
    return v


def parse_selection(raw: dict, subset: dict) -> Selection:
    """Validate a selection from the CLI or the app against the record's subset block."""
    if not isinstance(raw, dict):
        raise ValueError("a subset must be an object")
    unknown = set(raw) - {"mode", "count", "seed", "ids", "query"}
    if unknown:
        raise ValueError(f"unknown subset fields {sorted(unknown)}")
    query = raw.get("query")
    if query is not None:
        if not subset.get("query"):
            raise ValueError("this source does not take a search query")
        if not isinstance(query, str) or len(query) > MAX_QUERY:
            raise ValueError(f"query must be text of at most {MAX_QUERY} characters")
        query = query.strip() or None
    mode = raw.get("mode")
    if mode == "sample":
        return Selection("sample", count=_int(raw.get("count"), "count", 1, MAX_COUNT),
                         seed=_int(raw.get("seed", 0), "seed", 0, 2**31 - 1), query=query)
    if mode == "ids":
        ids = raw.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, str) and i.strip() for i in ids):
            raise ValueError(f"ids must be a list of 1 to {MAX_IDS:,} non-empty strings")
        return Selection("ids", ids=sorted({i.strip() for i in ids}), query=query)
    raise ValueError("mode must be 'sample' or 'ids'")


def listing(acq: dict, query: str | None = None) -> Listing:
    """List a source's units, cached for CACHE_SECONDS so a plan and the download that follows agree."""
    fetcher = acq.get("fetcher")
    if fetcher not in LISTERS:
        raise AccessError(f"{fetcher!r} sources cannot be fetched as a subset")
    key = repr((sorted((k, repr(v)) for k, v in acq.items()), query))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    result = LISTERS[fetcher](acq, query)
    _cache[key] = (time.monotonic(), result)
    return result


def _present(root: Path, p: FilePlan) -> bool:
    f = root / p.relpath
    return f.exists() and (p.size is None or f.stat().st_size == p.size)


def _groups(units: list[Unit]) -> dict[str, list[Unit]]:
    out: dict[str, list[Unit]] = {}
    for u in units:
        out.setdefault(u.group, []).append(u)
    return out


def population_sha256(units: list[Unit]) -> str:
    """Identifies the listing a seeded sample was drawn from; it changes if the source adds or drops units."""
    return hashlib.sha256("\n".join(sorted(f"{u.group}\t{u.id}" for u in units)).encode()).hexdigest()


def choose(lst: Listing, sel: Selection, root: Path) -> tuple[list[Unit], dict]:
    groups = _groups(lst.units)
    on_disk = {g for g, us in groups.items() if all(_present(root, p) for u in us for p in u.plans)}
    summary = {**sel.describe(), "population_groups": len(groups), "population_units": len(lst.units),
               "population_sha256": population_sha256(lst.units)}
    if sel.mode == "sample":
        order = sorted(groups)
        random.Random(sel.seed).shuffle(order)
        picked = [g for g in order if g not in on_disk][: sel.count]
        units = [u for g in picked for u in groups[g]]
        summary["skipped_on_disk"] = len(on_disk)
        if len(picked) < sel.count:
            summary["short_by"] = sel.count - len(picked)
    else:
        wanted = set(sel.ids)
        unknown = wanted - set(groups) - {u.id for u in lst.units}
        if unknown:
            shown = ", ".join(sorted(unknown)[:10])
            raise ValueError(f"{len(unknown)} id(s) are not in this source: {shown}{' …' if len(unknown) > 10 else ''}")
        units = [u for u in lst.units if u.id in wanted or u.group in wanted]
        picked = sorted({u.group for u in units})
    summary["groups"] = picked
    summary["units"] = [u.id for u in units]
    return units, summary


def resolve_subset(acq: dict, raw: dict, root: Path) -> tuple[list[FilePlan], dict]:
    """Plans for a selection plus the summary recorded in provenance. Raises ValueError or AccessError."""
    subset = acq.get("subset")
    if not subset:
        raise ValueError("this record has no subset support")
    sel = parse_selection(raw, subset)
    lst = listing(acq, sel.query)
    units, summary = choose(lst, sel, root)
    summary["unit"] = subset.get("unit")
    plans, seen = [], set()
    for p in lst.shared + [p for u in units for p in u.plans]:
        if p.relpath not in seen:
            seen.add(p.relpath)
            plans.append(p)
    return plans, summary


def summarize_units(acq: dict, root: Path, query: str | None = None) -> dict:
    """Groups on offer for the app's checklist, with size and whether each is already on disk."""
    subset = acq.get("subset")
    if not subset:
        raise ValueError("this record has no subset support")
    if query is not None:
        parse_selection({"mode": "ids", "ids": ["-"], "query": query}, subset)
    lst = listing(acq, query or None)
    rows = []
    for g, us in sorted(_groups(lst.units).items()):
        if len(us) == 1:
            detail = us[0].detail
        else:  # e.g. "CT ×1, MR ×4, PT ×1, RTSTRUCT ×6" from each unit's leading detail field
            kinds = collections.Counter(u.detail.split(" · ")[0] or "item" for u in us)
            detail = ", ".join(f"{k} ×{n}" for k, n in sorted(kinds.items()))
        rows.append({"id": g, "units": len(us), "bytes": sum(u.bytes for u in us),
                     "on_disk": all(_present(root, p) for u in us for p in u.plans), "detail": detail})
    return {"unit": subset.get("unit"), "groups": rows, "population_units": len(lst.units),
            "integrity": sorted({p.integrity for u in lst.units for p in u.plans})}
