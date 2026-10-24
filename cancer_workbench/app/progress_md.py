"""Read and edit PROGRESS.md checklist items and workstream owners in place."""
from __future__ import annotations

import re
from pathlib import Path

from ..common.paths import PROJECT_ROOT

PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.md"
_ITEM = re.compile(r"^(\s*)- \[( |x|~)\] (.*)$")
_HEADING = re.compile(r"^(#{2,3}) (.*)$")
_OWNER_ROW = re.compile(r"^\| ([A-H]) \|")
MARKS = (" ", "x", "~")


def parse(path: Path = PROGRESS_PATH) -> dict:
    sections: list[dict] = []
    owners: list[dict] = []
    current = None
    for n, line in enumerate(path.read_text().splitlines()):
        if m := _HEADING.match(line):
            current = {"level": len(m.group(1)), "title": m.group(2), "items": []}
            sections.append(current)
        elif (m := _ITEM.match(line)) and current is not None:
            text = m.group(3)
            current["items"].append({"line": n, "mark": m.group(2), "text": text, "blocked": "🔒" in text,
                                     "indent": len(m.group(1))})
        elif _OWNER_ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 5:
                owners.append({"line": n, "ws": cells[0], "focus": cells[1], "modules": cells[2], "depends": cells[3], "owner": cells[4]})
    return {"sections": [s for s in sections if s["items"]], "owners": owners}


def _rewrite_line(path: Path, line_no: int, expect_text: str, transform) -> None:
    lines = path.read_text().splitlines(keepends=True)
    if line_no >= len(lines) or expect_text not in lines[line_no]:
        raise ValueError("PROGRESS.md changed on disk since it was loaded. Reload and try again.")
    lines[line_no] = transform(lines[line_no])
    path.write_text("".join(lines))


def set_mark(line_no: int, text: str, mark: str, path: Path = PROGRESS_PATH) -> None:
    if mark not in MARKS:
        raise ValueError(f"mark must be one of {MARKS}")
    _rewrite_line(path, line_no, text, lambda l: re.sub(r"- \[( |x|~)\]", f"- [{mark}]", l, count=1))


def set_owner(line_no: int, ws: str, name: str, path: Path = PROGRESS_PATH) -> None:
    name = name.replace("|", "/").strip()

    def tr(line: str) -> str:
        cells = line.rstrip("\n").strip().strip("|").split("|")
        cells[-1] = f" {name} "
        return "|" + "|".join(cells) + "|\n"

    _rewrite_line(path, line_no, f"| {ws} |", tr)
