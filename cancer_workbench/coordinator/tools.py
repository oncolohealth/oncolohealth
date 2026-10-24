"""Tools the coordinator may call. Each tool = JSON schema + a Python handler.

Handlers return JSON-serialisable observed results. Errors are returned as
{"error": ...} so the model sees the real failure instead of an invented answer.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable

from ..adapters.base import Adapter, execute_specialist
from ..registry.store import Catalog
from ..routing.router import route_models

_PUBLIC_FIELDS = ("id", "name", "kind", "summary", "tasks", "modality", "anatomy", "input", "outputs",
                  "license", "access", "evidence_state", "inference_permission", "counts", "labels",
                  "unresolved", "known_overlap", "citation")


@dataclasses.dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolBox:
    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def call(self, name: str, arguments: str) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name!r}; available: {sorted(self.tools)}"}
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return {"error": f"arguments are not valid JSON: {e}"}
        if not isinstance(args, dict):
            return {"error": "arguments must be a JSON object"}
        missing = [k for k in tool.parameters.get("required", []) if k not in args]
        if missing:
            return {"error": f"missing required arguments: {missing}"}
        unknown = set(args) - set(tool.parameters.get("properties", {}))
        if unknown:
            return {"error": f"unknown arguments: {sorted(unknown)}"}
        try:
            return {"result": tool.handler(**args)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


def _public(rec: dict) -> dict:
    return {k: rec[k] for k in _PUBLIC_FIELDS if k in rec} | {"record_type": rec.get("_kind")}


def default_toolbox(catalog: Catalog, adapters: dict[str, Adapter] | None = None, extra_models: list[dict] | None = None) -> ToolBox:
    adapters = adapters or {}
    models = catalog.models + [dict(m, _kind="model") for m in (extra_models or [])]
    by_id = {m["id"]: m for m in models} | {d["id"]: d for d in catalog.datasets}

    def search_catalog(query: str = "", record_type: str | None = None) -> list[dict]:
        pool = [r for r in list(by_id.values()) if record_type in (None, r["_kind"])]
        q = query.lower()
        hits = [r for r in pool if q in json.dumps(_public(r)).lower()]
        return [{"id": r["id"], "name": r.get("name"), "record_type": r["_kind"], "evidence_state": r.get("evidence_state")} for r in hits[:20]]

    def get_record(id: str) -> dict:
        if id not in by_id:
            raise KeyError(f"no catalog record {id!r}")
        return _public(by_id[id])

    def route(task: str, modality: str, anatomy: str, channels: int | None = None, spatial_dims: int | None = None) -> dict:
        inp = {k: v for k, v in (("channels", channels), ("spatial_dims", spatial_dims)) if v is not None}
        return route_models({"task": task, "modality": modality, "anatomy": anatomy, "input": inp}, models)

    def run_specialist(model_id: str, task: str, modality: str, anatomy: str, inputs: dict, input_refs: list | None = None) -> dict:
        model = next((m for m in models if m["id"] == model_id), None)
        if model is None:
            raise KeyError(f"no model {model_id!r}")
        req = {"task": task, "modality": modality, "anatomy": anatomy, "inputs": inputs, "input_refs": input_refs or []}
        return execute_specialist(model, req, adapters).to_dict()

    s = {"type": "string"}
    return ToolBox([
        Tool("search_catalog", "Search the model/dataset catalog. Returns ids and evidence states.",
             {"type": "object", "properties": {"query": s, "record_type": {"type": "string", "enum": ["model", "dataset"]}}}, search_catalog),
        Tool("get_record", "Get one catalog record: license, access, inputs, outputs, evidence state, unresolved issues.",
             {"type": "object", "properties": {"id": s}, "required": ["id"]}, get_record),
        Tool("route_models", "List models compatible/incompatible with a task. Does not run anything.",
             {"type": "object", "properties": {"task": s, "modality": s, "anatomy": s, "channels": {"type": "integer"}, "spatial_dims": {"type": "integer"}},
              "required": ["task", "modality", "anatomy"]}, route),
        Tool("run_specialist", "Run an installed, eligible specialist. Returns an observed result envelope or the rejection/failure.",
             {"type": "object", "properties": {"model_id": s, "task": s, "modality": s, "anatomy": s, "inputs": {"type": "object"},
                                               "input_refs": {"type": "array", "items": s}},
              "required": ["model_id", "task", "modality", "anatomy", "inputs"]}, run_specialist),
    ])
