"""Dataset audit over a manifest + spec.

Implemented: unresolved-evidence findings from the spec, per-partition class counts,
patient and duplicate-group leakage across partitions, missing grouping ids,
optional file existence/sha256 checks.
NOT implemented (Workstream A/F): pixel/geometry inspection, near-duplicate
detection, source verification, label adjudication. A hash proves file
identity only; it says nothing about label truth or consent.
"""
from __future__ import annotations

import collections
from pathlib import Path

from ..acquisition.download import hash_file
from .manifest import PARTITIONS


def _cross_partition(rows: list[dict], key: str) -> dict[str, list[str]]:
    parts: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        if r.get(key) and r.get("partition") in ("train", "val", "test"):
            parts[r[key]].add(r["partition"])
    return {g: sorted(p) for g, p in parts.items() if len(p) > 1}


def audit_dataset(spec: dict, rows: list[dict], files_root: Path | None = None) -> dict:
    findings: list[dict] = []

    def add(severity: str, code: str, detail: str):
        findings.append({"severity": severity, "code": code, "detail": detail})

    for item in spec.get("unresolved", []):
        add("warning", "unresolved_evidence", item)

    ids = [r["sample_id"] for r in rows]
    dup_ids = [i for i, n in collections.Counter(ids).items() if n > 1]
    if dup_ids:
        add("error", "duplicate_sample_id", f"{len(dup_ids)} sample ids repeat, e.g. {dup_ids[:3]}")

    bad_part = sorted({r.get("partition", "") for r in rows} - set(PARTITIONS))
    if bad_part:
        add("error", "invalid_partition", f"unknown partitions {bad_part}")

    classes = spec.get("classes")
    if classes:
        bad = sorted({r["label"] for r in rows} - set(classes))
        if bad:
            add("error", "unknown_label", f"labels not in spec classes: {bad}")

    no_patient = sum(1 for r in rows if not r.get("patient_id"))
    if no_patient:
        add("error" if no_patient == len(rows) else "warning", "missing_patient_id",
            f"{no_patient}/{len(rows)} rows lack patient_id; patient-level claims and leakage checks are unsupported for them")

    for key, code in (("patient_id", "patient_leakage"), ("duplicate_group", "duplicate_leakage")):
        leaks = _cross_partition(rows, key)
        if leaks:
            ex = list(leaks.items())[:3]
            add("error", code, f"{len(leaks)} {key} values span partitions, e.g. {ex}")

    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    patients: dict[str, set] = collections.defaultdict(set)
    for r in rows:
        counts[r.get("partition", "")][r["label"]] += 1
        if r.get("patient_id"):
            patients[r.get("partition", "")].add(r["patient_id"])

    file_checks = {"checked": 0, "missing": 0, "hash_mismatch": 0}
    if files_root is not None:
        for r in rows:
            if not r.get("file"):
                continue
            f = Path(files_root) / r["file"]
            file_checks["checked"] += 1
            if not f.exists():
                file_checks["missing"] += 1
            elif r.get("sha256") and hash_file(f)["sha256"] != r["sha256"]:
                file_checks["hash_mismatch"] += 1
        if file_checks["missing"] or file_checks["hash_mismatch"]:
            add("error", "file_integrity", str(file_checks))

    errors = sum(1 for f in findings if f["severity"] == "error")
    return {
        "dataset_id": spec.get("id"),
        "rows": len(rows),
        "class_counts": {p: dict(c) for p, c in counts.items()},
        "patients_per_partition": {p: len(s) for p, s in patients.items()},
        "file_checks": file_checks if files_root is not None else None,
        "findings": findings,
        "ready_for_training": errors == 0 and not spec.get("unresolved"),
        "note": "Audit covers declared records only; it cannot certify label correctness, consent or representativeness.",
    }
