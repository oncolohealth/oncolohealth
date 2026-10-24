"""Read-only published BTXRD evidence snapshot for the researcher workspace.

A matched publication hash establishes local consistency only. This module does
not inspect a current archive, authenticate evidence, authorize work or create a
cohort. It deliberately exports no returned patient/reference evidence values.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from ..common.paths import PROJECT_ROOT
from .release_audit import EVIDENCE_COLUMNS

HANDOFF_DIR = PROJECT_ROOT / "docs" / "research-handoff"
LIMIT_BYTES = 1_000_000
FILES = ("BTXRD-audit.json", "BTXRD-evidence-check.json", "BTXRD-evidence-template.csv")
MISSING_FIELDS = ("patient_id", "lesion_id", "grouping_reference", "reference_standard", "reference_evidence")
NOTE = ("Published review snapshot, not a check of your current local files. "
        "Source-byte matches do not establish patient independence or diagnostic truth. "
        "Independent evidence, permissions and protocol review remain necessary.")


class SnapshotError(ValueError):
    pass


def _read(root: Path, name: str) -> bytes:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise SnapshotError("Published review file is unavailable.")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT_BYTES + 1)
    if len(raw) > LIMIT_BYTES:
        raise SnapshotError("Published review file exceeds the read limit.")
    return raw


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise SnapshotError("Published review JSON is malformed.") from error
    if not isinstance(value, dict):
        raise SnapshotError("Published review JSON must be an object.")
    return value


def _count(value) -> int:
    if type(value) is not int or not 0 <= value <= 10_000_000:
        raise SnapshotError("Published review count is invalid.")
    return value


def _load(root: Path) -> tuple[dict, dict, bytes, list[dict]]:
    manifest = _json(_read(root, "publication-manifest.json"))
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise SnapshotError("Publication file identities are missing.")
    raw, identities = {}, []
    for name in FILES:
        matches = [e for e in entries if isinstance(e, dict) and e.get("path") == "docs/research-handoff/" + name]
        if len(matches) != 1:
            raise SnapshotError("Publication file identity is missing or ambiguous.")
        content = _read(root, name)
        sha = hashlib.sha256(content).hexdigest()
        if matches[0].get("sha256") != sha or matches[0].get("bytes") != len(content):
            raise SnapshotError("Published review changed from its recorded file identity.")
        raw[name] = content
        identities.append({"name": name, "sha256": sha, "bytes": len(content)})
    audit, evidence = _json(raw[FILES[0]]), _json(raw[FILES[1]])
    if (audit.get("dataset_id") != "btxrd" or evidence.get("dataset_id") != "btxrd"
            or not isinstance(audit.get("archive"), dict)
            or not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("archive_sha256", "")))
            or audit["archive"].get("sha256") != evidence["archive_sha256"]):
        raise SnapshotError("Published reports refer to different source archives.")
    n = _count(audit.get("image_count"))
    if n == 0 or _count(evidence.get("release_image_count")) != n:
        raise SnapshotError("Published report image counts disagree.")
    # These public snapshots are deliberately non-authorizing. Reject a changed
    # report that claims stronger evidence, even if its manifest was also edited.
    for report in (audit, evidence):
        for flag in ("ready_for_training", "patient_grouping_verified", "reference_standard_verified", "medical_validation_established"):
            if report.get(flag) is not False:
                raise SnapshotError("Published snapshot has an unsupported evidence state.")
    if evidence.get("cohort_created") is not False or evidence.get("supplied_patient_ids_and_reference_values_exported") is not False:
        raise SnapshotError("Published snapshot must not contain returned private evidence.")
    return audit, evidence, raw[FILES[2]], identities


def summary(root: Path | None = None) -> dict:
    """Return aggregate observations; current data/model directories are not read."""
    audit, evidence, _, identities = _load(Path(root) if root is not None else HANDOFF_DIR)
    n = audit["image_count"]
    classes = audit.get("class_counts", {})
    if set(classes) != {"normal", "benign", "malignant"} or sum(_count(v) for v in classes.values()) != n:
        raise SnapshotError("Published class counts disagree with the image count.")
    duplicates, lists, annotations = audit["exact_duplicates"], audit["split_lists"], audit["annotations"]
    conflicts = duplicates["conflicting_label_groups"]
    if not isinstance(conflicts, list) or any(not isinstance(g, list) or any(not isinstance(x, str) for x in g) for g in conflicts):
        raise SnapshotError("Published duplicate groups are malformed.")
    missing = evidence.get("missing_evidence_counts", {})
    if not isinstance(missing, dict) or any(k not in MISSING_FIELDS or _count(v) > n for k, v in missing.items()):
        raise SnapshotError("Published missing-evidence counts are invalid.")
    recorded = {k: _count(evidence.get(k)) for k in ("supplied_row_count", "matched_image_count")}
    if recorded["matched_image_count"] > min(n, recorded["supplied_row_count"]):
        raise SnapshotError("Published source-matching counts disagree.")
    status = evidence.get("status")
    if status not in {"blocked", "declared_evidence_requires_review"}:
        raise SnapshotError("Unknown published evidence status.")
    return {"dataset_id": "btxrd", "available": True, "source_kind": "published_review_snapshot",
            "note": NOTE, "archive_sha256": evidence["archive_sha256"], "files": identities,
            "observations": {"images": n, "annotations": _count(audit["annotation_count"]), "class_counts": classes,
                             "exact_duplicate_pairs": _count(duplicates["pair_count"]),
                             "conflicting_copy_groups": len(conflicts), "conflicting_images": len({x for g in conflicts for x in g}),
                             "pairs_crossing_original_lists": len(lists["exact_duplicate_groups_crossing_lists"]),
                             "original_extension_mismatches": _count(lists["extension_mismatch_count"]),
                             "subtype_label_differences": len(annotations["subtype_label_set_mismatch"])},
            "evidence": {"reported_status": status, "source_binding_reported": evidence.get("source_binding_verified") is True,
                         "missing_counts": {k: missing.get(k, 0) for k in MISSING_FIELDS}, **recorded},
            "ready_for_training": False, "execution_authorized": False, "cohort_created": False,
            "patient_grouping_verified": False, "reference_standard_verified": False,
            "medical_validation_established": False,
            "next_actions": ["Obtain genuine pseudonymous patient/lesion mapping with its evidence reference.",
                             "Obtain per-row diagnostic reference evidence and independent review.",
                             "Adjudicate conflicting source labels and review visual-overlap candidates.",
                             "Review export metadata, rights, the endpoint and prospective evaluation protocol."],
            "commands": ["python -m cancer_workbench btxrd-review audit --help",
                         "python -m cancer_workbench btxrd-review check --help"]}


def blank_template(root: Path | None = None) -> dict:
    """Export only the published blank template, never a returned evidence file."""
    _, evidence, raw, identities = _load(Path(root) if root is not None else HANDOFF_DIR)
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(EVIDENCE_COLUMNS):
        raise SnapshotError("Published evidence template columns changed.")
    rows = list(reader)
    ids = set()
    for row in rows:
        if None in row or any(row.get(k) != "" for k in MISSING_FIELDS) or row.get("review_status") != "unreviewed":
            raise SnapshotError("Only an unreviewed template with blank evidence fields can be exported.")
        sid = row.get("image_id")
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.(?:jpeg|jpg|png)", sid) or sid in ids:
            raise SnapshotError("Published template image identities are invalid.")
        ids.add(sid)
        if not re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", ""))):
            raise SnapshotError("Published template source hash is invalid.")
    if len(rows) != evidence["release_image_count"]:
        raise SnapshotError("Published template count disagrees with its report.")
    return {"filename": "BTXRD-blank-evidence-template.csv", "csv": text, "rows": len(rows),
            "sha256": identities[2]["sha256"], "note": NOTE, "execution_authorized": False}
