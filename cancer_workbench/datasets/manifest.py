"""Manifest row contract shared by datasets, learning and evaluation.

A manifest is a CSV with one row per image/volume/tile:

    sample_id        unique per row
    patient_id       grouping id for independent subjects ("" when unknown -> audit finding)
    duplicate_group  optional; rows sharing it are (near-)duplicates and must stay together
    partition        train | val | test | unassigned
    label            reference label string (ordered class list lives in the dataset spec)
    file             optional path relative to the dataset root
    sha256           optional file digest
"""
from __future__ import annotations

import csv
from pathlib import Path

FIELDS = ("sample_id", "patient_id", "duplicate_group", "partition", "label", "file", "sha256")
PARTITIONS = ("train", "val", "test", "unassigned")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS:
            r.setdefault(k, "")
    return rows


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = sorted({k for r in rows for k in r} - set(FIELDS))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS) + extra)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in list(FIELDS) + extra})
