"""Minimal tool-calling loop: model proposes calls, we execute them and feed back observed results."""
from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable

from .providers import ChatResult, Provider
from .tools import ToolBox

LEGACY_SYSTEM_PROMPT = """You are a research coordinator for a cancer AI workspace used by researchers.
- Use tools to look up catalog records and to run specialists; never invent tool results, metrics or predictions.
- Report specialist outputs exactly as returned, including rejections and failures.
- Distinguish cataloged / access_obtained / runnable / locally_reproduced / externally_evaluated evidence.
- If inputs are missing, a model is unavailable, or evidence is insufficient, say so plainly.
- This is a research tool. Do not give patient-specific clinical advice."""

SYSTEM_PROMPT = """You are an evidence-led assistant for medical practitioners and researchers using a cancer AI workspace.
- Help interpret supplied findings and actual model outputs, compare evidence, explain uncertainty and identify useful next investigations.
- Use tools for catalog facts, specialist execution and measured model performance. Never invent results, accuracy, image findings or installed capabilities.
- Lead with the useful answer and its basis. Qualify the specific conclusion proportionately; a medical topic alone is not a reason to refuse legitimate analysis.
- Distinguish model findings, reference agreement, research evaluation and established clinical evidence. Report failures honestly and offer the next feasible step.
- A model score is not automatically a calibrated disease probability or a confirmed diagnosis. Keep that distinction concise and relevant."""


@dataclasses.dataclass
class TurnRecord:
    messages: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    final: str | None
    stopped: str  # "answered" | "max_steps"


def run_turn(provider: Provider, toolbox: ToolBox, user_message: str, *, history: list[dict] | None = None,
             max_steps: int = 6, on_event: Callable[[dict[str, Any]], None] | None = None, **params: Any) -> TurnRecord:
    """Run one user turn. `on_event`, if given, hears about progress as it happens:
    {"type": "model", "step": n} before each model call, {"type": "tool_call", ...} before a tool
    runs and {"type": "tool_result", ...} with its observed result. Raising from it stops the turn."""
    emit = on_event or (lambda event: None)
    messages = list(history) if history else [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": user_message})
    steps: list[dict[str, Any]] = []
    for n in range(max_steps):
        emit({"type": "model", "step": n})
        res: ChatResult = provider.chat(messages, tools=toolbox.schemas(), **params)
        messages.append(res.assistant_message())
        step = {"profile": res.profile, "model": res.model, "latency_s": round(res.latency_s, 3), "usage": res.usage, "tool_calls": []}
        step["finish_reason"] = res.finish_reason
        steps.append(step)
        if not res.tool_calls:
            return TurnRecord(messages, steps, res.content, "response_limit" if res.finish_reason == "length" else "answered")
        for call in res.tool_calls:
            emit({"type": "tool_call", "name": call.name, "arguments": call.arguments})
            observed = toolbox.call(call.name, call.arguments)
            entry = {"name": call.name, "arguments": call.arguments, "observed": observed}
            step["tool_calls"].append(entry)
            emit({"type": "tool_result", **entry})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(observed)})
    return TurnRecord(messages, steps, None, "max_steps")
