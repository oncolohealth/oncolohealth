"""BTXRD -> manifest. Owner: Workstream A. STUB until the release has been inspected.

Contract:
    build_manifest(raw_dir: Path) -> list[dict]
        One row per radiograph following datasets/manifest.py. Must:
        - derive `label` for the chosen endpoint (see PROGRESS.md: endpoint decision)
        - set `patient_id` ONLY from a source-provided identifier; never invent one
        - keep `partition` = "unassigned" (splitting is a separate, reviewed step)
        - carry source metadata columns (age, sex, site, center...) as extra fields
    describe_release(raw_dir: Path) -> dict
        File inventory and metadata columns, for the readiness report.
"""
from __future__ import annotations

from pathlib import Path


def describe_release(raw_dir: Path) -> dict:
    raise NotImplementedError("Workstream A: inventory data/btxrd/BTXRD/ and document the metadata columns")


def build_manifest(raw_dir: Path) -> list[dict]:
    raise NotImplementedError("Workstream A: implement after the endpoint and grouping decisions are recorded")
