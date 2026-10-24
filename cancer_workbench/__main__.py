"""CLI: python -m cancer_workbench <app|fetch|catalog|route|coordinator|btxrd|baseline> ..."""
from __future__ import annotations

import argparse
import json
import sys


def _catalog(argv: list[str]) -> int:
    from .registry import load_catalog

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench catalog")
    ap.add_argument("cmd", choices=["validate", "show"])
    ap.add_argument("id", nargs="?")
    args = ap.parse_args(argv)
    cat = load_catalog()
    if args.cmd == "validate":
        errs = cat.validate()
        print("\n".join(errs) or f"ok: {len(cat.models)} models, {len(cat.datasets)} datasets")
        return 1 if errs else 0
    rec = cat.get(args.id or "")
    if rec is None:
        print(f"unknown id {args.id!r}", file=sys.stderr)
        return 1
    print(json.dumps(rec, indent=2))
    return 0


def _route(argv: list[str]) -> int:
    from .registry import load_catalog
    from .routing import route_models

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench route")
    ap.add_argument("--task", required=True)
    ap.add_argument("--modality", required=True)
    ap.add_argument("--anatomy", required=True)
    ap.add_argument("--channels", type=int)
    ap.add_argument("--spatial-dims", type=int)
    a = ap.parse_args(argv)
    inp = {k: v for k, v in (("channels", a.channels), ("spatial_dims", a.spatial_dims)) if v is not None}
    print(json.dumps(route_models({"task": a.task, "modality": a.modality, "anatomy": a.anatomy, "input": inp}, load_catalog().models), indent=2))
    return 0


def _coordinator(argv: list[str]) -> int:
    from .coordinator import ProviderError, default_toolbox, load_profiles, make_provider, run_turn
    from .registry import load_catalog

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench coordinator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profiles", help="list configured endpoint profiles")
    p = sub.add_parser("ping", help="GET /models on each profile")
    p.add_argument("profiles", nargs="*")
    p = sub.add_parser("ask", help="one tool-using turn against one or more profiles")
    p.add_argument("question")
    p.add_argument("--profile", action="append", help="repeat to compare several models on the same question")
    p.add_argument("--json", action="store_true", help="print the full transcript")
    a = ap.parse_args(argv)

    profiles, default = load_profiles()
    if a.cmd == "profiles":
        for name, p in profiles.items():
            mark = "*" if name == default else " "
            print(f"{mark} {name:24} {p.get('model', ''):34} {p.get('base_url', '')}")
        return 0
    if a.cmd == "ping":
        rc = 0
        for name in a.profiles or list(profiles):
            try:
                print(f"{name:24} ok  {make_provider(name).list_models()}")
            except ProviderError as e:
                rc = 1
                print(f"{name:24} DOWN {e}")
        return rc
    toolbox = default_toolbox(load_catalog())
    rc = 0
    for name in a.profile or [None]:
        try:
            rec = run_turn(make_provider(name), toolbox, a.question)
        except ProviderError as e:
            print(f"[{name or default}] {e}", file=sys.stderr)
            rc = 1
            continue
        if a.json:
            print(json.dumps({"profile": name or default, "steps": rec.steps, "messages": rec.messages}, indent=2))
        else:
            calls = [c["name"] for s in rec.steps for c in s["tool_calls"]]
            lat = sum(s["latency_s"] for s in rec.steps)
            print(f"=== {name or default} ({rec.stopped}, tools={calls}, {lat:.1f}s)\n{rec.final}\n")
    return rc


def _btxrd(argv: list[str]) -> int:
    from pathlib import Path

    from .datasets import btxrd, write_manifest

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench btxrd")
    ap.add_argument("cmd", choices=["describe", "manifest"])
    ap.add_argument("--raw-dir", type=Path, default=btxrd.RAW_DIR)
    ap.add_argument("--endpoint", choices=sorted(btxrd.ENDPOINTS), default="three_class")
    ap.add_argument("--out", type=Path, default=btxrd.MANIFEST_PATH)
    ap.add_argument("--no-hash", action="store_true", help="skip per-image sha256")
    a = ap.parse_args(argv)
    if a.cmd == "describe":
        print(json.dumps(btxrd.describe_release(a.raw_dir), indent=2))
        return 0
    rows = btxrd.build_manifest(a.raw_dir, a.endpoint, hash_files=not a.no_hash)
    write_manifest(a.out, rows)
    flagged = sum(1 for r in rows if r["audit_flags"])
    print(f"wrote {len(rows)} rows to {a.out} ({flagged} with audit flags)")
    return 0


def _baseline(argv: list[str]) -> int:
    from .experiments import btxrd_baseline as bb

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench baseline", description=bb.LABEL)
    ap.add_argument("--encoder", action="append", choices=bb.ENCODERS)
    ap.add_argument("--endpoint", action="append", choices=sorted(bb.CLASSES))
    ap.add_argument("--protocol", action="append", choices=bb.PROTOCOLS)
    ap.add_argument("--seed", default="0")
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(argv)
    out = bb.run(a.encoder or bb.ENCODERS, a.endpoint or tuple(bb.CLASSES), a.protocol or bb.PROTOCOLS,
                 seed=a.seed, n_boot=a.n_boot)
    print((out / "summary.md").read_text())
    print(f"wrote {out}")
    return 0


def _app(argv: list[str]) -> int:
    from .app.server import serve

    ap = argparse.ArgumentParser(prog="python -m cancer_workbench app")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    serve(a.port, open_browser=not a.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"fetch": None, "catalog": _catalog, "route": _route, "coordinator": _coordinator, "btxrd": _btxrd, "baseline": _baseline, "app": _app}
    if not argv or argv[0] not in commands:
        print(__doc__ + "\n  app          open the local researcher app in your browser\n"
              "  fetch        list/plan/get datasets and weights\n  catalog      validate/show catalog records\n"
              "  route        list compatible models for a task\n  coordinator  profiles/ping/ask OpenAI-compatible endpoints\n"
              "  btxrd        describe the BTXRD release / build its manifest\n"
              "  baseline     exploratory frozen-encoder baseline on BTXRD (needs the ml extra)")
        return 0 if not argv else 2
    if argv[0] == "fetch":
        from .acquisition.fetch import main as fetch_main

        return fetch_main(argv[1:])
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
