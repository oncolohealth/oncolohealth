"""Dataset/model acquisition: resumable verified downloads, storage budget, provenance.

Owner: Workstream A (datasets) with C (models). Records live in catalog/*.json;
files land in data/<id>/ or models/<id>/ with a PROVENANCE.json.
"""
from .download import IntegrityError, download, hash_file, safe_extract_zip, verify
from .sources import AccessError, FilePlan, resolve

__all__ = ["AccessError", "FilePlan", "IntegrityError", "download", "hash_file", "resolve", "safe_extract_zip", "verify"]
