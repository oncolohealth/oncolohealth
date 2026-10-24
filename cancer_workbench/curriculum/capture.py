"""Capture candidate tool-use conversations from observed tool results. Owner: Workstream D.

Each scenario in curriculum/scenarios.json names a researcher request, the tool
calls an assistant makes (one list per assistant turn) and, once the observed
results have been read, a drafted final response. `capture` replays the calls
through the coordinator's real loop (`run_turn`) against the real toolbox, so
every tool message is exactly what the product returns, then writes one
candidate per scenario with call/result ids, exact schemas, source identities
and pending review fields.

A drafted response is tied to the digest of the observed results it was
written against (`response_for`). If a later capture observes something
different, the candidate is marked `stale_response` instead of silently pairing
old prose with new results. Nothing here admits a candidate to training; see
`export_curriculum`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from ..common.paths import CATALOG_DIR, PROJECT_ROOT

CURRICULUM_DIR = PROJECT_ROOT / "curriculum"
SPLITS = ("train_candidate", "development", "evaluation_reserved")
# Fields that change on every run and say nothing about what was observed.
VOLATILE = {"run_id", "created_at", "seconds", "latency_s"}
THINKING_MODE = "off: scripted tool calls and a drafted final response; no reasoning trace is recorded or included"
RESPONSE_ORIGIN = "drafted by Claude Code (Claude Opus 5.5) from the observed tool results; pending human review"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def observed_digest(observed: list[dict]) -> str:
    return hashlib.sha256(_canonical(_strip_volatile(observed)).encode()).hexdigest()


def _git_head() -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "cancer_workbench", "catalog"], cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, check=True).stdout.strip())
        return {"commit": head, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def source_identities() -> dict:
    files = {}
    for name in ("models.json", "datasets.json", "cards.json", "workflows.json"):
        path = CATALOG_DIR / name
        if path.exists():
            files[f"catalog/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"git": _git_head(), "files": files}


def load_scenarios(path: Path | None = None, responses: Path | None = None) -> list[dict]:
    """Scenarios plus their drafted responses ({id: {response, response_for}}) from responses.json when present."""
    data = json.loads(Path(path or CURRICULUM_DIR / "scenarios.json").read_text())
    rpath = Path(responses or CURRICULUM_DIR / "responses.json")
    drafted = json.loads(rpath.read_text())["responses"] if rpath.exists() else {}
    unknown = sorted(set(drafted) - {sc["id"] for sc in data["scenarios"]})
    if unknown:
        raise ValueError(f"responses for unknown scenarios: {unknown}")
    scenarios, seen = [dict(sc, **drafted.get(sc["id"], {})) for sc in data["scenarios"]], set()
    for sc in scenarios:
        if sc["id"] in seen:
            raise ValueError(f"duplicate scenario id {sc['id']!r}")
        seen.add(sc["id"])
        if sc.get("split") not in SPLITS:
            raise ValueError(f"{sc['id']}: split must be one of {SPLITS}")
        if not sc.get("lineage_group") or not sc.get("user") or not isinstance(sc.get("turns"), list) or not sc["turns"]:
            raise ValueError(f"{sc['id']}: needs lineage_group, user and at least one turn of calls")
    groups: dict[str, set] = {}
    for sc in scenarios:
        groups.setdefault(sc["lineage_group"], set()).add(sc["split"])
    mixed = sorted(g for g, s in groups.items() if len(s) > 1)
    if mixed:
        raise ValueError(f"lineage groups span splits: {mixed}")
    return scenarios


def capture_one(scenario: dict, toolbox) -> dict:
    from ..coordinator.loop import run_turn
    from ..coordinator.providers import ChatResult, ScriptedProvider, ToolCall

    cid = scenario["id"]
    script, call_ids = [], []
    for t, turn in enumerate(scenario["turns"]):
        calls = []
        for c, call in enumerate(turn):
            call_id = f"{cid}.t{t}.c{c}"
            call_ids.append(call_id)
            calls.append(ToolCall(call_id, call["name"], json.dumps(call["arguments"], sort_keys=True)))
        script.append(ChatResult(None, calls, "tool_calls", "scripted-capture", "capture"))
    final = scenario.get("response")
    script.append(ChatResult(final or "[response pending]", [], "stop", "scripted-capture", "capture"))
    record = run_turn(ScriptedProvider(script, profile="scripted-capture"), toolbox, scenario["user"], max_steps=len(script))
    schemas = {s["function"]["name"]: s for s in toolbox.schemas()}
    calls, observed = [], []
    for step in record.steps:
        for tc in step["tool_calls"]:
            out = tc["observed"]
            res = out.get("result")
            result_id = res.get("run_id") if isinstance(res, dict) and res.get("run_id") else \
                "sha256:" + hashlib.sha256(_canonical(_strip_volatile(out)).encode()).hexdigest()
            calls.append({"call_id": call_ids[len(calls)], "name": tc["name"], "arguments": json.loads(tc["arguments"]),
                          "schema": schemas.get(tc["name"]), "result_id": result_id,
                          "outcome": "error" if "error" in out else (res.get("status", "ok") if isinstance(res, dict) else "ok"),
                          "observed": out})
            observed.append(out)
    digest = observed_digest(observed)
    if not final:
        state = "needs_response"
    elif scenario.get("response_for") != digest:
        state = "stale_response"
    else:
        state = "pending_review"
    messages = record.messages[:-1] + ([record.messages[-1]] if final else [])
    return {
        "candidate_id": f"sebastian-2026-10-24/{cid}",
        "conversation_id": cid,
        "family": scenario["family"],
        "lineage_group": scenario["lineage_group"],
        "split": scenario["split"],
        "thinking_mode": THINKING_MODE,
        "user": scenario["user"],
        "messages": messages,
        "calls": calls,
        "observed_digest": digest,
        "response_origin": RESPONSE_ORIGIN if final else None,
        "state": state,
        "review": {"status": "pending", "reviewer": None, "reviewed_at": None,
                   "rights_status": "pending", "rights_notes": scenario.get("rights_notes", "Tool results come from this repository's catalog and code. No patient identifiers; image references are BTXRD ids (CC BY 4.0) only."),
                   "notes": None},
        "admitted_to_training": False,
    }


def capture(scenarios: list[dict] | None = None, out_dir: Path | None = None, *, toolbox=None) -> Path:
    from ..adapters.installed import installed_adapters
    from ..coordinator.tools import default_toolbox
    from ..registry import load_catalog

    scenarios = scenarios if scenarios is not None else load_scenarios()
    out_dir = Path(out_dir or CURRICULUM_DIR)
    installed = None
    if toolbox is None:
        cat = load_catalog()
        adapters = installed_adapters(cat.models)
        installed = sorted(adapters)
        toolbox = default_toolbox(cat, adapters)
    candidates = [capture_one(sc, toolbox) for sc in scenarios]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidates.jsonl").write_text("".join(json.dumps(c, sort_keys=True, default=str) + "\n" for c in candidates))
    counts: dict[str, dict[str, int]] = {}
    for c in candidates:
        for key in ("split", "family", "state"):
            counts.setdefault(key, {}).setdefault(c[key], 0)
            counts[key][c[key]] += 1
    manifest = {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "capturer": "Sebastian with Claude Code (Claude Opus 5.5)",
        "candidates": len(candidates),
        "tool_calls": sum(len(c["calls"]) for c in candidates),
        "counts": counts,
        "sources": source_identities(),
        "tools": [s["function"]["name"] for s in toolbox.schemas()],
        "adapters_installed": installed,
        "environment_note": "run_specialist and route_models results depend on which adapters this process could install; recapture elsewhere marks responses stale if results differ",
        "candidates_file_sha256": hashlib.sha256((out_dir / "candidates.jsonl").read_bytes()).hexdigest(),
        "admission": "none: every candidate is review.status 'pending' and admitted_to_training false; export_curriculum returns only reviewed train candidates",
        "reconcile_with": "Jordi's 44 training + 12 development candidates (140 offline catalog calls) and the original 83/21 pilot are not on this machine; de-duplicate by lineage before any admission",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return out_dir
