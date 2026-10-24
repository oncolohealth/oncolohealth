"""Minimal read-only .xlsx reader (standard library only) for dataset metadata sheets.

Reads cell values as strings; no formulas, styles or dates. Treat the file as
untrusted: member sizes are capped and nothing in it is executed.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_MEMBER_BYTES = 200 * 10**6


def _xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    if zf.getinfo(name).file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"{name} exceeds {MAX_MEMBER_BYTES} bytes uncompressed")
    return ET.fromstring(zf.read(name))


def _col(ref: str) -> int:
    n = 0
    for c in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(c) - 64
    return n - 1


def _text(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(f"{_M}t"))


def sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return [s.get("name") for s in _xml(zf, "xl/workbook.xml").iter(f"{_M}sheet")]


def read_sheet(path: Path, sheet: str | None = None) -> list[list[str]]:
    """Return the rows of `sheet` (default: the first) as lists of strings, padded to equal width."""
    with zipfile.ZipFile(path) as zf:
        sheets = {s.get("name"): s.get(f"{_R}id") for s in _xml(zf, "xl/workbook.xml").iter(f"{_M}sheet")}
        if not sheets:
            return []
        rid = sheets[sheet] if sheet else next(iter(sheets.values()))
        rels = {r.get("Id"): r.get("Target") for r in _xml(zf, "xl/_rels/workbook.xml.rels").iter(f"{_PKG_REL}Relationship")}
        target = rels[rid].lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        shared = [_text(si) for si in _xml(zf, "xl/sharedStrings.xml").iter(f"{_M}si")] if "xl/sharedStrings.xml" in zf.namelist() else []
        rows = []
        for row in _xml(zf, target).iter(f"{_M}row"):
            cells = {}
            for c in row.iter(f"{_M}c"):
                v, kind = c.find(f"{_M}v"), c.get("t")
                if kind == "inlineStr":
                    cells[_col(c.get("r"))] = _text(c)
                elif v is not None:
                    cells[_col(c.get("r"))] = shared[int(v.text)] if kind == "s" else (v.text or "")
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]
