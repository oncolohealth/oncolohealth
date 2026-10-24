"""Versioned coordinator trace evaluation, using only catalog and synthetic tools.

Smoke mode checks deterministic plumbing. Live mode measures observed trace
requirements on these public development cases, not held-out reasoning quality.
Final-answer accuracy and scope require a separate human review.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from ..registry import load_catalog
from .loop import SYSTEM_PROMPT, run_turn
from .providers import ChatResult, ScriptedProvider, ToolCall
from .tools import default_toolbox

SUITE_PATH = Path(__file__).resolve().parents[2] / "configs" / "coordinator-evaluation.json"


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load_suite(path: Path = SUITE_PATH) -> dict:
    suite = json.loads(path.read_text())
    if (not isinstance(suite, dict) or type(suite.get("schema_version")) is not int
            or suite["schema_version"] != 1 or not isinstance(suite.get("suite_id"), str)
            or not suite["suite_id"] or not isinstance(suite.get("cases"), list) or not suite["cases"]):
        raise ValueError("expected a nonempty schema_version=1 evaluation suite")
    ids = set()
    for case in suite["cases"]:
        if not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("case IDs must be unique nonempty strings")
        ids.add(case["id"])
        if (not isinstance(case.get("request"), str) or not case["request"]
                or not case.get("script_calls") or not case.get("expectations")
                or not set(case.get("modes", [])) <= {"smoke", "live"} or not case.get("modes")):
            raise ValueError(f"invalid evaluation case {case['id']}")
        for call in case["script_calls"]:
            if not isinstance(call.get("name"), str) or not isinstance(call.get("arguments"), dict):
                raise ValueError("script calls need a tool name and argument object")
        for exp in case["expectations"]:
            if (not isinstance(exp.get("tool"), str) or not isinstance(exp.get("arguments", {}), dict)
                    or not isinstance(exp.get("path"), list) or "equals" not in exp):
                raise ValueError("expectations need a tool, path and equals value")
    _digest(suite)  # refuse non-finite JSON fixtures
    return suite


def evaluation_toolbox():
    """No installed medical adapter is exposed, even on a collaborator machine."""
    failure = dict(SYNTHETIC_MODEL_RECORD, id="synthetic-failure-model",
                   name="Synthetic failure fixture", adapter="synthetic-failure")
    return default_toolbox(load_catalog(), {
        "synthetic-threshold": SyntheticThresholdAdapter(),
        "synthetic-failure": SyntheticThresholdAdapter(fail=True),
    }, extra_models=[SYNTHETIC_MODEL_RECORD, failure])


def scripted_provider(case: dict):
    calls = [ToolCall(f"fixture-{i}", c["name"], json.dumps(c["arguments"]))
             for i, c in enumerate(case["script_calls"])]
    return ScriptedProvider([
        ChatResult(None, calls, "tool_calls", "scripted", "smoke"),
        ChatResult("SYNTHETIC scripted completion. Review the observed tool trace.", [], "stop", "scripted", "smoke"),
    ])


class _RecordingBox:
    def __init__(self):
        self.inner = evaluation_toolbox()
        self.calls = []

    def schemas(self):
        return self.inner.schemas()

    def call(self, name, arguments):
        observed = self.inner.call(name, arguments)
        self.calls.append({"name": name, "arguments": arguments, "observed": copy.deepcopy(observed)})
        return observed


class _RecordingProvider:
    def __init__(self, inner):
        self.inner = inner
        self.requests = []
        self.responses = []

    def chat(self, messages, tools=None, **params):
        # Only prompt/tool messages and public response metadata are retained.
        # No auth headers, credentials, raw payload or private reasoning.
        self.requests.append(copy.deepcopy(messages))
        response = self.inner.chat(messages, tools=tools, **params)
        self.responses.append({"profile": response.profile, "model": response.model,
                               "latency_s": response.latency_s, "usage": response.usage})
        return response


def _equal_json(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _matches(call, exp):
    if call["name"] != exp["tool"]:
        return False
    try:
        arguments = json.loads(call["arguments"])
        if not all(k in arguments and _equal_json(arguments[k], v) for k, v in exp.get("arguments", {}).items()):
            return False
        value = call["observed"]
        for key in exp["path"]:
            value = value[key]
        return _equal_json(value, exp["equals"])
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def evaluate_suite(suite: dict, *, mode: str = "smoke", provider_factory: Callable | None = None,
                   max_steps: int = 6, limit: int | None = None) -> dict:
    if mode not in {"smoke", "live"}:
        raise ValueError("mode must be smoke or live")
    if mode == "live" and provider_factory is None:
        raise ValueError("live mode requires an explicit provider factory")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 8:
        raise ValueError("max_steps must be an integer in [1, 8]")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50):
        raise ValueError("limit must be an integer in [1, 50]")
    cases = [c for c in suite["cases"] if mode in c["modes"]][:limit]
    if not cases:
        raise ValueError("no cases selected")
    results = []
    for case in cases:
        box = _RecordingBox()
        provider = None
        started = time.monotonic()
        row = {"id": case["id"], "request": case["request"], "status": "error", "final": None,
               "stopped": None, "error": None, "answer_review": "unscored"}
        try:
            inner = provider_factory(case) if provider_factory else scripted_provider(case)
            provider = _RecordingProvider(inner)
            turn = run_turn(provider, box, case["request"], max_steps=max_steps)
            row.update(final=turn.final, stopped=turn.stopped)
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        checks = [{"tool": exp["tool"], "path": exp["path"], "equals": exp["equals"],
                   "passed": any(_matches(call, exp) for call in box.calls)} for exp in case["expectations"]]
        # Check the actual next provider request, including a request that fails.
        observed = [c["observed"] for c in box.calls]
        feedback = []
        if provider:
            for request in provider.requests[1:]:
                for msg in request:
                    if msg.get("role") == "tool":
                        try:
                            feedback.append(json.loads(msg["content"]))
                        except (KeyError, TypeError, ValueError):
                            pass
        feedback_ok = bool(observed) and all(any(_equal_json(o, f) for f in feedback) for o in observed)
        if row["error"] is None:
            row["status"] = "pass" if all(c["passed"] for c in checks) and feedback_ok and row["stopped"] == "answered" and bool(row["final"]) else "fail"
        row.update(checks=checks, observed_result_fed_back=feedback_ok, calls=box.calls,
                   responses=provider.responses if provider else [],
                   elapsed_s=round(time.monotonic() - started, 3))
        results.append(row)
    counts = {status: sum(r["status"] == status for r in results) for status in ("pass", "fail", "error")}
    catalog = load_catalog()
    return {"schema_version": 1, "suite_id": suite["suite_id"], "suite_sha256": _digest(suite),
            "catalog_sha256": _digest({"models": catalog.models, "datasets": catalog.datasets}),
            "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
            "scope": "Public development scenarios. Synthetic execution only. No medical inference. Human answer review is unscored.",
            "max_steps": max_steps, "summary": {"cases": len(results), **counts,
                "trace_pass_rate": counts["pass"] / len(results) if mode == "live" else None,
                "reasoning_quality_score": None}, "cases": results}
