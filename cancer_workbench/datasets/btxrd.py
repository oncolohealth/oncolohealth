"""BTXRD release -> manifest. Owner: Workstream A.

Release layout (figshare 27865398 v1): images/ (.jpeg/.jpg), Annotations/ (LabelMe
JSON, one per tumor image), dataset.xlsx (one row per image, 0/1 indicator columns).
The release has no patient or lesion identifier, so `patient_id` stays empty and
the audit reports it. Never derive groups from filename order, age, sex or center.

describe_release(raw_dir) -> dict      inventory and metadata checks for the readiness report
build_manifest(raw_dir, endpoint, hash_files) -> list[dict]
    One row per radiograph following datasets/manifest.py, partition "unassigned",
    source metadata as extra columns. Rows whose indicators are missing or
    contradictory keep an empty label and an audit flag instead of a guessed class.
    With hash_files, byte-identical images get a shared duplicate_group, and a
    duplicate set whose labels disagree loses its labels. Pairs reviewed as the
    same radiograph in catalog/reviews/btxrd-same-image.json join one group too.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from ..acquisition.download import hash_file
from ..common.paths import CATALOG_DIR, DATA_DIR
from .xlsx import read_sheet, sheet_names

RAW_DIR = DATA_DIR / "btxrd" / "BTXRD" / "BTXRD"
MANIFEST_PATH = DATA_DIR / "btxrd" / "manifest.csv"
REVIEWED_PAIRS = CATALOG_DIR / "reviews" / "btxrd-same-image.json"
RELEASE = "figshare:27865398/v1"

SITES = ("hand", "ulna", "radius", "humerus", "foot", "tibia", "fibula", "femur", "hip bone",
         "ankle-joint", "knee-joint", "hip-joint", "wrist-joint", "elbow-joint", "shoulder-joint")
BENIGN_SUBTYPES = ("osteochondroma", "multiple osteochondromas", "simple bone cyst", "giant cell tumor",
                   "osteofibroma", "synovial osteochondroma", "other bt")
MALIGNANT_SUBTYPES = ("osteosarcoma", "other mt")
REGIONS = ("upper limb", "lower limb", "pelvis")
VIEWS = ("frontal", "lateral", "oblique")
INDICATORS = ("tumor", "benign", "malignant")
REQUIRED_COLUMNS = ("image_id", "center", "age", "gender", *INDICATORS, *SITES, *BENIGN_SUBTYPES,
                    *MALIGNANT_SUBTYPES, *REGIONS, *VIEWS)
GROUPING_HINTS = ("patient", "subject", "case", "lesion", "person")

# (tumor, benign, malignant) -> class. Anything else is quarantined.
_DERIVED = {("0", "0", "0"): "normal", ("1", "1", "0"): "benign", ("1", "0", "1"): "malignant"}
# Candidate endpoints (PROGRESS.md: endpoint decision). None excludes the row from that cohort.
ENDPOINTS = {
    "three_class": {"normal": "normal", "benign": "benign", "malignant": "malignant"},
    "tumor_vs_normal": {"normal": "normal", "benign": "tumor", "malignant": "tumor"},
    "benign_vs_malignant": {"normal": None, "benign": "benign", "malignant": "malignant"},
}


def _rows(raw_dir: Path) -> tuple[list[str], list[dict[str, str]]]:
    table = read_sheet(raw_dir / "dataset.xlsx")
    if not table:
        raise ValueError("dataset.xlsx has no rows")
    header = [h.strip() for h in table[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"dataset.xlsx lacks expected columns {missing}")
    return header, [dict(zip(header, r)) for r in table[1:] if any(r)]


def _on(row: dict, cols) -> list[str]:
    return [c for c in cols if row.get(c, "").strip() == "1"]


def _annotation(raw_dir: Path, stem: str) -> dict | None:
    p = raw_dir / "Annotations" / f"{stem}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _row_flags(row: dict, label: str | None, ann: dict | None) -> list[str]:
    flags = []
    if label is None:
        flags.append("label_combination:" + "".join(row.get(k, "?") or "?" for k in INDICATORS))
    subtypes = _on(row, BENIGN_SUBTYPES + MALIGNANT_SUBTYPES)
    if label in ("benign", "malignant"):
        expected = BENIGN_SUBTYPES if label == "benign" else MALIGNANT_SUBTYPES
        if len(subtypes) != 1:
            flags.append(f"subtype_count:{len(subtypes)}")
        if any(s not in expected for s in subtypes):
            flags.append("subtype_class_mismatch")
        if ann is None:
            flags.append("annotation_missing")
        elif {s.get("label") for s in ann.get("shapes", [])} != set(subtypes):
            flags.append("annotation_subtype_mismatch")
    elif subtypes or ann is not None:
        flags.append("tumor_detail_on_non_tumor_row")
    for name, cols in (("view", VIEWS), ("region", REGIONS)):
        if len(_on(row, cols)) != 1:
            flags.append(f"{name}_count:{len(_on(row, cols))}")
    return flags


def describe_release(raw_dir: Path = RAW_DIR) -> dict:
    """Inventory files and metadata. Reads names, the spreadsheet and annotation JSON; never decodes images."""
    raw_dir = Path(raw_dir)
    header, rows = _rows(raw_dir)
    images = {p.name for p in (raw_dir / "images").iterdir() if p.is_file()}
    annotations = {p.stem for p in (raw_dir / "Annotations").glob("*.json")}
    ids = [r["image_id"] for r in rows]
    stems = {Path(i).stem for i in ids}
    tumor_stems = {Path(r["image_id"]).stem for r in rows if r["tumor"] == "1"}

    shape_labels, shape_types, versions = collections.Counter(), collections.Counter(), collections.Counter()
    for stem in sorted(annotations):
        ann = _annotation(raw_dir, stem)
        versions[ann.get("version")] += 1
        for s in ann.get("shapes", []):
            shape_labels[s.get("label")] += 1
            shape_types[s.get("shape_type")] += 1

    flagged = {}
    for r in rows:
        stem = Path(r["image_id"]).stem
        f = _row_flags(r, _DERIVED.get(tuple(r[k] for k in INDICATORS)), _annotation(raw_dir, stem) if stem in annotations else None)
        if f:
            flagged[stem] = f

    count = lambda cols: {c: len([r for r in rows if r.get(c) == "1"]) for c in cols}
    return {
        "root": str(raw_dir),
        "release": RELEASE,
        "sheets": sheet_names(raw_dir / "dataset.xlsx"),
        "rows": len(rows),
        "columns": header,
        "grouping_columns": [h for h in header if any(k in h.lower() for k in GROUPING_HINTS)],
        "files": {
            "images": dict(collections.Counter(Path(n).suffix.lower() for n in images)),
            "annotations": len(annotations),
            "other": sorted(p.name for p in raw_dir.iterdir() if p.is_file() and p.name != "dataset.xlsx"),
        },
        "id_checks": {
            "duplicate_image_ids": len(ids) - len(set(ids)),
            "rows_without_image": len(set(ids) - images),
            "images_without_row": len(images - set(ids)),
            "tumor_rows_without_annotation": len(tumor_stems - annotations),
            "annotations_without_tumor_row": len(annotations - tumor_stems),
            "annotations_without_row": len(annotations - stems),
        },
        "label_combinations": dict(collections.Counter("".join(r[k] for k in INDICATORS) for r in rows)),
        "derived_classes": dict(collections.Counter(_DERIVED.get(tuple(r[k] for k in INDICATORS), "quarantined") for r in rows)),
        "subtypes": count(BENIGN_SUBTYPES + MALIGNANT_SUBTYPES),
        "centers": dict(collections.Counter(r["center"] for r in rows)),
        "gender": dict(collections.Counter(r["gender"] for r in rows)),
        "regions": count(REGIONS),
        "views": count(VIEWS),
        "sites": count(SITES),
        "annotation": {"versions": dict(versions), "shape_types": dict(shape_types), "labels": dict(shape_labels)},
        "flagged_rows": flagged,
        "note": "Metadata checks only. No pixels were inspected; label truth and patient independence are not established.",
    }


def build_manifest(raw_dir: Path = RAW_DIR, endpoint: str = "three_class", hash_files: bool = True,
                   reviewed_pairs: Path | None = REVIEWED_PAIRS) -> list[dict]:
    """Manifest rows for `endpoint` (see ENDPOINTS). `file` is relative to `raw_dir`."""
    if endpoint not in ENDPOINTS:
        raise ValueError(f"endpoint must be one of {sorted(ENDPOINTS)}")
    raw_dir = Path(raw_dir)
    _, rows = _rows(raw_dir)
    out = []
    for r in rows:
        stem = Path(r["image_id"]).stem
        derived = _DERIVED.get(tuple(r[k] for k in INDICATORS))
        if derived is not None and ENDPOINTS[endpoint][derived] is None:
            continue
        ann = _annotation(raw_dir, stem)
        rel = f"images/{r['image_id']}"
        out.append({
            "sample_id": stem,
            "patient_id": "",
            "duplicate_group": "",
            "partition": "unassigned",
            "label": ENDPOINTS[endpoint][derived] if derived else "",
            "file": rel,
            "sha256": hash_file(raw_dir / rel)["sha256"] if hash_files and (raw_dir / rel).exists() else "",
            "image_id": r["image_id"],
            "release": RELEASE,
            "endpoint": endpoint,
            "label_raw": ";".join(f"{k}={r[k]}" for k in INDICATORS),
            "label_derived": derived or "",
            "label_evidence": "unknown",
            "subtype": ";".join(_on(r, BENIGN_SUBTYPES + MALIGNANT_SUBTYPES)),
            "lesion_group_id": "",
            "grouping_evidence": "none: release has no patient or lesion identifier",
            "center": r["center"],
            "age": r["age"],
            "gender": r["gender"],
            "site": ";".join(_on(r, SITES)),
            "region": ";".join(_on(r, REGIONS)),
            "view": ";".join(_on(r, VIEWS)),
            "annotation_shapes": len(ann.get("shapes", [])) if ann else 0,
            "audit_flags": ";".join(_row_flags(r, derived, ann)),
        })
    out = _mark_exact_duplicates(out)
    if reviewed_pairs is not None and Path(reviewed_pairs).exists():
        out = _merge_reviewed_pairs(out, json.loads(Path(reviewed_pairs).read_text()).get("same_image", []))
    return out


def _merge_reviewed_pairs(rows: list[dict], pairs: list[dict]) -> list[dict]:
    """Join reviewed same-radiograph pairs (and any exact-duplicate group they touch) into one duplicate_group.

    Only pairs a person reviewed as the same image belong here; similar views of one patient do not.
    """
    by_id = {r["sample_id"]: r for r in rows}
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for pair in pairs:
        a, b = pair["a"], pair["b"]
        if a in by_id and b in by_id:  # an endpoint may drop one side (e.g. normals for benign_vs_malignant)
            parent[find(a)] = find(b)
    members: dict[str, list[dict]] = collections.defaultdict(list)
    for sid in parent:
        members[find(sid)].append(by_id[sid])
    for group in members.values():
        exact = {r["duplicate_group"] for r in group if r["duplicate_group"]}
        group += [r for r in rows if r["duplicate_group"] in exact and r not in group]  # exact copies of any member
        ids = {r["sample_id"] for r in group}
        name = "reviewed:" + "+".join(sorted(ids))
        conflict = len({r["label_derived"] for r in group}) > 1
        for r in group:
            r["duplicate_group"] = name
            flags = [f for f in r["audit_flags"].split(";") if f] + ["reviewed_same_image"]
            if conflict:
                r["label"] = ""
                flags.append("duplicate_label_conflict")
            r["audit_flags"] = ";".join(dict.fromkeys(flags))
    return rows


def _mark_exact_duplicates(rows: list[dict]) -> list[dict]:
    """Byte-identical images share a duplicate_group so splits keep them together; conflicting labels are cleared.

    This uses file identity only. It is not patient grouping and finds no near-duplicates.
    """
    by_hash: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        if r["sha256"]:
            by_hash[r["sha256"]].append(r)
    for digest, group in by_hash.items():
        if len(group) < 2:
            continue
        conflict = len({r["label_derived"] for r in group}) > 1
        for r in group:
            r["duplicate_group"] = f"sha256:{digest[:16]}"
            flags = [f for f in r["audit_flags"].split(";") if f] + ["exact_duplicate"]
            if conflict:
                r["label"] = ""
                flags.append("duplicate_label_conflict")
            r["audit_flags"] = ";".join(flags)
    return rows
