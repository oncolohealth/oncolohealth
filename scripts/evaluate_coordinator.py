"""Run bounded public development workflows. Default: offline scripted smoke."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cancer_workbench.coordinator.config import make_provider
from cancer_workbench.coordinator.evaluation import SUITE_PATH, evaluate_suite, load_suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "live"), default="smoke")
    parser.add_argument("--profile", help="explicit configured profile required for live mode")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--max-steps", type=int, default=6, choices=range(1, 9))
    parser.add_argument("--limit", type=int, choices=range(1, 51))
    parser.add_argument("--out", type=Path, help="new report path (existing files are never overwritten)")
    args = parser.parse_args()
    if args.mode == "live" and not args.profile:
        parser.error("live mode requires --profile and may incur provider API charges")
    if args.mode == "smoke" and (args.profile or args.config):
        parser.error("--profile and --config only apply to live mode")
    if args.out and args.out.exists():
        parser.error("--out already exists; choose a new report path")
    suite = load_suite(args.suite)
    factory = (lambda case: make_provider(args.profile, args.config)) if args.mode == "live" else None
    report = evaluate_suite(suite, mode=args.mode, provider_factory=factory,
                            max_steps=args.max_steps, limit=args.limit)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x") as stream:
            stream.write(text)
    else:
        print(text, end="")
    return 0 if report["summary"]["fail"] == report["summary"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
