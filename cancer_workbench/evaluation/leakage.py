"""Declared-record overlap checks; absent matches never establish independence.

Pretraining refs: [{id, citation, coverage: complete|partial|unknown,
                   dataset_id: optional namespace, records: [manifest-like rows]}].
Unstructured citations are retained as unresolved findings. sample_id/patient_id
matches against pretraining require matching dataset_id namespaces; sha256 does
not. `source` means a documented source identifier, not a local center number.
"""
from __future__ import annotations

from collections import Counter


def _values(rows, key):
    return {r[key] for r in rows if r.get(key)}


def _validate(rows):
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError("rows must be lists of manifest-like records")
    for row in rows:
        for key in ("sample_id", "patient_id", "duplicate_group", "sha256", "dataset_id", "source"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or value != value.strip()):
                raise ValueError(f"{key} must be a trimmed string when supplied")


def check(train_rows: list[dict], eval_rows: list[dict], pretraining_refs: list) -> list[dict]:
    """Report exact train/eval overlaps, shared sources and unresolved pretraining coverage.

    Evaluation means validation OR test. Empty partitions and missing patient
    identifiers are reported, so an empty result cannot mask an absent split.
    This is not a pixel similarity, patient identity or label-truth validator.
    """
    _validate(train_rows)
    _validate(eval_rows)
    if not isinstance(pretraining_refs, list):
        raise ValueError("pretraining_refs must be a list")
    findings = []

    def add(severity, code, detail, **extra):
        findings.append({"severity": severity, "code": code, "detail": detail, **extra})

    for name, rows in (("train", train_rows), ("eval", eval_rows)):
        if not rows:
            add("error", "empty_partition", f"{name} has no rows")
        for key in ("sample_id", "patient_id"):
            missing = sum(not r.get(key) for r in rows)
            if missing:
                add("error" if key == "sample_id" else "warning", f"missing_{key}", f"{name}: {missing}/{len(rows)} missing")
        repeats = sorted(k for k, n in Counter(r.get("sample_id") for r in rows if r.get("sample_id")).items() if n > 1)
        if repeats:
            add("error", "duplicate_sample_id", f"repeated ids in {name}", values=repeats)
    for key in ("sample_id", "patient_id", "duplicate_group", "sha256"):
        overlap = sorted(_values(train_rows, key) & _values(eval_rows, key))
        if overlap:
            add("error", f"{key}_overlap", f"{len(overlap)} declared {key} values occur in train and eval", values=overlap)
    for key in ("dataset_id", "source"):
        overlap = sorted(_values(train_rows, key) & _values(eval_rows, key))
        if overlap:
            add("warning", f"shared_{key}", "Shared provenance; this alone is not case-level leakage or external validation", values=overlap)
    if not pretraining_refs:
        add("warning", "pretraining_unresolved", "No pretraining records supplied; overlap remains unknown")
    for ref in pretraining_refs:
        if not isinstance(ref, dict) or not isinstance(ref.get("records"), list):
            add("warning", "pretraining_unresolved", "Reference lacks inspectable records; overlap remains unknown")
            continue
        records = ref["records"]
        _validate(records)
        records = [dict(r, dataset_id=r.get("dataset_id") or ref.get("dataset_id", "")) for r in records]
        _validate(records)
        ref_id = ref.get("id", "unidentified")
        if not ref.get("citation") or ref.get("coverage") != "complete" or not records:
            add("warning", "pretraining_unresolved", "Missing citation, incomplete coverage, or empty pretraining records", reference=ref_id)
        for name, rows in (("train", train_rows), ("eval", eval_rows)):
            for key in ("sha256", "sample_id", "patient_id"):
                if key == "sha256":
                    overlap = sorted(_values(rows, key) & _values(records, key))
                else:
                    scoped = lambda rr: {(r["dataset_id"], r[key]) for r in rr if r.get("dataset_id") and r.get(key)}
                    overlap = [list(v) for v in sorted(scoped(rows) & scoped(records))]
                if overlap:
                    add("error" if name == "eval" else "warning", "pretraining_overlap",
                        f"{name}: exact declared {key} match", reference=ref_id, key=key, values=overlap)
            for key in ("dataset_id", "source"):
                overlap = sorted(_values(rows, key) & _values(records, key))
                if overlap:
                    add("warning", "pretraining_provenance_overlap", f"{name}: shared {key}; inspect cases", reference=ref_id, values=overlap)
        add("info", "pretraining_scope", "Checks cover supplied identifiers only; no match does not prove independence", reference=ref_id)
    return findings
