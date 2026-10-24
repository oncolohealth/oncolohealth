"""Durable experiment drafts and read-only ExperimentRecord browsing.

No jobs are dispatched by this module. Recorded states describe saved software
work, not protocol approval or medical validity.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import uuid
from pathlib import Path

from .records import ExperimentRecord

MAX_FILE_BYTES = 2_000_000
MAX_HISTORY_BYTES = 8_000_000
MAX_HISTORY_ITEMS = 500
MAX_RUNS = 100
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_RECORD_FIELDS = {f.name for f in dataclasses.fields(ExperimentRecord)}


def _reject_constant(value):
    raise ValueError("Non-finite JSON value")


def _read_json(path: Path, root: Path):
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Record path leaves the runs folder.")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Record file exceeds the 2 MB preview limit.")
    return json.loads(data, parse_constant=_reject_constant), len(data)


def save_draft(root: Path, preview: dict, *, source_revision: str) -> dict:
    """Persist a freshly computed draft. Never accepts an execution-ready state."""
    if (preview.get("plan", {}).get("state") not in {"blocked", "ready_for_review"}
            or preview["plan"].get("execution_authorized") is not False):
        raise ValueError("Only non-authorizing experiment drafts can be saved.")
    identifier = uuid.uuid4().hex
    folder = root / "drafts"
    if not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError("Draft folder leaves the runs folder.")
    folder.mkdir(parents=True, exist_ok=True)
    doc = {**preview, "schema_version": 1, "kind": "experiment_draft", "id": identifier,
           "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "source_revision": source_revision}
    # Serialize before opening the file. A failed write removes only this newly
    # created file; an identifier collision never overwrites another draft.
    payload = json.dumps(doc, indent=2, allow_nan=False) + "\n"
    if len(payload.encode()) > MAX_FILE_BYTES:
        raise ValueError("Draft exceeds the 2 MB preview limit.")
    path = folder / f"{identifier}.json"
    with path.open("x") as stream:
        try:
            stream.write(payload)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return {"key": f"draft:{identifier}", "file": f"drafts/{identifier}.json", "draft": doc}


def _draft_file(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Unknown draft.")
    return root / "drafts" / f"{identifier}.json"


def _validate_draft(value):
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("kind") != "experiment_draft" or not isinstance(value.get("plan"), dict)
            or value["plan"].get("execution_authorized") is not False
            or value["plan"].get("state") not in {"blocked", "ready_for_review"}):
        raise ValueError("Invalid saved draft.")
    return value


def _records(value):
    if not isinstance(value, list):
        raise ValueError("records.json must contain a list of ExperimentRecord objects.")
    for row in value:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ("id", "task", "model", "state")):
            raise ValueError("Malformed ExperimentRecord.")
    return value


def detail(root: Path, key: str) -> dict:
    if not isinstance(key, str):
        raise ValueError("Select a saved draft or run record.")
    parts = key.split(":")
    if len(parts) == 2 and parts[0] == "draft":
        path = _draft_file(root, parts[1])
        value, _ = _read_json(path, root)
        value = _validate_draft(value)
        if value.get("id") != parts[1]:
            raise ValueError("Saved draft identity does not match its file.")
        return {"key": key, "kind": "draft", "file": f"drafts/{parts[1]}.json", "record": value}
    if (len(parts) == 3 and parts[0] == "run" and _NAME.fullmatch(parts[1])
            and parts[2].isdigit() and len(parts[2]) < 8):
        path = root / parts[1] / "records.json"
        value, _ = _read_json(path, root)
        rows = _records(value)
        index = int(parts[2])
        if index >= len(rows):
            raise ValueError("Unknown run record.")
        # Keep the established record fields. Extra arbitrary file content is
        # not promoted into a new API contract.
        record = {k: v for k, v in rows[index].items() if k in _RECORD_FIELDS or k == "synthetic"}
        return {"key": key, "kind": "run", "file": f"{parts[1]}/records.json", "record": record,
                "note": "Recorded software state. It does not establish protocol approval, independence or medical performance."}
    raise ValueError("Unknown saved record.")


def history(root: Path) -> dict:
    items, warnings = [], []
    total = 0
    files = []
    def modified(item):
        try:
            return item[1].lstat().st_mtime_ns
        except OSError:
            return 0
    if root.exists():
        directories = [d for d in root.iterdir() if d.is_dir() and _NAME.fullmatch(d.name)
                       and d.name != "drafts" and (d / "records.json").is_file()]
        directories.sort(key=lambda d: modified(("run", d / "records.json")), reverse=True)
        for d in directories[:MAX_RUNS]:
            if (d / "records.json").is_file():
                files.append(("run", d / "records.json"))
        if len(directories) > MAX_RUNS:
            warnings.append(f"Only the {MAX_RUNS} most recently modified run record files were inspected.")
        drafts = root / "drafts"
        if drafts.exists() and drafts.resolve().is_relative_to(root.resolve()):
            draft_files = sorted(drafts.glob("*.json"), key=lambda f: modified(("draft", f)), reverse=True)
            files += [("draft", f) for f in draft_files[:MAX_HISTORY_ITEMS]]
            if len(draft_files) > MAX_HISTORY_ITEMS:
                warnings.append("Older drafts exceed the history preview limit and remain on disk.")
    files.sort(key=modified, reverse=True)
    for kind, path in files:
        if len(items) >= MAX_HISTORY_ITEMS or total >= MAX_HISTORY_BYTES:
            warnings.append("History preview limit reached. Older records remain on disk.")
            break
        try:
            # Count malformed files against the aggregate read budget as well.
            size = min(path.stat().st_size, MAX_FILE_BYTES + 1)
            if total + size > MAX_HISTORY_BYTES:
                warnings.append("History byte-preview limit reached. Older records remain on disk.")
                break
            total += size
            value, size = _read_json(path, root)
            if kind == "draft":
                if not re.fullmatch(r"[0-9a-f]{32}", path.stem):
                    raise ValueError("Unknown draft filename.")
                doc = _validate_draft(value)
                if doc.get("id") != path.stem:
                    raise ValueError("Saved draft identity does not match its file.")
                items.append({"key": f"draft:{path.stem}", "kind": "draft", "id": doc["id"],
                              "state": doc["plan"]["state"], "model": doc["plan"].get("model_id"),
                              "task": doc.get("question") or "Experiment draft", "created_at": doc.get("created_at"),
                              "synthetic": doc.get("synthetic") is True})
            else:
                for i, row in enumerate(_records(value)):
                    if len(items) >= MAX_HISTORY_ITEMS:
                        warnings.append("History preview limit reached. Older records remain on disk.")
                        break
                    items.append({"key": f"run:{path.parent.name}:{i}", "kind": "run",
                                  **{k: row[k] for k in ("id", "state", "model", "task")},
                                  "synthetic": row.get("synthetic") if isinstance(row.get("synthetic"), bool) else None})
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            warnings.append(f"{path.parent.name}/{path.name}: {exc}")
    return {"items": items, "warnings": warnings,
            "note": "Saved local records. A recorded completion is not a medical validation or execution permission."}
