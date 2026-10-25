"""JSON API behind the local app. Plain functions so they can be tested without HTTP."""
from __future__ import annotations

import base64
import binascii
import collections
import concurrent.futures
import csv
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path

from ..acquisition import budget
from ..acquisition.download import hash_file
from ..acquisition.fetch import plan, target_dir
from ..acquisition.sources import AccessError
from ..acquisition.subsets import summarize_units
from ..adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from ..adapters.installed import adapter_status, installed_adapters
from ..common.paths import CONFIG_DIR, DATA_DIR, MODELS_DIR, PROJECT_ROOT
from ..coordinator import ProviderError, default_toolbox, load_profiles, make_provider, run_turn
from ..coordinator.config import config_path
from ..coordinator.loop import SYSTEM_PROMPT
from ..datasets import audit_dataset, grouped_split, read_manifest, write_manifest
from ..datasets import readiness
from ..datasets.btxrd import MANIFEST_PATH as BTXRD_MANIFEST, RAW_DIR as BTXRD_RAW
from ..experiments import explore, workspace
from ..experiments.plan import plan_experiment
from ..experiments.records import REUSE_PATHS
from ..registry import load_catalog
from ..routing import route_models
from . import progress_md
from .jobs import JobManager
from .scoring import ScoringJobs

