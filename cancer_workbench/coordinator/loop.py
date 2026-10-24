"""Minimal tool-calling loop: model proposes calls, we execute them and feed back observed results."""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from .providers import ChatResult, Provider
from .tools import ToolBox

SYSTEM_PROMPT = """You are a research coordinator for a cancer AI workspace used by researchers.
- Use tools to look up catalog records and to run specialists; never invent tool results, metrics or predictions.
- Report specialist outputs exactly as returned, including rejections and failures.
- Distinguish cataloged / access_obtained / runnable / locally_reproduced / externally_evaluated evidence.
- If inputs are missing, a model is unavailable, or evidence is insufficient, say so plainly.
- This is a research tool. Do not give patient-specific clinical advice."""


@dataclasses.dataclass
class TurnRecord:
    messages: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    final: str | None
    stopped: str  # "answered" | "max_steps"


def run_turn(provider: Provider, toolbox: ToolBox, user_message: str, *, history: list[dict] | None = None,
             max_steps: int = 6, **params: Any) -> TurnRecord:
    messages = list(history) if history else [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": user_message})
    steps: list[dict[str, Any]] = []
    for _ in range(max_steps):
        res: ChatResult = provider.chat(messages, tools=toolbox.schemas(), **params)
        messages.append(res.assistant_message())
        step = {"profile": res.profile, "model": res.model, "latency_s": round(res.latency_s, 3), "usage": res.usage, "tool_calls": []}
        steps.append(step)
        if not res.tool_calls:
            return TurnRecord(messages, steps, res.content, "answered")
        for call in res.tool_calls:
            observed = toolbox.call(call.name, call.arguments)
            step["tool_calls"].append({"name": call.name, "arguments": call.arguments, "observed": observed})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(observed)})
    return TurnRecord(messages, steps, None, "max_steps")
