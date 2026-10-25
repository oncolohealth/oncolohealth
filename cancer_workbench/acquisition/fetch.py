"""Plan and execute fetches for catalog records, writing a PROVENANCE.json per artifact."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Callable

from ..common.paths import DATA_DIR, MODELS_DIR
from ..registry.store import Catalog, load_catalog
from . import budget
from .download import download, hash_file, safe_extract_zip
from .sources import AccessError, FilePlan, resolve
from .subsets import resolve_subset, summarize_units

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
            if p.size is not None:
                total += p.size
            elif p.approx_size is not None:
                total += p.approx_size * (2 if p.extract else 1)  # the extracted copy stays next to the archive
            else:
                total += int(record["acquisition"].get("approx_bytes", 0) / max(len(plans), 1))
    return total


def plan(records: list[dict], subsets: dict[str, dict] | None = None) -> list[dict]:
    """Resolve each record to files. `subsets` maps a record id to a selection (see subsets.py)."""
    rows = []
    for r in records:
        acq = r.get("acquisition", {})
        row = {"id": r["id"], "tier": acq.get("tier"), "fetcher": acq.get("fetcher"), "plans": [], "error": None, "selection": None}
        try:
            if (subsets or {}).get(r["id"]) is not None:
                row["plans"], row["selection"] = resolve_subset(acq, subsets[r["id"]], target_dir(r))
            elif (acq.get("subset") or {}).get("required"):
                raise AccessError(f"too large to fetch whole; choose a subset of {acq['subset']['unit']}s first")
            else:
                row["plans"] = resolve(acq)
            row["bytes"] = remaining_bytes(r, row["plans"])
        except (AccessError, ValueError) as e:
            row["error"] = str(e)
            row["bytes"] = 0
        except OSError as e:  # URLError, timeouts: report per record instead of failing the whole plan
            row["error"] = f"could not reach the source: {e}"
            row["bytes"] = 0
        rows.append(row)
    return rows


def write_provenance(record: dict, plans: list[FilePlan], files: list[dict], selection: dict | None = None) -> Path:
    """Write PROVENANCE.json, keeping files and selections from earlier fetches of the same record."""
    path = target_dir(record) / "PROVENANCE.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    by_path = {f["path"]: f for f in old.get("files", [])}
    by_path.update({f["path"]: f for f in files})
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    selections = list(old.get("selections", []))
    if selection is not None or record["acquisition"].get("subset"):
        selections.append({"retrieved_at": now, **(selection or {"mode": "default"}), "files_fetched": len(files)})
    prov = {
        "id": record["id"],
        "kind": record["_kind"],
        "name": record.get("name"),
        "license": record.get("license"),
        "source": {k: v for k, v in record["acquisition"].items() if k not in ("instructions",)},
        "citation": record.get("citation"),
        "retrieved_at": now,
        "files": list(by_path.values()),
        "note": "Hashes verify file identity/integrity only, not medical correctness of labels.",
    }
    if selections:
        prov["selections"] = selections
    path.write_text(json.dumps(prov, indent=2) + "\n")
    return path


def fetch(record: dict, plans: list[FilePlan], *, extract: bool = True, quiet: bool = False,
          on_progress: Callable[[str, int, int | None], None] | None = None, selection: dict | None = None) -> Path:
    """Download every planned file. `on_progress(relpath, bytes_done, bytes_total)` is called per chunk."""
    root = target_dir(record)
    files = []
    for p in plans:
        dest = root / p.relpath
        if not quiet:
            print(f"[{record['id']}] {p.relpath}", file=sys.stderr)
        cb = (lambda done, total, rel=p.relpath: on_progress(rel, done, total)) if on_progress else None
        download(p.url, dest, size=p.size, md5=p.md5, sha256=p.sha256, headers=p.headers, quiet=quiet, progress=cb)
        h = hash_file(dest)
        files.append({"path": p.relpath, "url": p.url, "integrity": p.integrity, **({"group": p.group} if p.group else {}), **h})
        if extract and p.extract:
            out = dest.with_suffix("")
            if not out.exists():
                if not quiet:
                    print(f"  extracting -> {out.relative_to(root)}", file=sys.stderr)
                safe_extract_zip(dest, out)
    return write_provenance(record, plans, files, selection)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench fetch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show catalog records with tier, size and local status")
    u = sub.add_parser("units", help="list the patients/files/slides a subset-capable record offers")
    u.add_argument("id")
    u.add_argument("--query", help="narrowing search (ISIC only)")
    for name in ("plan", "get"):
        p = sub.add_parser(name)
        p.add_argument("ids", nargs="*")
        p.add_argument("--tier", choices=TIERS)
        g = p.add_mutually_exclusive_group()
        g.add_argument("--sample", type=int, metavar="N", help="subset: N whole groups not yet on disk, in seeded order")
        g.add_argument("--pick", nargs="+", metavar="ID", help="subset: these group or unit ids")
        p.add_argument("--seed", type=int, default=0, help="seed for --sample (default 0)")
        p.add_argument("--query", help="subset: narrowing search (ISIC only)")
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
        print(f"\nused {used / 1e9:.2f} GB; budget {budget.describe(budget.budget_bytes())}")
        return 0

    if args.cmd == "units":
        rec = catalog.get(args.id)
        if rec is None:
            ap.error(f"unknown catalog id {args.id!r}")
        try:
            info = summarize_units(rec["acquisition"], target_dir(rec), args.query)
        except (AccessError, ValueError) as e:
            print(f"BLOCKED: {e}", file=sys.stderr)
            return 2
        for g in info["groups"]:
            print(f"{g['id']:48} {g['units']:4} {g['bytes'] / 1e6:10.1f} MB  {'on disk' if g['on_disk'] else '-':8} {g['detail']}")
        print(f"\n{len(info['groups'])} {info['unit'] or 'group'}s, {info['population_units']} units; integrity: {', '.join(info['integrity'])}")
        return 0

    if not args.ids and not args.tier:
        ap.error("give catalog ids or --tier")
    subsets = None
    if args.sample is not None or args.pick or args.query:
        if args.tier or len(args.ids) != 1:
            ap.error("--sample/--pick/--query apply to exactly one catalog id")
        if args.sample is None and not args.pick:
            ap.error("--query needs --sample or --pick")
        sel = {"mode": "sample", "count": args.sample, "seed": args.seed} if args.sample is not None else {"mode": "ids", "ids": args.pick}
        if args.query:
            sel["query"] = args.query
        subsets = {args.ids[0]: sel}
    records = select(catalog, args.ids, args.tier)
    rows = plan(records, subsets)
    total = sum(r["bytes"] for r in rows if not r["error"])
    for r in rows:
        status = f"BLOCKED: {r['error']}" if r["error"] else f"{len(r['plans'])} files, {r['bytes'] / 1e9:.2f} GB to fetch"
        print(f"{r['id']:38} {status}")
        sel = r["selection"]
        if sel:
            short = f", {sel['short_by']} fewer than asked (none left)" if sel.get("short_by") else ""
            skipped = f", {sel['skipped_on_disk']} already on disk skipped" if sel.get("skipped_on_disk") else ""
            print(f"{'':38} {len(sel['groups'])} of {sel['population_groups']} {sel['unit']}s{skipped}{short}")
    fits, used, cap = budget.check(total)
    print(f"\nplanned {total / 1e9:.2f} GB; used {used / 1e9:.2f} GB; budget {budget.describe(cap)} -> {'OK' if fits else 'OVER BUDGET'}")
    if args.cmd == "plan":
        return 0

    if not fits:
        print("Refusing: over budget. Raise or unset CW_STORAGE_BUDGET_GB, or fetch fewer records.", file=sys.stderr)
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
            print(f"wrote {fetch(rec, row['plans'], selection=row['selection'])}", file=sys.stderr)
        except Exception as e:  # keep going; report every failure at the end
            failed += 1
            print(f"[{rec['id']}] FAILED: {e}", file=sys.stderr)
    blocked = sum(1 for r in rows if r["error"])
    print(f"done: {len(rows) - failed - blocked} fetched, {failed} failed, {blocked} blocked", file=sys.stderr)
    return 1 if failed else 0