JOBS = JobManager()
SCORES = ScoringJobs()
_HIDDEN = {"_kind"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------- catalog, router, storage ----------

def catalog() -> dict:
    cat = load_catalog()
    status = adapter_status(cat.models)
    out = []
    for r in cat.all():
        rec = {k: v for k, v in r.items() if k not in _HIDDEN}
        rec["record_type"] = r["_kind"]
        prov = target_dir(r) / "PROVENANCE.json"
        rec["local"] = prov.exists()
        if r["_kind"] == "model" and r.get("adapter") in status:
            rec["adapter_status"] = status[r["adapter"]]
        if rec["local"] and r.get("acquisition", {}).get("subset"):
            rec["local_files"] = len(json.loads(prov.read_text()).get("files", []))
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
    models = load_catalog().models
    return route_models(req, models, installed=set(installed_adapters(models)))


# ---------- specialists ----------

SPECIALIST_LOG = PROJECT_ROOT / "runs" / "specialist-calls"


def specialist_run(body: dict) -> dict:
    """Run one specialist through the coordinator's own run_specialist tool, so the UI and the assistant share one path.

    The envelope, including rejections and failures, is also written to runs/specialist-calls/ for review.
    """
    allowed = {"model_id", "task", "modality", "anatomy", "inputs", "input_refs"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise ApiError(f"Specialist requests take only {sorted(allowed)}.")
    cat = load_catalog()
    box = default_toolbox(cat, installed_adapters(cat.models))
    args = json.dumps(body)
    answer = box.call("run_specialist", args)
    record = {"tool": "run_specialist", "arguments": body, **answer}
    env = answer.get("result")
    if isinstance(env, dict) and env.get("run_id"):
        SPECIALIST_LOG.mkdir(parents=True, exist_ok=True)
        (SPECIALIST_LOG / f"{env['created_at'].replace(':', '')}-{env['run_id']}.json").write_text(
            json.dumps(record, indent=2, default=str) + "\n")
    return record


def storage() -> dict:
    used = budget.usage_bytes()
    return {"used": used, "budget": budget.budget_bytes(), "data_dir": str(DATA_DIR), "models_dir": str(MODELS_DIR),
            "hf_token": bool(os.environ.get("HF_TOKEN"))}


# ---------- downloads ----------

def _subsets(body: dict, ids: list[str]) -> dict[str, dict]:
    subsets = body.get("subsets") or {}
    if not isinstance(subsets, dict) or not set(subsets) <= set(ids):
        raise ApiError("subsets must map selected catalog ids to a selection.")
    return subsets


def _selection_brief(sel: dict | None) -> dict | None:
    """The provenance summary minus the full unit list, which can run to thousands of ids."""
    return None if sel is None else {k: v for k, v in sel.items() if k != "units"} | {"unit_count": len(sel["units"])}


def fetch_plan(body: dict) -> dict:
    cat = load_catalog()
    ids = list(body.get("ids", []))
    records = [cat.get(i) for i in ids]
    if any(r is None for r in records):
        raise ApiError("Unknown catalog id in request.")
    rows = plan(records, _subsets(body, ids))
    total = sum(r["bytes"] for r in rows if not r["error"])
    fits, used, cap = budget.check(total)
    return {
        "rows": [{"id": r["id"], "tier": r["tier"], "bytes": r["bytes"], "error": r["error"], "selection": _selection_brief(r["selection"]),
                  "files": [{"path": p.relpath, "size": p.size, "integrity": p.integrity} for p in r["plans"]]} for r in rows],
        "total": total, "fits": fits, "used": used, "budget": cap,
    }


def fetch_start(body: dict) -> dict:
    ids = list(body.get("ids", []))
    try:
        return JOBS.start(load_catalog(), ids, allow_big=bool(body.get("allow_big")), subsets=_subsets(body, ids))
    except (RuntimeError, KeyError, PermissionError) as e:
        raise ApiError(str(e).strip("'\""), 409)


def fetch_units(body: dict) -> dict:
    rec = load_catalog().get(body.get("id", ""))
    if rec is None:
        raise ApiError("Unknown catalog id.", 404)
    query = body.get("query")
    try:
        return {"id": rec["id"], **summarize_units(rec["acquisition"], target_dir(rec), query if query else None)}
    except (AccessError, ValueError) as e:
        raise ApiError(str(e), 409)
    except OSError as e:
        raise ApiError(f"Could not reach the source: {e}", 502)


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


def dataset_evidence() -> dict:
    try:
        return readiness.summary()
    except (OSError, ValueError, KeyError, TypeError):
        return {"dataset_id": "btxrd", "available": False, "source_kind": "published_review_snapshot",
                "note": "Published BTXRD evidence snapshot is unavailable or inconsistent. Local manifest audits remain available.",
                "ready_for_training": False, "execution_authorized": False}


def dataset_evidence_template() -> dict:
    try:
        return readiness.blank_template()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ApiError("The published blank template is unavailable or inconsistent. No evidence file was exported.", 409) from error


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


# ---------- experiment drafts and recorded runs ----------

EXPERIMENTS_DIR = PROJECT_ROOT / "runs"
MAX_MANIFEST_BYTES = 16_000_000


def experiment_options() -> dict:
    return {"paths": list(REUSE_PATHS), "models": [{"id": m["id"], "name": m.get("name", m["id"])}
                                                    for m in load_catalog().models],
            "manifests": manifests()["manifests"], "storage": storage()}


def experiment_preview(body: dict) -> dict:
    allowed = {"model_id", "reuse_path", "manifest", "planned_bytes", "question", "synthetic"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise ApiError("Unknown experiment input. Supply model, reuse path, manifest and storage reservation.")
    if body.get("reuse_path") not in REUSE_PATHS:
        raise ApiError("Choose a supported model reuse path.")
    synthetic = body.get("synthetic", False)
    if not isinstance(synthetic, bool):
        raise ApiError("Synthetic mode must be true or false.")
    question = body.get("question", "")
    if not isinstance(question, str) or len(question) > 1000:
        raise ApiError("Research question must be text of at most 1,000 characters.")
    planned = body.get("planned_bytes")
    if isinstance(planned, bool) or not isinstance(planned, int) or not 0 <= planned <= 10**15:
        raise ApiError("Storage reservation must be a nonnegative integer number of bytes (at most 10^15).")
    identity = None
    if synthetic:
        model = dict(SYNTHETIC_MODEL_RECORD, acquisition={"revision": "0" * 40}, reuse_permissions={
            p: {"status": "allowed", "evidence": "SYNTHETIC software fixture only"}
            for p in ("transfer_learning", "distillation")})
        rows = [{"sample_id": f"fixture-{i}", "patient_id": f"fixture-patient-{i}", "duplicate_group": "",
                 "partition": ("train", "val", "test")[i // 4], "label": ("negative", "positive")[i % 2]}
                for i in range(12)]
        spec = {"id": "synthetic-plan-fixture", "classes": ["negative", "positive"], "unresolved": []}
        identity = {"fixture": "synthetic-plan-v1", "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
    else:
        if not isinstance(body.get("model_id"), str):
            raise ApiError("Select a catalog model.")
        model = load_catalog().get(body.get("model_id"))
        if model is None or model.get("_kind") != "model":
            raise ApiError("Select a catalog model.")
        rel = body.get("manifest")
        if not isinstance(rel, str) or not rel:
            raise ApiError("Select a dataset manifest from this machine.")
        path = _safe_data_path(rel)
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise ApiError("Manifest exceeds the 16 MB draft-preview limit.")
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
            required = {"sample_id", "patient_id", "partition", "label"}
            if not required <= set(reader.fieldnames or []):
                raise ApiError("Manifest needs sample_id, patient_id, partition and label columns.")
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ApiError("Manifest has duplicate CSV column names.")
            rows = list(reader)
            if any(None in r or any(r.get(k) is None for k in required) for r in rows):
                raise ApiError("Manifest has a malformed CSV row.")
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ApiError(f"Cannot read the selected manifest: {exc}") from exc
        dataset_id = path.relative_to(DATA_DIR.resolve()).parts[0]
        dataset = load_catalog().get(dataset_id)
        if not dataset or dataset.get("_kind") != "dataset":
            raise ApiError("Manifest must belong to a catalog dataset folder.")
        spec = _spec_for(dataset_id, rows)
        identity = {"path": str(path.relative_to(DATA_DIR.resolve())), "sha256": hashlib.sha256(raw).hexdigest()}
    audit = audit_dataset(spec, rows)
    if any(not r["sample_id"].strip() for r in rows):
        audit["findings"].append({"severity": "error", "code": "missing_sample_id", "detail": "Some manifest rows lack a sample identity."})
        audit["ready_for_training"] = False
    if any((r.get(k) or "") != (r.get(k) or "").strip() for r in rows for k in ("sample_id", "patient_id", "duplicate_group")):
        audit["findings"].append({"severity": "error", "code": "identity_whitespace", "detail": "Identity fields contain surrounding whitespace. Review the source identities before grouping."})
        audit["ready_for_training"] = False
    if any(r.get("partition") in {"train", "val", "test"} and not r["label"].strip() for r in rows):
        audit["findings"].append({"severity": "error", "code": "missing_label", "detail": "Assigned rows lack reference labels. Review eligibility or mark exclusions explicitly."})
        audit["ready_for_training"] = False
    measured = {"used_bytes": budget.usage_bytes(), "planned_bytes": planned, "limit_bytes": budget.budget_bytes()}
    installed = {SYNTHETIC_MODEL_RECORD["adapter"]} if synthetic else set(installed_adapters(load_catalog().models))
    plan = plan_experiment(body["reuse_path"], model, audit, measured, installed)
    preview = {"question": question.strip(), "synthetic": synthetic, "manifest": identity, "audit": audit, "plan": plan,
               "note": "Draft only. The question is unreviewed. No weights, data, training or specialist execution is dispatched."}
    preview["execution_review"] = workspace.execution_review(preview)
    return preview


def experiment_save(body: dict) -> dict:
    # Recompute from catalog/manifest/storage now. No client-supplied audit,
    # permission overlay, saved preview or execution state is accepted.
    preview = experiment_preview(body)
    from ..experiments.btxrd_baseline import _git_revision
    try:
        return workspace.save_draft(EXPERIMENTS_DIR, preview, source_revision=_git_revision())
    except (OSError, ValueError) as exc:
        raise ApiError(f"Could not save draft: {exc}") from exc


def experiment_history() -> dict:
    return workspace.history(EXPERIMENTS_DIR)


def experiment_record(body: dict) -> dict:
    if not isinstance(body, dict) or set(body) != {"key"}:
        raise ApiError("Select a saved record.")
    try:
        return workspace.detail(EXPERIMENTS_DIR, body["key"])
    except FileNotFoundError as exc:
        raise ApiError("Saved record is no longer available. Refresh history.", 404) from exc
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ApiError(str(exc)) from exc


# ---------- images: browse, annotations, runs, uploads, live scoring ----------

UPLOADS_DIR = DATA_DIR / "uploads"
MAX_UPLOAD = 20_000_000
IMAGE_TYPES = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}
# Image sets the Images screen can browse: image root, manifest (its `file` column is relative to root), LabelMe folder.
IMAGE_SETS = {"btxrd": {"root": BTXRD_RAW, "manifest": BTXRD_MANIFEST, "annotations": BTXRD_RAW / "Annotations"}}
IMAGE_FIELDS = ("sample_id", "label", "file", "center", "site", "subtype", "view", "region", "age", "gender",
                "duplicate_group", "audit_flags", "annotation_shapes", "label_raw")
ML_MODULES = ("numpy", "sklearn", "torch", "PIL", "transformers", "timm", "safetensors")


def _ml_missing() -> list[str]:
    return [m for m in ML_MODULES if importlib.util.find_spec(m) is None]


def media_file(rel: str) -> tuple[Path, str]:
    """Resolve `<set>/<path>` from a /media/ URL to an image file inside that set's root (or the uploads folder)."""
    name, _, sub = rel.partition("/")
    root = UPLOADS_DIR if name == "uploads" else IMAGE_SETS.get(name, {}).get("root")
    p = (root / sub).resolve() if root and sub else None
    if p is None or not p.is_relative_to(root.resolve()) or p.suffix.lower() not in IMAGE_TYPES or not p.is_file():
        raise ApiError("No such image.", 404)
    return p, IMAGE_TYPES[p.suffix.lower()]


def image_sets() -> dict:
    sets = [{"id": k, "available": v["manifest"].exists()} for k, v in IMAGE_SETS.items()]
    return {"sets": sets, "ml_missing": _ml_missing(), "max_score": explore.MAX_SCORE, "max_upload": MAX_UPLOAD}


def image_set(name: str) -> dict:
    spec = IMAGE_SETS.get(name)
    if spec is None:
        raise ApiError("Unknown image set.", 404)
    if not spec["manifest"].exists():
        raise ApiError(f"No manifest for {name} yet. Run `python -m cancer_workbench {name} manifest`.", 404)
    rows = read_manifest(spec["manifest"])
    return {"id": name, "manifest": str(spec["manifest"].relative_to(DATA_DIR)), "rows": [{k: r.get(k, "") for k in IMAGE_FIELDS} for r in rows]}


def annotation(rel: str) -> dict:
    """LabelMe shapes for one image (`<set>/<sample_id>`): label, shape type and points in image pixels."""
    name, _, sid = rel.partition("/")
    spec = IMAGE_SETS.get(name)
    if spec is None or not sid.replace("_", "").replace("-", "").isalnum():
        raise ApiError("Unknown image.", 404)
    p = spec["annotations"] / f"{sid}.json"
    if not p.is_file():
        return {"width": None, "height": None, "shapes": []}
    a = json.loads(p.read_text())
    shapes = [{"label": str(s.get("label", "")), "type": str(s.get("shape_type", "")), "points": [[float(x), float(y)] for x, y in s.get("points", [])]}
              for s in a.get("shapes", [])]
    return {"width": a.get("imageWidth"), "height": a.get("imageHeight"), "shapes": shapes}


def runs() -> dict:
    return {"runs": explore.list_runs()}


def run_review(body: dict) -> dict:
    try:
        return explore.review(body.get("run", ""), body.get("result", ""))
    except (ValueError, FileNotFoundError, KeyError) as e:
        raise ApiError(str(e).strip("'\""), 404)


def _upload_stem(stem) -> str:
    if not isinstance(stem, str) or len(stem) != 16 or any(c not in "0123456789abcdef" for c in stem):
        raise ApiError("Unknown upload.", 404)
    return stem


def uploads() -> dict:
    metas = sorted(UPLOADS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if UPLOADS_DIR.exists() else []
    return {"uploads": [json.loads(p.read_text()) for p in metas]}


def upload(body: dict) -> dict:
    """Store one JPEG/PNG under data/uploads/, named by content hash, with a sidecar. Pixels are only decoded when scored."""
    try:
        raw = base64.b64decode(body.get("data") or "", validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("Upload data must be base64.")
    if not raw:
        raise ApiError("The file is empty.")
    if len(raw) > MAX_UPLOAD:
        raise ApiError(f"Images over {MAX_UPLOAD // 1_000_000} MB can't be uploaded.", 413)
    ext = ".jpeg" if raw[:3] == b"\xff\xd8\xff" else ".png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else None
    if ext is None:
        raise ApiError("Only JPEG and PNG images can be uploaded.")
    if not budget.check(len(raw))[0]:
        raise ApiError("This upload would go over the storage budget.", 409)
    sha = hashlib.sha256(raw).hexdigest()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOADS_DIR / f"{sha[:16]}{ext}").write_bytes(raw)
    meta = {"id": sha[:16], "file": f"{sha[:16]}{ext}", "original_name": str(body.get("name") or "upload")[:200], "bytes": len(raw),
            "sha256": sha, "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (UPLOADS_DIR / f"{sha[:16]}.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def delete_upload(body: dict) -> dict:
    stem = _upload_stem(body.get("id"))
    for p in UPLOADS_DIR.glob(f"{stem}.*"):
        p.unlink()
    return uploads()


def _score_items(body: dict) -> list[dict]:
    """Validate and resolve score inputs before starting any background work."""
    if missing := _ml_missing():
        raise ApiError(f"Live scoring needs the ml extra ({', '.join(missing)} not installed). "
                       "Start the app with `.venv/bin/python -m cancer_workbench app`.", 409)
    requested = body.get("items")
    if not isinstance(requested, list) or not 1 <= len(requested) <= explore.MAX_SCORE:
        raise ApiError(f"Select between 1 and {explore.MAX_SCORE} images.", 409)
    if any(not isinstance(it, dict) for it in requested):
        raise ApiError("Each selected image must specify its set and id.")
    files, items = {}, []
    for it in requested:
        name = it.get("set")
        if name == "uploads":
            stem = _upload_stem(it.get("id"))
            found = [p for p in UPLOADS_DIR.glob(f"{stem}.*") if p.suffix in IMAGE_TYPES]
            if not found:
                raise ApiError(f"Upload {stem} is gone.", 404)
            items.append({"key": f"uploads:{stem}", "path": str(found[0])})
        elif name in IMAGE_SETS:
            if name not in files:
                files[name] = {r["sample_id"]: r["file"] for r in read_manifest(IMAGE_SETS[name]["manifest"])}
            sid = it.get("id")
            if sid not in files[name]:
                raise ApiError(f"{sid!r} is not in the {name} manifest.", 404)
            # Baseline runs are BTXRD-only, so only BTXRD ids are matched against the run's split.
            items.append({"key": f"{name}:{sid}", "path": str(IMAGE_SETS[name]["root"] / files[name][sid]),
                          "sample_id": sid if name == "btxrd" else None})
        else:
            raise ApiError("Unknown image set.", 404)
    return items


def live_score(body: dict) -> dict:
    """Synchronous scoring kept for API clients."""
    items = _score_items(body)
    try:
        return explore.score(body.get("run", ""), body.get("result", ""), items)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise ApiError(str(e), 409)


def start_score(body: dict) -> dict:
    items = _score_items(body)
    run, result = body.get("run", ""), body.get("result", "")
    try:
        # Validate run identity before returning a job to the browser.
        explore.review(run, result)
        return SCORES.start(run, result, len(items), lambda progress: explore.score(run, result, items, progress=progress),
                            keys=[it["key"] for it in items])
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise ApiError(str(e), 409)


def score_job(job_id: str) -> dict:
    try:
        return SCORES.get(job_id)
    except KeyError as e:
        raise ApiError(e.args[0], 404)


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
    allowed = {"type", "base_url", "base_url_env", "model", "api_key_env", "timeout_s", "default_params", "extra_body",
               "supports_tools", "require_api_key", "extra_headers_env", "_notes"}
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
        adapters = installed_adapters(cat.models)
        if synthetic:
            adapters["synthetic-threshold"] = SyntheticThresholdAdapter()
        box = default_toolbox(cat, adapters, extra_models=[SYNTHETIC_MODEL_RECORD] if synthetic else None)
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
    "/api/datasets/btxrd/evidence": dataset_evidence,
    "/api/datasets/btxrd/evidence-template": dataset_evidence_template,
    "/api/coordinator/profiles": profiles, "/api/progress": progress,
    "/api/images": image_sets, "/api/runs": runs, "/api/uploads": uploads,
    "/api/score/current": lambda: {"job": SCORES.current()},
    "/api/experiments/options": experiment_options, "/api/experiments/history": experiment_history,
}
GET_PARAM_ROUTES = {"/api/provenance/": provenance, "/api/inventory/": inventory, "/api/images/": image_set,
                    "/api/annotation/": annotation, "/api/score/jobs/": score_job}
POST_ROUTES = {
    "/api/route": route, "/api/specialist/run": specialist_run, "/api/fetch/plan": fetch_plan, "/api/fetch/start": fetch_start, "/api/fetch/cancel": fetch_cancel,
    "/api/fetch/units": fetch_units,
    "/api/audit": audit, "/api/split": split,
    "/api/coordinator/profiles/save": save_profile, "/api/coordinator/profiles/delete": delete_profile,
    "/api/coordinator/ping": ping, "/api/coordinator/ask": ask,
    "/api/progress/mark": progress_mark, "/api/progress/owner": progress_owner,
    "/api/runs/review": run_review, "/api/uploads/add": upload, "/api/uploads/delete": delete_upload, "/api/score": live_score,
    "/api/score/start": start_score,
    "/api/experiments/preview": experiment_preview, "/api/experiments/save": experiment_save,
    "/api/experiments/record": experiment_record,
}
