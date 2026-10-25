"""LLM providers behind one interface, so the coordinator model stays swappable.

`OpenAICompatibleProvider` talks to any server implementing POST /chat/completions:
vLLM, SGLang, llama.cpp server, Ollama, LM Studio, TGI, or hosted gateways.
Several endpoints/models can be configured side by side as named profiles
(see configs/coordinator.example.json) and compared on the same workflows.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.parse
from typing import Any, Protocol

from ..acquisition.download import _HTTPHandler, _HTTPSHandler  # IPv6 -> IPv4 fallback on dead-IPv6 networks


@dataclasses.dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as returned by the model; parsed by the loop


@dataclasses.dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str | None
    model: str
    profile: str
    usage: dict[str, Any] = dataclasses.field(default_factory=dict)
    latency_s: float = 0.0
    reasoning: str | None = None  # kept for debugging only; not stored as training data
    raw: dict[str, Any] = dataclasses.field(default_factory=dict, repr=False)

    def assistant_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return msg


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    profile: str

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **params: Any) -> ChatResult: ...


class _SameOriginRedirects(urllib.request.HTTPRedirectHandler):
    """A configured model endpoint must not redirect requests to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        def origin(url):
            p = urllib.parse.urlsplit(url)
            return p.scheme.lower(), p.hostname, p.port or (443 if p.scheme == "https" else 80)

        if origin(req.full_url) != origin(newurl):
            raise ProviderError("Model endpoint redirected to another origin; request refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclasses.dataclass
class OpenAICompatibleProvider:
    profile: str
    base_url: str  # e.g. http://gpu-box:8000/v1
    model: str
    api_key_env: str | None = None
    timeout_s: float = 120.0
    default_params: dict[str, Any] = dataclasses.field(default_factory=dict)
    extra_body: dict[str, Any] = dataclasses.field(default_factory=dict)  # server-specific fields
    supports_tools: bool = True
    require_api_key: bool = False
    extra_headers_env: dict[str, str] = dataclasses.field(default_factory=dict)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if self.require_api_key and not key:
            raise ProviderError(f"[{self.profile}] missing required credential environment variable {self.api_key_env!r}")
        if key:
            h["Authorization"] = f"Bearer {key}"
        if not isinstance(self.extra_headers_env, dict):
            raise ProviderError(f"[{self.profile}] extra_headers_env must map header names to environment-variable names")
        reserved = {"authorization", "host", "content-type", "content-length", "connection", "transfer-encoding"}
        for name, env in self.extra_headers_env.items():
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]+", name)
                    or name.lower() in reserved or not isinstance(env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env)):
                raise ProviderError(f"[{self.profile}] invalid extra_headers_env entry")
            value = os.environ.get(env)
            if value:
                if "\r" in value or "\n" in value:
                    raise ProviderError(f"[{self.profile}] invalid header value from environment variable {env!r}")
                h[name] = value
        return h

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = self.base_url.rstrip("/") + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._headers())
        try:
            opener = urllib.request.build_opener(_SameOriginRedirects(), _HTTPHandler, _HTTPSHandler)
            with opener.open(req, timeout=self.timeout_s) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise ProviderError(f"[{self.profile}] HTTP {e.code} from {url}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise ProviderError(f"[{self.profile}] cannot reach {url}: {e}") from e

    def list_models(self) -> list[str]:
        return [m["id"] for m in self._request("GET", "/models").get("data", [])]

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **params: Any) -> ChatResult:
        body: dict[str, Any] = {"model": self.model, "messages": messages, **self.default_params, **params}
        if tools:
            if not self.supports_tools:
                raise ProviderError(f"[{self.profile}] profile is configured without tool-calling support")
            body["tools"] = tools
        body.update(self.extra_body)
        t0 = time.monotonic()
        raw = self._request("POST", "/chat/completions", body)
        latency = time.monotonic() - t0
        try:
            choice = raw["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"[{self.profile}] malformed response: {json.dumps(raw)[:300]}") from e
        calls = [
            ToolCall(id=c.get("id") or f"call_{i}", name=c["function"]["name"], arguments=c["function"].get("arguments") or "{}")
            for i, c in enumerate(msg.get("tool_calls") or [])
        ]
        return ChatResult(
            content=msg.get("content"),
            tool_calls=calls,
            finish_reason=choice.get("finish_reason"),
            model=raw.get("model", self.model),
            profile=self.profile,
            usage=raw.get("usage") or {},
            latency_s=latency,
            reasoning=msg.get("reasoning_content") or msg.get("reasoning"),
            raw=raw,
        )


class ScriptedProvider:
    """Deterministic provider for tests: returns pre-written ChatResults in order. SYNTHETIC."""

    def __init__(self, script: list[ChatResult], profile: str = "scripted"):
        self.profile = profile
        self._script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **params: Any) -> ChatResult:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "params": params})
        if not self._script:
            raise ProviderError("scripted provider exhausted")
        return self._script.pop(0)
