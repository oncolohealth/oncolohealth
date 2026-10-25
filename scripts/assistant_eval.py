"""Ask the running Assistant a fixed set of researcher questions and score the answers.

Talks to a running workbench over HTTP, exactly as the chat page does: it reads the
per-launch token from the page, resolves reserved samples through /api/research and
streams each question through /api/coordinator/ask/stream on the default profile.
Writes a JSON-lines trace and a Markdown pass/fail table. Checks are loose software
checks (tools used, phrases present or absent), never medical findings.

    python scripts/assistant_eval.py --base http://localhost:8766 --out-dir DIR [--only ID ...] [--include-slow]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

CASES_PATH = Path(__file__).with_name("assistant_eval_cases.json")


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return cases


def check(case: dict, final: str, tools: list[str], stopped: str | None, error: str | None) -> list[str]:
    """Return the reasons a case failed; an empty list means it passed."""
    if error:
        return [f"error: {error}"]
    problems = []
    if stopped != "answered":
        problems.append(f"stopped={stopped}")
    text = (final or "").lower()
    if not text.strip():
        problems.append("empty answer")
    used = set(tools)
    if case.get("expect_tools_any") and not used & set(case["expect_tools_any"]):
        problems.append("no tool from " + "/".join(case["expect_tools_any"]))
    for name in case.get("expect_tools_all", []):
        if name not in used:
            problems.append(f"did not call {name}")
    for name in case.get("forbid_tools", []):
        if name in used:
            problems.append(f"called {name}")
    for phrase in case.get("must_include_all", []):
        if phrase.lower() not in text:
            problems.append(f"missing '{phrase}'")
    anyof = case.get("must_include_any")
    if anyof and not any(p.lower() in text for p in anyof):
        problems.append("none of: " + ", ".join(anyof[:4]) + ("…" if len(anyof) > 4 else ""))
    for phrase in case.get("must_not_include", []):
        if phrase.lower() in text:
            problems.append(f"says '{phrase}'")
    return problems


class Workbench:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        page = urllib.request.urlopen(self.base + "/", timeout=30).read().decode("utf-8")
        found = re.search(r'name="cw-token" content="([^"]+)"', page)
        if not found:
            raise SystemExit("Could not read the app token from the page; is this the workbench?")
        self.token = found.group(1)

    def _request(self, path: str, body: dict | None = None, timeout: float = 60):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, headers={"X-CW-Token": self.token, "Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=timeout)

    def samples(self) -> dict[str, str]:
        with self._request("/api/research") as resp:
            return {s["model_id"]: s["input_id"] for s in json.load(resp).get("samples", [])}

    def ask(self, question: str, attachments: list[dict], timeout: float) -> list[dict]:
        events = []
        with self._request("/api/coordinator/ask/stream", {"question": question, "attachments": attachments}, timeout) as resp:
            for line in resp:
                if line.strip():
                    events.append(json.loads(line))
        return events


def attachments_for(case: dict, samples: dict[str, str]) -> list[dict]:
    out = []
    for item in case.get("attach", []):
        if item["sample"] not in samples:
            raise KeyError(f"no reserved sample for {item['sample']}")
        entry = {"input_id": samples[item["sample"]]}
        if item.get("workflow"):
            entry["workflow_id"] = item["sample"]
        out.append(entry)
    return out


def run_case(bench: Workbench, case: dict, samples: dict[str, str], timeout: float) -> dict:
    started = time.monotonic()
    final, stopped, error, tools, events = "", None, None, [], []
    try:
        events = bench.ask(case["question"], attachments_for(case, samples), timeout)
        tools = [e["name"] for e in events if e.get("type") == "tool_call"]
        done = next((e["result"] for e in events if e.get("type") == "done"), None)
        if done is None:
            error = "stream ended without a done event"
        else:
            final, stopped, error = done.get("final") or "", done.get("stopped"), done.get("error")
    except Exception as exc:  # network, timeout or HTTP error: record and keep going
        error = f"{type(exc).__name__}: {exc}"
    problems = check(case, final, tools, stopped, error)
    return {"id": case["id"], "group": case.get("group"), "question": case["question"],
            "seconds": round(time.monotonic() - started, 1), "tools": tools, "stopped": stopped,
            "error": error, "passed": not problems, "problems": problems, "final": final,
            "events": [e for e in events if e.get("type") != "done"]}


def markdown(results: list[dict], base: str, started: str) -> str:
    passed = sum(r["passed"] for r in results)
    lines = [f"# Assistant evaluation, {started}", "",
             f"Endpoint `{base}/api/coordinator/ask/stream`, default profile. {passed}/{len(results)} cases passed.",
             "These are loose software checks of tool use and wording, not medical findings.", "",
             "| Case | Group | Result | Seconds | Tools | Problems |", "|---|---|---|---|---|---|"]
    for r in results:
        problems = "; ".join(r["problems"]).replace("|", "/")
        lines.append(f"| {r['id']} | {r['group']} | {'pass' if r['passed'] else 'FAIL'} | {r['seconds']} | "
                     f"{', '.join(r['tools']) or '-'} | {problems or '-'} |")
    lines += ["", "## Answers", ""]
    for r in results:
        lines += [f"### {r['id']} ({'pass' if r['passed'] else 'FAIL'})", "", f"**Q:** {r['question']}", "",
                  (r["final"] or f"_(no answer: {r['error'] or r['stopped']})_"), ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://localhost:8766")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--only", nargs="+", help="run only these case ids")
    parser.add_argument("--include-slow", action="store_true", help="also run cases marked slow (full MRI/CT, minutes each)")
    parser.add_argument("--timeout", type=float, default=900, help="seconds per case")
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.only:
        unknown = set(args.only) - {c["id"] for c in cases}
        if unknown:
            parser.error("unknown case ids: " + ", ".join(sorted(unknown)))
        cases = [c for c in cases if c["id"] in args.only]
    elif not args.include_slow:
        cases = [c for c in cases if not c.get("slow")]
    bench = Workbench(args.base)
    samples = bench.samples()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = args.out_dir / f"OncoloHealth-Claude-assistant-eval-{stamp}.jsonl"
    results = []
    with trace_path.open("x", encoding="utf-8") as trace:
        for case in cases:
            result = run_case(bench, case, samples, args.timeout)
            results.append(result)
            trace.write(json.dumps(result, ensure_ascii=False) + "\n")
            trace.flush()
            print(f"{'pass' if result['passed'] else 'FAIL'} {case['id']} ({result['seconds']}s) {'; '.join(result['problems'])}", flush=True)
    report = args.out_dir / f"OncoloHealth-Claude-assistant-eval-{stamp}.md"
    with report.open("x", encoding="utf-8") as stream:
        stream.write(markdown(results, bench.base, stamp))
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed; report {report}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
