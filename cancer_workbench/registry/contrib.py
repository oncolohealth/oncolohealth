"""Community contributions: turn a submitted model or dataset (a link, often to a zip) into a catalog
record held for maintainer review.

A contribution never enters the catalog as more than `cataloged`, never carries an inference permission
and never fetches anything: the link becomes manual-tier instructions. The site's contribute form
(site/contribute.html) produces the submission JSON this module accepts.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..common.paths import CATALOG_DIR
from .schema import ACCESS, MODEL_KINDS, validate_dataset, validate_model

SCHEMA = "oncolohealth-contribution/1"
PATIENT_IDS = {"yes", "partial", "no", "unknown"}
CONTRIB_DIR = CATALOG_DIR / "contributions"
_MAX = 2000


def _https(url) -> bool:
    return isinstance(url, str) and re.match(r"^https://[^\s/]+\.[^\s]+$", url) is not None


def _list(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip().lower() for v in (value or []) if str(v).strip()]


def slug(name: str) -> str:
    return "contrib-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "untitled")


def check(sub: dict) -> list[str]:
    """Problems with a submission, in plain words. Empty means it can become a record."""
    errs = []
    if sub.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}")
    if sub.get("type") not in {"model", "dataset"}:
        errs.append("type must be 'model' or 'dataset'")
    for field in ("name", "summary", "license_id", "contributor_name"):
        if not str(sub.get(field, "")).strip():
            errs.append(f"{field} is required")
    for field, value in sub.items():
        if isinstance(value, str) and len(value) > _MAX:
            errs.append(f"{field} is longer than {_MAX} characters")
    if not _https(sub.get("link")):
        errs.append("link must be an https URL to the files (a zip, a model page or a dataset page)")
    if sub.get("citation") and not _https(sub["citation"]):
        errs.append("citation must be an https URL (a DOI link works)")
    if sub.get("access") not in ACCESS:
        errs.append(f"access must be one of {sorted(ACCESS)}")
    if not _list(sub.get("modality")):
        errs.append("modality is required (for example: ct, mri, xray, pathology)")
    if not _list(sub.get("anatomy")):
        errs.append("anatomy is required (for example: lung, brain, bone, breast)")
    if sub.get("rights_confirmed") is not True:
        errs.append("confirm that you may share this link under its stated license")
    if sub.get("contains_identifiable_data") is not False:
        errs.append("confirm the files contain no identifiable patient information")
    if sub.get("type") == "model":
        if sub.get("model_kind") not in MODEL_KINDS:
            errs.append(f"model_kind must be one of {sorted(MODEL_KINDS)}")
        if not _list(sub.get("tasks")):
            errs.append("tasks is required for a model (for example: classification, segmentation)")
    if sub.get("type") == "dataset" and sub.get("patient_ids") not in PATIENT_IDS:
        errs.append(f"patient_ids must be one of {sorted(PATIENT_IDS)}")
    return errs


def to_record(sub: dict, now: str | None = None) -> dict:
    """Catalog record for a submission that passed check()."""
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = {
        "id": slug(sub["name"]),
        "name": sub["name"].strip(),
        "summary": sub["summary"].strip(),
        "modality": _list(sub["modality"]),
        "anatomy": _list(sub["anatomy"]),
        "license": {"id": sub["license_id"].strip(), "commercial": sub.get("commercial")},
        "access": sub["access"],
        "evidence_state": "cataloged",
        "citation": sub.get("citation") or sub["link"],
        "acquisition": {"tier": "manual", "fetcher": "none",
                        "instructions": f"Community contribution. Files at {sub['link']}. Review the license and access terms before fetching."},
        "contribution": {"contributor": sub["contributor_name"].strip(), "affiliation": str(sub.get("affiliation", "")).strip(),
                         "link": sub["link"], "submitted_at": now, "review": "pending"},
    }
    if sub["type"] == "model":
        rec.update(kind=sub["model_kind"], tasks=_list(sub["tasks"]),
                   input={"description": str(sub.get("input", "")).strip()},
                   outputs={"type": str(sub.get("outputs", "")).strip() or "unspecified"},
                   inference_permission="unreviewed", adapter=None)
    else:
        counts = {"status": "contributor-reported"}
        for key in ("images", "patients"):
            if str(sub.get(key, "")).strip().isdigit():
                counts[key] = int(sub[key])
        rec.update(counts=counts, labels={"description": str(sub.get("labels", "")).strip(), "patient_ids": sub["patient_ids"]},
                   unresolved=[] if sub["patient_ids"] == "yes" else ["patient grouping not confirmed by the contributor"])
    return rec


def accept(sub: dict, catalog, out_dir: Path = CONTRIB_DIR) -> tuple[dict | None, list[str]]:
    """Check a submission, build its record, validate it like any catalog record and queue it for review."""
    errs = check(sub)
    if errs:
        return None, errs
    rec = to_record(sub)
    errs = (validate_model if sub["type"] == "model" else validate_dataset)(rec)
    if catalog.get(rec["id"]) or (out_dir / f"{rec['id']}.json").exists():
        errs.append(f"{rec['id']}: already in the catalog or the review queue")
    if errs:
        return None, errs
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec, []


def pending(out_dir: Path = CONTRIB_DIR) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_dir.glob("*.json"))] if out_dir.exists() else []
