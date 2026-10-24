"""JSON API behind the local app. Plain functions so they can be tested without HTTP."""
from __future__ import annotations

import collections
import concurrent.futures
import json
import os
from pathlib import Path

from ..acquisition import budget
from ..acquisition.download import hash_file
from ..acquisition.fetch import plan, target_dir
from ..adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from ..common.paths import CONFIG_DIR, DATA_DIR, MODELS_DIR
from ..coordinator import ProviderError, default_toolbox, load_profiles, make_provider, run_turn
from ..coordinator.config import config_path
from ..coordinator.loop import SYSTEM_PROMPT
from ..datasets import audit_dataset, grouped_split, read_manifest, write_manifest
from ..registry import load_catalog
from ..routing import route_models
from . import progress_md
from .jobs import JobManager

JOBS = JobManager()
_HIDDEN = {"_kind"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------- catalog, router, storage ----------

def catalog() -> dict:
    cat = load_catalog()
    out = []
    for r in cat.all():
        rec = {k: v for k, v in r.items() if k not in _HIDDEN}
        rec["record_type"] = r["_kind"]
        rec["local"] = (target_dir(r) / "PROVENANCE.json").exists()
        out.append(rec)
    return {"records": out, "validation": cat.validate()}


def route_options() -> dict:
    models = load_catalog().models
    opts = collections.defaultdict(set)
    for m in models:
        opts["task"].update(m.get("tasks", []))
        for key in ("modality", "anatomy"):
            v = m.get(key, [])
            opts[key].update(v if isinstance(v, list) else [v])
    opts["anatomy"].update({"bone", "brain", "chest", "breast", "skin", "colon", "prostate", "lymph_node"})
    opts["anatomy"].discard("any")
    return {k: sorted(v) for k, v in opts.items()}


def route(body: dict) -> dict:
    inp = {k: int(body[k]) for k in ("channels", "spatial_dims") if body.get(k) not in (None, "")}
    req = {"task": body.get("task"), "modality": body.get("modality"), "anatomy": body.get("anatomy"), "input": inp}
    return route_models(req, load_catalog().models)


def storage() -> dict:
    used = budget.usage_bytes()
    return {"used": used, "budget": budget.budget_bytes(), "data_dir": str(DATA_DIR), "models_dir": str(MODELS_DIR),
            "hf_token": bool(os.environ.get("HF_TOKEN"))}


# ---------- downloads ----------

def fetch_plan(body: dict) -> dict:
    cat = load_catalog()
    records = [cat.get(i) for i in body.get("ids", [])]
    if any(r is None for r in records):
        raise ApiError("Unknown catalog id in request.")
    rows = plan(records)
    total = sum(r["bytes"] for r in rows if not r["error"])
    fits, used, cap = budget.check(total)
    return {
        "rows": [{"id": r["id"], "tier": r["tier"], "bytes": r["bytes"], "error": r["error"],
                  "files": [{"path": p.relpath, "size": p.size, "integrity": p.integrity} for p in r["plans"]]} for r in rows],
        "total": total, "fits": fits, "used": used, "budget": cap,
    }


def fetch_start(body: dict) -> dict:
    try:
        return JOBS.start(load_catalog(), list(body.get("ids", [])), allow_big=bool(body.get("allow_big")))
    except (RuntimeError, KeyError, PermissionError) as e:
        raise ApiError(str(e).strip("'\""), 409)


def fetch_cancel(body: dict) -> dict:
    return {"cancelled": JOBS.cancel(body.get("id", ""))}


def provenance(record_id: str) -> dict:
    rec = load_catalog().get(record_id)
    if rec is None:
        raise ApiError("Unknown catalog id.", 404)
    p = target_dir(rec) / "PROVENANCE.json"
    if not p.exists():
        raise ApiError(f"{record_id} has not been downloaded yet.", 404)
    return json.loads(p.read_text())


def inventory(record_id: str) -> dict:
    """File counts by extension and top-level layout. Lists names only; never opens downloaded files."""
    rec = load_catalog().get(record_id)
    if rec is None:
        raise ApiError("Unknown catalog id.", 404)
    root = target_dir(rec)
    if not root.exists():
        raise ApiError(f"{record_id} has not been downloaded yet.", 404)
    exts, total, dirs = collections.Counter(), 0, collections.Counter()
    for f in root.rglob("*"):
        if f.is_file() and not f.is_symlink():
            exts[f.suffix.lower() or "(none)"] += 1
            total += f.stat().st_size
            rel = f.relative_to(root).parts
            dirs["/".join(rel[:-1][:3]) or "."] += 1
    return {"id": record_id, "root": str(root), "bytes": total, "extensions": dict(exts.most_common()),
            "folders": dict(sorted(dirs.items())[:40])}


# ---------- datasets: manifests, audit, splits ----------

def _safe_data_path(rel: str) -> Path:
    p = (DATA_DIR / rel).resolve()
    if not p.is_relative_to(DATA_DIR.resolve()) or p.suffix != ".csv":
        raise ApiError("Manifest path must be a .csv inside the data folder.")
    return p


def manifests() -> dict:
    found = []
    if DATA_DIR.exists():
        for ds in sorted(DATA_DIR.iterdir()):
            if not ds.is_dir():
                continue
            for f in sorted(list(ds.glob("*.csv")) + list(ds.glob("splits/*.csv"))):
                found.append({"dataset_id": ds.name, "path": str(f.relative_to(DATA_DIR)), "bytes": f.stat().st_size})
    return {"manifests": found}


def _synthetic_rows() -> list[dict]:
    rows = []
    for i in range(240):
        p = i // 3
        rows.append({"sample_id": f"syn{i:04d}", "patient_id": "" if p % 17 == 0 else f"P{p:03d}", "duplicate_group": "",
                     "partition": ("train" if p % 5 else "test") if p != 7 else ("train" if i % 2 else "test"),
                     "label": "tumor" if p % 3 == 0 else "normal", "file": "", "sha256": ""})
    return rows


def _spec_for(dataset_id: str, rows: list[dict]) -> dict:
    rec = load_catalog().get(dataset_id) or {}
    return {"id": dataset_id, "unresolved": rec.get("unresolved", []), "classes": sorted({r["label"] for r in rows})}


def audit(body: dict) -> dict:
    if body.get("synthetic"):
        rows = _synthetic_rows()
        spec = {"id": "synthetic-demo", "unresolved": [], "classes": ["normal", "tumor"]}
    else:
        path = _safe_data_path(body.get("path", ""))
        rows = read_manifest(path)
        spec = _spec_for(body.get("dataset_id", path.parent.name), rows)
    rep = audit_dataset(spec, rows, files_root=None)
    rep["synthetic"] = bool(body.get("synthetic"))
    return rep


def split(body: dict) -> dict:
    fr = {k: float(v) for k, v in body.get("fractions", {}).items() if float(v) > 0}
    if abs(sum(fr.values()) - 1) > 1e-6:
        raise ApiError("Split fractions must add up to 1.")
    seed = str(body.get("seed", "0"))
    if body.get("synthetic"):
        rows, spec = _synthetic_rows(), {"id": "synthetic-demo", "unresolved": [], "classes": ["normal", "tumor"]}
        src = None
    else:
        src = _safe_data_path(body.get("path", ""))
        rows = read_manifest(src)
        spec = _spec_for(body.get("dataset_id", src.parent.name), rows)
    out = grouped_split(rows, fr, seed=seed)
    rep = audit_dataset(spec, out)
    saved = None
    if body.get("save"):
        if src is None:
            raise ApiError("Synthetic demo splits can't be saved.")
        name = body.get("name") or f"split-seed{seed}"
        dest = src.parent / "splits" / f"{''.join(c for c in name if c.isalnum() or c in '-_')}.csv"
        write_manifest(dest, out)
        sidecar = {"source_manifest": str(src.relative_to(DATA_DIR)), "source_sha256": hash_file(src)["sha256"],
                   "fractions": fr, "seed": seed, "grouping": "patient_id > duplicate_group > sample_id", "audit": rep}
        dest.with_suffix(".json").write_text(json.dumps(sidecar, indent=2) + "\n")
        saved = str(dest.relative_to(DATA_DIR))
    rep["saved"] = saved
    rep["synthetic"] = bool(body.get("synthetic"))
    return rep


# ---------- coordinator ----------

def profiles() -> dict:
    profs, default = load_profiles()
    path = config_path()
    return {"profiles": profs, "default": default, "config_file": str(path.relative_to(CONFIG_DIR.parent)),
            "is_local": path.name == "coordinator.json", "system_prompt": SYSTEM_PROMPT}


def _local_config() -> tuple[Path, dict]:
    local = CONFIG_DIR / "coordinator.json"
    src = local if local.exists() else CONFIG_DIR / "coordinator.example.json"
    return local, json.loads(src.read_text())


def save_profile(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name or name.startswith("_") or not all(c.isalnum() or c in "-_." for c in name):
        raise ApiError("Profile names use letters, numbers, dot, dash or underscore.")
    p = body.get("profile") or {}
    if not p.get("base_url") or not p.get("model"):
        raise ApiError("A profile needs a server URL and a model name.")
    if "api_key" in p:
        raise ApiError("Don't store keys in the profile. Put the key in an environment variable and enter its name instead.")
    allowed = {"type", "base_url", "base_url_env", "model", "api_key_env", "timeout_s", "default_params", "extra_body", "supports_tools", "_notes"}
    clean = {k: v for k, v in p.items() if k in allowed and v not in ("", None)}
    clean.setdefault("type", "openai_compatible")
    local, cfg = _local_config()
    cfg["profiles"][name] = clean
    if body.get("make_default"):
        cfg["default_profile"] = name
    local.write_text(json.dumps(cfg, indent=2) + "\n")
    return profiles()


def delete_profile(body: dict) -> dict:
    local, cfg = _local_config()
    name = body.get("name")
    if name not in cfg["profiles"]:
        raise ApiError(f"No profile named {name!r}.", 404)
    if cfg.get("default_profile") == name:
        raise ApiError("That's the default profile. Make another profile the default first.")
    del cfg["profiles"][name]
    local.write_text(json.dumps(cfg, indent=2) + "\n")
    return profiles()


def ping(body: dict) -> dict:
    try:
        return {"ok": True, "models": make_provider(body.get("profile")).list_models()}
    except (ProviderError, KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ask(body: dict) -> dict:
    question = (body.get("question") or "").strip()
    names = body.get("profiles") or [None]
    if not question:
        raise ApiError("Type a question first.")
    histories = body.get("histories") or {}
    synthetic = bool(body.get("synthetic_demo"))
    cat = load_catalog()

    def one(name):
        box = default_toolbox(cat, {"synthetic-threshold": SyntheticThresholdAdapter()} if synthetic else {},
                              extra_models=[SYNTHETIC_MODEL_RECORD] if synthetic else None)
        try:
            prov = make_provider(name)
            rec = run_turn(prov, box, question, history=histories.get(prov.profile) or None)
            return {"profile": prov.profile, "model": prov.model, "final": rec.final, "stopped": rec.stopped,
                    "steps": rec.steps, "messages": rec.messages}
        except (ProviderError, KeyError, ValueError) as e:
            return {"profile": name, "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(names))) as ex:
        return {"results": list(ex.map(one, names))}


# ---------- progress ----------

def progress() -> dict:
    return progress_md.parse()


def progress_mark(body: dict) -> dict:
    try:
        progress_md.set_mark(int(body["line"]), body["text"], body["mark"])
    except (KeyError, ValueError) as e:
        raise ApiError(str(e), 409)
    return progress_md.parse()


def progress_owner(body: dict) -> dict:
    try:
        progress_md.set_owner(int(body["line"]), body["ws"], body.get("name", ""))
    except (KeyError, ValueError) as e:
        raise ApiError(str(e), 409)
    return progress_md.parse()


GET_ROUTES = {
    "/api/catalog": catalog, "/api/route/options": route_options, "/api/storage": storage,
    "/api/jobs": lambda: {"jobs": JOBS.list()}, "/api/manifests": manifests,
    "/api/coordinator/profiles": profiles, "/api/progress": progress,
}
GET_PARAM_ROUTES = {"/api/provenance/": provenance, "/api/inventory/": inventory}
POST_ROUTES = {
    "/api/route": route, "/api/fetch/plan": fetch_plan, "/api/fetch/start": fetch_start, "/api/fetch/cancel": fetch_cancel,
    "/api/audit": audit, "/api/split": split,
    "/api/coordinator/profiles/save": save_profile, "/api/coordinator/profiles/delete": delete_profile,
    "/api/coordinator/ping": ping, "/api/coordinator/ask": ask,
    "/api/progress/mark": progress_mark, "/api/progress/owner": progress_owner,
}
