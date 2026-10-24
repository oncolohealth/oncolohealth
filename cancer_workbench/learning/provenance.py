"""Measured identities for feature inputs. Standard library only, no inference.

Hashes establish byte identity, not medical truth, rights, publisher authenticity
or absent patient overlap. A feature binding is a local reproducibility record.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import stat
import csv
import io
from pathlib import Path

SCHEMA_VERSION = 1
_SHA = re.compile(r"[0-9a-f]{64}")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def measured_file(path: Path) -> dict:
    """Read once, refusing ordinary concurrent replacement/write of the file."""
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Input is not a regular file: {path.name}")
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            sha.update(chunk)
            size += len(chunk)
    after = path.stat()
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if fields(before) != fields(after) or size != after.st_size:
        raise ValueError(f"Input file changed while hashing: {path.name}")
    return {"sha256": sha.hexdigest(), "bytes": size}


def image_sources(rows: list[dict], data_root: Path) -> dict:
    if not rows:
        raise ValueError("Feature extraction requires nonempty source rows.")
    root = Path(data_root).resolve()
    samples, seen = [], set()
    for row in rows:
        sid, file = row.get("sample_id"), row.get("file")
        if not isinstance(sid, str) or not sid.strip() or sid != sid.strip() or sid in seen:
            raise ValueError("Feature sources need unique nonempty sample IDs without surrounding whitespace.")
        seen.add(sid)
        if not isinstance(file, str) or not file.strip() or Path(file).is_absolute():
            raise ValueError(f"Source {sid!r} needs a relative image file.")
        path = (root / file).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Source {sid!r} leaves the dataset root.")
        measured = measured_file(path)
        declared = row.get("sha256")
        if declared not in (None, "") and (not isinstance(declared, str) or not _SHA.fullmatch(declared.lower()) or declared.lower() != measured["sha256"]):
            raise ValueError(f"Declared image hash mismatch for {sid!r}. Re-audit the source before using features.")
        samples.append({"sample_id": sid, "file": path.relative_to(root).as_posix(), **measured})
    samples.sort(key=lambda row: row["sample_id"])
    return {"samples": samples, "sha256": digest(samples)}


def model_identity(encoder_id: str, variant: str = "pad", models_dir: Path | None = None) -> dict:
    from ..adapters import encoder

    if encoder_id not in encoder.ENCODERS:
        raise ValueError(f"Unknown encoder {encoder_id!r}")
    base = Path(encoder.MODELS_DIR if models_dir is None else models_dir)
    declared_revision = encoder.revision(encoder_id, base)
    root = (base / encoder_id).resolve()
    names = ["model.safetensors"]
    if encoder.ENCODERS[encoder_id]["arch"] == "dinov2":
        names.append("config.json")  # actually consumed by Dinov2Model.from_pretrained
    files = {}
    for name in names:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Model file {name!r} leaves its configured root.")
        files[name] = measured_file(path)
    versions = {}
    for package in ("numpy", "Pillow", "torch", "timm", "transformers", "safetensors"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    body = {"encoder_id": encoder_id, "revision": declared_revision, "files": files,
            "architecture": encoder.ENCODERS[encoder_id]["arch"], "feature_dim": encoder.ENCODERS[encoder_id]["dim"],
            "variant": variant, "preprocessing": encoder.preprocessing(encoder_id, variant),
            "preprocessing_hash": encoder.preprocessing_hash(encoder_id, variant),
            "implementation_sha256": encoder.IMPLEMENTATION_SHA256, "library_versions": versions}
    return {**body, "sha256": digest(body)}


def binding(sources: dict, model: dict) -> dict:
    body = {"schema_version": SCHEMA_VERSION, "sources": sources, "model": model}
    return {**body, "sha256": digest(body)}


def feature_binding(encoder_id: str, rows: list[dict], data_root: Path, variant: str = "pad", models_dir: Path | None = None) -> dict:
    return binding(image_sources(rows, data_root), model_identity(encoder_id, variant, models_dir))


def valid_sha(value) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def manifest_snapshot(path: Path) -> tuple[list[dict], str]:
    """Parse and hash the same bytes, rather than rereading a changing manifest."""
    from ..datasets.manifest import FIELDS

    raw = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Manifest needs distinct CSV column names.")
    rows = list(reader)
    for row in rows:
        if None in row:
            raise ValueError("Malformed manifest CSV row.")
        for field in FIELDS:
            row.setdefault(field, "")
    return rows, hashlib.sha256(raw).hexdigest()
