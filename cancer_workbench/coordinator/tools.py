"""Tools the coordinator may call. Each tool = JSON schema + a Python handler.

Handlers return JSON-serialisable observed results. Errors are returned as
{"error": ...} so the model sees the real failure instead of an invented answer.
"""
from __future__ import annotations

import dataclasses
import json
import math
from typing import Any, Callable

from ..adapters.base import Adapter, execute_specialist
from ..registry.store import Catalog
from ..routing.router import route_models
from ..retrieval.datasets import search_public_datasets, list_tcga_files
from ..learning.requirements import get_training_requirements

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
        # Top-level tool arguments remain closed, as before. Nested objects
        # follow their own schemas (open unless additionalProperties is false).
        schema = dict(tool.parameters, additionalProperties=False)
        problems = _argument_errors(args, schema)
        if problems:
            return {"error": "; ".join(problems)}
        try:
            return {"result": tool.handler(**args)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}


def _argument_errors(value: Any, schema: dict, path: str = "arguments") -> list[str]:
    """Validate the JSON-schema subset used by this toolbox, without coercion.

    Supports type, enum, object properties/required/additionalProperties, array
    items/minItems/maxItems, string minLength/maxLength and numeric bounds.
    This is a tool-argument boundary, not a general JSON Schema implementation.
    """
    kinds = {
        "object": lambda x: isinstance(x, dict),
        "array": lambda x: isinstance(x, list),
        "string": lambda x: isinstance(x, str),
        "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        "boolean": lambda x: isinstance(x, bool),
        "null": lambda x: x is None,
    }
    kind = schema.get("type")
    allowed = kind if isinstance(kind, list) else [kind]
    if kind is not None and not any(k in kinds and kinds[k](value) for k in allowed):
        return [f"{path} must have type {kind}"]
    if isinstance(value, float) and not math.isfinite(value):
        return [f"{path} must be finite"]
    if "enum" in schema and not any(_same_json(value, item) for item in schema["enum"]):
        return [f"{path} must be one of {schema['enum']}"]
    errors = []
    if isinstance(value, dict):
        props = schema.get("properties", {})
        missing = [k for k in schema.get("required", []) if k not in value]
        if missing:
            errors.append(f"{path}: missing required arguments: {missing}")
        for key, item in value.items():
            if key in props:
                errors.extend(_argument_errors(item, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unknown arguments: {[key]}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_argument_errors(item, schema["additionalProperties"], f"{path}.{key}"))
            else:
                # Even unconstrained payloads must contain actual finite JSON.
                errors.extend(_argument_errors(item, {}, f"{path}.{key}"))
    elif isinstance(value, list):
        for bound, op in (("minItems", lambda a, b: a < b), ("maxItems", lambda a, b: a > b)):
            if bound in schema and op(len(value), schema[bound]):
                errors.append(f"{path} violates {bound}={schema[bound]}")
        for i, item in enumerate(value):
            errors.extend(_argument_errors(item, schema.get("items", {}), f"{path}[{i}]"))
    elif isinstance(value, str):
        for bound, op in (("minLength", lambda a, b: a < b), ("maxLength", lambda a, b: a > b)):
            if bound in schema and op(len(value), schema[bound]):
                errors.append(f"{path} violates {bound}={schema[bound]}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        for bound, op in (("minimum", lambda a, b: a < b), ("maximum", lambda a, b: a > b),
                          ("exclusiveMinimum", lambda a, b: a <= b), ("exclusiveMaximum", lambda a, b: a >= b)):
            if bound in schema and op(value, schema[bound]):
                errors.append(f"{path} violates {bound}={schema[bound]}")
    return errors


def _same_json(a: Any, b: Any) -> bool:
    """JSON booleans must not match numeric enum members through Python ==."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same_json(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same_json(x, y) for x, y in zip(a, b))
    return a == b


def _public(rec: dict) -> dict:
    return {k: rec[k] for k in _PUBLIC_FIELDS if k in rec} | {"record_type": rec.get("_kind")}


def default_toolbox(catalog: Catalog, adapters: dict[str, Adapter] | None = None, extra_models: list[dict] | None = None, *, online_discovery: bool = True) -> ToolBox:
    adapters = adapters or {}
    models = catalog.models + [dict(m, _kind="model") for m in (extra_models or [])]
    by_id = {m["id"]: m for m in models} | {d["id"]: d for d in catalog.datasets}

    def search_catalog(query: str = "", record_type: str | None = None) -> list[dict]:
        pool = [r for r in list(by_id.values()) if record_type in (None, r["_kind"])]
        q = query.lower()
        hits = [r for r in pool if q in json.dumps(_public(r)).lower()]
        if not hits and q.strip():
            # Natural-language fallback: every word must appear, ignoring '-', '_' and spacing,
            # so "rad dino" finds rad-dino and "prostate pathology" finds PANDA.
            norm = lambda t: "".join(ch for ch in t.lower() if ch.isalnum())
            terms = [norm(w) for w in q.split() if norm(w)]
            hits = [r for r in pool if all(t in norm(json.dumps(_public(r))) for t in terms)] if terms else []
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
    box = ToolBox([
        Tool("get_training_requirements", "Explain source data, labels, splits, runnable code and missing implementation for a specific training task. Preparation only, never starts downloads/training or claims a model is installed.",
             {"type": "object", "properties": {"task": {"type": "string", "enum": ["coordinator_tools", "tabular_profile", "bone_xray", "mammography", "whole_slide", "volume_specialist"]}}, "required": ["task"]}, get_training_requirements),
        Tool("search_public_datasets", "Search LIVE official TCIA imaging collections or TCGA/GDC project metadata on the internet. Use for finding public research data beyond the local catalog. Send only public research terms, never patient details. Returns current source URLs, counts, access and citation information; does not download or train.",
             {"type": "object", "properties": {
                 "source": {"type": "string", "enum": ["tcia", "tcga", "gdc"]},
                 "query": {"type": "string", "maxLength": 200},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                 "page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["source"]}, search_public_datasets),
        Tool("list_tcga_files", "Inspect LIVE TCGA/GDC files for a project ID. Returns official links, byte sizes, MD5, formats and file-specific access. Optional exact data_type, e.g. Slide Image or Gene Expression Quantification. Metadata only; default access=open. Does not download files or create a trained model.",
             {"type": "object", "properties": {
                 "project_id": {"type": "string", "maxLength": 30},
                 "data_type": {"type": "string", "maxLength": 200},
                 "access": {"type": "string", "enum": ["open", "controlled", "all"]},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                 "page": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["project_id"]}, list_tcga_files),
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
    if not online_discovery:
        for name in ("search_public_datasets", "list_tcga_files", "get_training_requirements"):
            box.tools.pop(name)
    return box
