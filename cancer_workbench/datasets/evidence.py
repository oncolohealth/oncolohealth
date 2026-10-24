"""Bind a returned evidence handoff to local source bytes; no medical attestation."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from .release_audit import audit_btxrd_release, EVIDENCE_COLUMNS

UNRESOLVED = {"", "unknown", "unavailable", "none", "n/a", "na", "not provided",
              "pending", "tbd", "unreviewed"}
IMMUTABLE = ("center", "tumor", "benign", "malignant", "sha256", "review_flags")
REQUIRED_EVIDENCE = ("patient_id", "grouping_reference", "lesion_id", "reference_standard", "reference_evidence")


def _text(value):
    return "" if value is None else str(value).strip()


def _source_value(field, value):
    value = _text(value)
    if field in {"tumor", "benign", "malignant"}:
        return {"0": "0", "0.0": "0", "false": "0", "1": "1", "1.0": "1", "true": "1"}.get(value.casefold(), value)
    if field == "center":
        return value.removesuffix(".0")
    if field == "sha256":
        return value.lower()
    if field == "review_flags":
        return tuple(sorted(filter(None, (v.strip() for v in value.split(";")))))
    return value


def check_btxrd_evidence(archive, evidence_rows, *, expected_md5=None):
    """Check source binding and declared completeness; never create a cohort.

    The returned report omits supplied patient IDs and evidence/reference values.
    Non-placeholder text is still an unverified assertion, not an authenticated map.
    """
    rows = list(evidence_rows)
    if any(not isinstance(row, dict) or set(row) != set(EVIDENCE_COLUMNS) for row in rows):
        raise ValueError("Evidence input must preserve exactly the template columns")
    source = audit_btxrd_release(archive, expected_md5=expected_md5, include_evidence_rows=True)
    baseline = {row["image_id"]: row for row in source["evidence_rows"]}
    if not baseline:
        raise ValueError("Cannot check evidence against empty source metadata")
    supplied, repeated = {}, Counter()
    for row in rows:
        name = _text(row["image_id"])
        repeated[name] += 1
        supplied.setdefault(name, row)
    findings = []

    def finding(code, count, **extra):
        if count:
            findings.append({"level": "blocker", "code": code, "image_count": count, **extra})

    finding("duplicate_image_id", sum(n - 1 for n in repeated.values() if n > 1))
    finding("unknown_image_id", len(set(supplied) - set(baseline)))
    finding("release_image_missing", len(set(baseline) - set(supplied)))
    matched = sorted(set(supplied) & set(baseline))
    source_changes = {}
    for field in IMMUTABLE:
        changed = [name for name in matched
                   if _source_value(field, supplied[name][field]) != _source_value(field, baseline[name][field])]
        if changed:
            source_changes[field] = changed
            finding("source_field_drift", len(changed), field=field, example_image_ids=changed[:10])
    bound = not (set(supplied) != set(baseline) or source_changes or any(n > 1 for n in repeated.values()))
    missing = Counter()
    source_names = {name.casefold() for name in baseline} | {PurePosixPath(name).stem.casefold() for name in baseline}
    unresolved_status = 0
    valid_groups = []
    for name in matched:
        row = supplied[name]
        unresolved = set()
        for field in REQUIRED_EVIDENCE:
            value = _text(row[field])
            if value.casefold() in UNRESOLVED or (field in {"patient_id", "lesion_id"} and value.casefold() in source_names):
                missing[field] += 1
                unresolved.add(field)
        if _text(row["review_status"]).casefold() != "reviewed":
            unresolved_status += 1
        if not unresolved & {"patient_id", "lesion_id"}:
            valid_groups.append(name)
    for field, count in sorted(missing.items()):
        finding("evidence_missing_or_placeholder", count, field=field)
    finding("review_status_not_reviewed", unresolved_status)
    conflict_ids = {name for group in source["exact_duplicates"]["conflicting_label_groups"] for name in group}
    finding("source_exact_duplicate_label_conflict", len(conflict_ids))
    invalid_flags = sum(source["class_counts"].get(key, 0) for key in ("invalid_flags", "conflicting_flags"))
    finding("source_diagnostic_flags_unresolved", invalid_flags)
    exact_patient_conflicts = 0
    for group in source["exact_duplicates"]["groups"]:
        patients = {_text(supplied[name]["patient_id"]) for name in group if name in supplied
                    and _text(supplied[name]["patient_id"]).casefold() not in UNRESOLVED}
        if len(patients) > 1:
            exact_patient_conflicts += len(group)
    finding("exact_duplicate_patient_mapping_conflict", exact_patient_conflicts)
    lesion_labels = defaultdict(set)
    lesion_sizes = Counter()
    for name in valid_groups:
        row = supplied[name]
        key = (_text(row["patient_id"]), _text(row["lesion_id"]))
        label = tuple(baseline[name][k] for k in ("tumor", "benign", "malignant"))
        lesion_labels[key].add(label)
        lesion_sizes[key] += 1
    finding("declared_lesion_source_label_conflict", sum(lesion_sizes[k] for k, labels in lesion_labels.items() if len(labels) > 1))
    mismatches = source["annotations"]["subtype_label_set_mismatch"]
    if mismatches:
        findings.append({"level": "warning", "code": "source_subtype_label_set_difference_requires_review",
                         "image_count": len(mismatches)})
    findings.extend({"level": "warning", "code": code} for code in (
        "patient_and_lesion_mapping_assertions_not_authenticated",
        "diagnostic_reference_assertions_not_verified", "permissions_and_protocol_require_review",
        "near_duplicate_and_pixel_privacy_review_not_completed"))
    content = sorted(rows, key=lambda row: (_text(row["image_id"]), json.dumps(row, sort_keys=True)))
    return {
        "dataset_id": "btxrd", "scope": "Local source binding and declared evidence completeness only",
        "status": "blocked" if any(f["level"] == "blocker" for f in findings) else "declared_evidence_requires_review",
        "archive_sha256": source["archive"]["sha256"],
        "archive_reference_md5_checked": source["archive"]["reference_md5_checked"],
        "evidence_content_sha256": hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "release_image_count": len(baseline), "supplied_row_count": len(rows), "matched_image_count": len(matched),
        "source_binding_verified": bound, "missing_evidence_counts": dict(sorted(missing.items())),
        "findings": findings, "ready_for_training": False, "cohort_created": False,
        "patient_grouping_verified": False, "reference_standard_verified": False,
        "medical_validation_established": False,
        "supplied_patient_ids_and_reference_values_exported": False}
