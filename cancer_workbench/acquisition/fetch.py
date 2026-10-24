"""Plan and execute fetches for catalog records, writing a PROVENANCE.json per artifact."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from ..common.paths import DATA_DIR, MODELS_DIR
from ..registry.store import Catalog, load_catalog
from . import budget
from .download import download, hash_file, safe_extract_zip
from .sources import AccessError, FilePlan, resolve

TIERS = ("default", "optional", "gated", "big_machine", "manual")


def target_dir(record: dict) -> Path:
    root = MODELS_DIR if record["_kind"] == "model" else DATA_DIR
    return root / record["id"]


def select(catalog: Catalog, ids: list[str], tier: str | None) -> list[dict]:
    if tier:
        return [r for r in catalog.all() if r.get("acquisition", {}).get("tier") == tier]
    out = []
    for i in ids:
        rec = catalog.get(i)
        if rec is None:
            raise KeyError(f"unknown catalog id {i!r}")
        out.append(rec)
    return out


def remaining_bytes(record: dict, plans: list[FilePlan]) -> int:
    root = target_dir(record)
    total = 0
    for p in plans:
        f = root / p.relpath
        if not (f.exists() and (p.size is None or f.stat().st_size == p.size)):
            total += p.size if p.size is not None else int(record["acquisition"].get("approx_bytes", 0) / max(len(plans), 1))
    return total


def plan(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        acq = r.get("acquisition", {})
        row = {"id": r["id"], "tier": acq.get("tier"), "fetcher": acq.get("fetcher"), "plans": [], "error": None}
        try:
            row["plans"] = resolve(acq)
            row["bytes"] = remaining_bytes(r, row["plans"])
        except AccessError as e:
            row["error"] = str(e)
            row["bytes"] = 0
        rows.append(row)
    return rows


def write_provenance(record: dict, plans: list[FilePlan], files: list[dict]) -> Path:
    prov = {
        "id": record["id"],
        "kind": record["_kind"],
        "name": record.get("name"),
        "license": record.get("license"),
        "source": {k: v for k, v in record["acquisition"].items() if k not in ("instructions",)},
        "citation": record.get("citation"),
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "files": files,
        "note": "Hashes verify file identity/integrity only, not medical correctness of labels.",
    }
    path = target_dir(record) / "PROVENANCE.json"
    path.write_text(json.dumps(prov, indent=2) + "\n")
    return path


def fetch(record: dict, plans: list[FilePlan], *, extract: bool = True) -> Path:
    root = target_dir(record)
    files = []
    for p in plans:
        dest = root / p.relpath
        print(f"[{record['id']}] {p.relpath}", file=sys.stderr)
        download(p.url, dest, size=p.size, md5=p.md5, sha256=p.sha256, headers=p.headers)
        h = hash_file(dest)
        files.append({"path": p.relpath, "url": p.url, "integrity": p.integrity, **h})
        if extract and p.extract:
            out = dest.with_suffix("")
            if not out.exists():
                print(f"  extracting -> {out.relative_to(root)}", file=sys.stderr)
                safe_extract_zip(dest, out)
    return write_provenance(record, plans, files)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench fetch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show catalog records with tier, size and local status")
    for name in ("plan", "get"):
        p = sub.add_parser(name)
        p.add_argument("ids", nargs="*")
        p.add_argument("--tier", choices=TIERS)
        if name == "get":
            p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
            p.add_argument("--allow-big", action="store_true", help="permit big_machine tier records")
    args = ap.parse_args(argv)
    catalog = load_catalog()

    if args.cmd == "list":
        print(f"{'id':38} {'kind':8} {'tier':12} {'access':14} {'~GB':>7}  local")
        for r in catalog.all():
            acq = r.get("acquisition", {})
            local = "yes" if (target_dir(r) / "PROVENANCE.json").exists() else "-"
            print(
                f"{r['id']:38} {r['_kind']:8} {acq.get('tier', '?'):12} {r.get('access', '?'):14} "
                f"{acq.get('approx_bytes', 0) / 1e9:7.2f}  {local}"
            )
        used = budget.usage_bytes()
        print(f"\nused {used / 1e9:.2f} GB of {budget.budget_bytes() / 1e9:.0f} GB budget")
        return 0

    if not args.ids and not args.tier:
        ap.error("give catalog ids or --tier")
    records = select(catalog, args.ids, args.tier)
    rows = plan(records)
    total = sum(r["bytes"] for r in rows if not r["error"])
    for r in rows:
        status = f"BLOCKED: {r['error']}" if r["error"] else f"{len(r['plans'])} files, {r['bytes'] / 1e9:.2f} GB to fetch"
        print(f"{r['id']:38} {status}")
    fits, used, cap = budget.check(total)
    print(f"\nplanned {total / 1e9:.2f} GB; used {used / 1e9:.2f} GB; budget {cap / 1e9:.0f} GB -> {'OK' if fits else 'OVER BUDGET'}")
    if args.cmd == "plan":
        return 0

    if not fits:
        print("Refusing: over budget. Raise CW_STORAGE_BUDGET_GB or fetch fewer records.", file=sys.stderr)
        return 2
    big = [r["id"] for r in records if r["acquisition"].get("tier") == "big_machine"]
    if big and not args.allow_big:
        print(f"Refusing big_machine records {big} without --allow-big.", file=sys.stderr)
        return 2
    if not args.yes and input("proceed? [y/N] ").strip().lower() != "y":
        return 1
    failed = 0
    for rec, row in zip(records, rows):
        if row["error"]:
            continue
        try:
            print(f"wrote {fetch(rec, row['plans'])}", file=sys.stderr)
        except Exception as e:  # keep going; report every failure at the end
            failed += 1
            print(f"[{rec['id']}] FAILED: {e}", file=sys.stderr)
    blocked = sum(1 for r in rows if r["error"])
    print(f"done: {len(rows) - failed - blocked} fetched, {failed} failed, {blocked} blocked", file=sys.stderr)
    return 1 if failed else 0
