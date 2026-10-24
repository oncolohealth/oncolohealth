"""Read-only BTXRD archive audit. No extraction, acquisition, training or network."""

import csv
import hashlib
import io
import json
import re
import stat
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LABEL_FLAGS = {(False, False, False): "normal", (True, True, False): "benign",
               (True, False, True): "malignant"}
MAX_MEMBER = 20_000_000
SUBTYPES = {"osteochondroma", "multiple osteochondromas", "simple bone cyst", "giant cell tumor",
            "osteofibroma", "synovial osteochondroma", "other bt", "osteosarcoma", "other mt"}
EVIDENCE_COLUMNS = ("image_id", "center", "tumor", "benign", "malignant", "sha256",
                    "patient_id", "grouping_reference", "lesion_id", "reference_standard",
                    "reference_evidence", "review_status", "review_flags")


def _member_bytes(archive, member):
    if archive.getinfo(member).file_size > MAX_MEMBER:
        raise ValueError("Tabular, annotation or EXIF input exceeds the 20 MB member limit")
    return archive.read(member)


def _safe_members(archive):
    infos = archive.infolist()
    names = [i.filename for i in infos]
    if len(names) != len(set(names)):
        raise ValueError("ZIP has duplicate member paths")
    for info in infos:
        name = info.filename.replace("\\", "/")
        if (PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or re.match(r"^[A-Za-z]:", name)
                or stat.S_ISLNK(info.external_attr >> 16)):
            raise ValueError("ZIP contains an unsafe path or symbolic link")
    return names


def _xlsx_rows(data):
    """Read the workbook's first worksheet; reject formulas and ambiguous headers."""
    with ZipFile(io.BytesIO(data)) as book:
        names = _safe_members(book)
        workbook = ET.fromstring(_member_bytes(book, "xl/workbook.xml"))
        sheets = workbook.findall("x:sheets/x:sheet", NS)
        if not sheets:
            raise ValueError("XLSX has no worksheet")
        rel_id = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = ET.fromstring(_member_bytes(book, "xl/_rels/workbook.xml.rels"))
        matches = [r for r in rels if r.get("Id") == rel_id]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("XLSX first worksheet relationship is invalid")
        target = matches[0].get("Target", "")
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in PurePosixPath(sheet_path).parts or sheet_path not in names:
            raise ValueError("XLSX first worksheet path is invalid")
        strings = []
        if "xl/sharedStrings.xml" in names:
            shared = ET.fromstring(_member_bytes(book, "xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in s.findall(".//x:t", NS))
                       for s in shared.findall("x:si", NS)]
        sheet = ET.fromstring(_member_bytes(book, sheet_path))
        grid = []
        for row in sheet.findall(".//x:sheetData/x:row", NS):
            values = {}
            for cell in row.findall("x:c", NS):
                if cell.find("x:f", NS) is not None:
                    raise ValueError("XLSX formulas require a reviewed values-only export")
                match = re.fullmatch(r"([A-Z]+)[0-9]+", cell.get("r", ""))
                if not match:
                    raise ValueError("XLSX has an invalid cell reference")
                col = 0
                for char in match.group(1):
                    col = col * 26 + ord(char) - 64
                value = cell.find("x:v", NS)
                raw = value.text if value is not None and value.text is not None else ""
                if cell.get("t") == "s":
                    index = int(raw)
                    if not 0 <= index < len(strings):
                        raise ValueError("XLSX shared-string index is invalid")
                    raw = strings[index]
                elif cell.get("t") == "inlineStr":
                    raw = "".join(t.text or "" for t in cell.findall(".//x:t", NS))
                if col in values:
                    raise ValueError("XLSX repeats a cell")
                values[col] = raw
            if any(str(v).strip() for v in values.values()):
                grid.append(values)
    if not grid:
        raise ValueError("XLSX first worksheet is empty")
    fields = [grid[0].get(i, "").strip() for i in range(1, max(grid[0]) + 1)]
    if not all(fields) or len(fields) != len(set(fields)):
        raise ValueError("Table needs nonempty unique headers")
    if any(any(i > len(fields) and str(v).strip() for i, v in r.items()) for r in grid[1:]):
        raise ValueError("XLSX data extends beyond its header width")
    return fields, [{f: r.get(i, "") for i, f in enumerate(fields, 1)} for r in grid[1:]]


def _table(data, suffix):
    if suffix.lower() == ".xlsx":
        return _xlsx_rows(data)
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    fields = reader.fieldnames or []
    if not fields or not all(fields) or len(fields) != len(set(fields)):
        raise ValueError("Table needs nonempty unique headers")
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("CSV rows do not match the header width")
    return fields, rows


def _image_id(value):
    name = str(value).strip()
    if (not name or "/" in name or "\\" in name or name[0] in "=+-@"
            or any(ord(char) < 32 for char in name)):
        raise ValueError("image_id must be a nonempty filename")
    return name if name.lower().endswith((".jpg", ".jpeg")) else name + ".jpeg"


def _label(row):
    flags = []
    for name in ("tumor", "benign", "malignant"):
        value = str(row[name]).strip().lower()
        if value not in {"0", "0.0", "false", "1", "1.0", "true"}:
            return "invalid_flags"
        flags.append(value in {"1", "1.0", "true"})
    return LABEL_FLAGS.get(tuple(flags), "conflicting_flags")


def _split_audit(train_list, validation_list, image_ids, duplicates):
    if not train_list and not validation_list:
        return {"checked": False}
    if not train_list or not validation_list:
        raise ValueError("Supply both training and validation lists")
    lists, digests = [], []
    for path in (Path(train_list), Path(validation_list)):
        data = path.read_bytes()
        digests.append(hashlib.sha256(data).hexdigest())
        fields, rows = _table(data, path.suffix)
        if "image_id" not in fields:
            raise ValueError("Split lists require image_id")
        ids = [_image_id(r["image_id"]) for r in rows]
        if len({Path(n).stem for n in ids}) != len(ids):
            raise ValueError("Split list repeats an image stem")
        lists.append(ids)
    train, val = [{Path(n).stem for n in group} for group in lists]
    release = {Path(n).stem: n for n in image_ids}
    if len(release) != len(image_ids):
        raise ValueError("Release has ambiguous image stems")
    mismatches = sorted(n for group in lists for n in group
                        if Path(n).stem in release and release[Path(n).stem] != n)
    cross = [g for g in duplicates if {Path(n).stem for n in g} & train
             and {Path(n).stem for n in g} & val]
    return {"checked": True, "train_count": len(train), "validation_count": len(val),
            "train_list_sha256": digests[0], "validation_list_sha256": digests[1],
            "overlap_image_stems": sorted(train & val),
            "unknown_image_stems": sorted((train | val) - release.keys()),
            "release_image_stems_omitted": sorted(release.keys() - (train | val)),
            "extension_mismatch_count": len(mismatches),
            "exact_duplicate_groups_crossing_lists": cross,
            "patient_independence_established": False}


def audit_btxrd_release(path, *, expected_md5=None, train_list=None,
                        validation_list=None, inspect_exif=False, include_evidence_rows=False):
    """Return structural findings only; never attest patient or medical validity."""
    if expected_md5 is not None and not re.fullmatch(r"[a-fA-F0-9]{32}", expected_md5):
        raise ValueError("Expected MD5 must contain 32 hexadecimal characters")
    if inspect_exif:
        try:
            from PIL import Image, ExifTags
        except ImportError as exc:
            raise ValueError("EXIF tag counting needs optional Pillow; values are never exported") from exc
    md5, sha = hashlib.md5(), hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            md5.update(block)
            sha.update(block)
    if expected_md5 and md5.hexdigest() != expected_md5.lower():
        raise ValueError("Archive MD5 does not match the supplied reference")
    try:
        with ZipFile(path) as archive:
            names = _safe_members(archive)
            if len(names) > 50_000 or sum(i.file_size for i in archive.infolist()) > 2_000_000_000:
                raise ValueError("Archive exceeds this audit's 50,000-member / 2 GB uncompressed limit")
            if archive.testzip() is not None:
                raise ValueError("Archive CRC check failed")
            metadata = [n for n in names if PurePosixPath(n).name.lower() in {"dataset.xlsx", "dataset.csv"}]
            if len(metadata) != 1:
                raise ValueError("Archive must have exactly one dataset.xlsx or dataset.csv")
            fields, rows = _table(_member_bytes(archive, metadata[0]), Path(metadata[0]).suffix)
            if not {"image_id", "center", "tumor", "benign", "malignant"}.issubset(fields):
                raise ValueError("BTXRD metadata is missing required columns")
            ids = [_image_id(r["image_id"]) for r in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("Metadata repeats image_id")
            by_id = dict(zip(ids, rows))
            by_stem = {Path(n).stem: n for n in ids}
            if len(by_stem) != len(ids):
                raise ValueError("Metadata has ambiguous image stems")
            labels = {n: _label(r) for n, r in by_id.items()}
            images = [n for n in names if n.lower().endswith((".jpg", ".jpeg"))]
            annotations = [n for n in names if n.lower().endswith(".json")]
            image_names = [PurePosixPath(n).name for n in images]
            annotation_ids = [PurePosixPath(n).stem for n in annotations]
            if len(image_names) != len(set(image_names)) or len(annotation_ids) != len(set(annotation_ids)):
                raise ValueError("Archive has ambiguous image or annotation filenames")
            digests, image_digests = defaultdict(list), {}
            exif_counts, exif_nonempty = Counter(), Counter()
            for member in images:
                h = hashlib.sha256()
                with archive.open(member) as stream:
                    for block in iter(lambda: stream.read(1 << 20), b""):
                        h.update(block)
                image_name = PurePosixPath(member).name
                image_digests[image_name] = h.hexdigest()
                digests[h.hexdigest()].append(image_name)
                if inspect_exif:
                    with Image.open(io.BytesIO(_member_bytes(archive, member))) as image:
                        exif = image.getexif()
                        exif_counts.update(str(ExifTags.TAGS.get(k, k)) for k in exif)
                        exif_nonempty.update(str(ExifTags.TAGS.get(k, k)) for k in exif if exif.get(k))
            shapes, annotation_labels, bad_json, bad_paths = Counter(), Counter(), [], []
            subtype_mismatches = []
            subtype_checked = SUBTYPES.issubset(fields)
            for member in annotations:
                name = PurePosixPath(member).name
                try:
                    data = json.loads(_member_bytes(archive, member))
                    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
                        raise ValueError("Invalid annotation structure")
                    if any(not isinstance(s, dict) for s in data["shapes"]):
                        raise ValueError("Invalid annotation shape")
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    bad_json.append(name)
                    continue
                embedded = PurePosixPath(str(data.get("imagePath") or "").replace("\\", "/")).stem
                if not embedded or embedded != PurePosixPath(member).stem:
                    bad_paths.append(name)
                shapes.update(str(s.get("shape_type")) for s in data["shapes"])
                annotation_labels.update(str(s.get("label")) for s in data["shapes"])
                image_id = by_stem.get(PurePosixPath(member).stem)
                if subtype_checked and image_id:
                    row = by_id[image_id]
                    expected = {k for k in SUBTYPES if str(row[k]).strip().lower() in {"1", "1.0", "true"}}
                    observed = {str(s.get("label")).strip().lower() for s in data["shapes"]}
                    if expected != observed:
                        subtype_mismatches.append({"image_id": image_id, "metadata_subtypes": sorted(expected),
                                                   "annotation_labels": sorted(observed)})
    except (BadZipFile, ET.ParseError, IndexError, KeyError) as exc:
        raise ValueError("Archive or spreadsheet structure is unreadable") from exc
    duplicates = sorted(sorted(g) for g in digests.values() if len(g) > 1)
    tumor_ids = {Path(n).stem for n, lab in labels.items() if lab in {"benign", "malignant"}}
    centers = defaultdict(Counter)
    for n, r in by_id.items():
        centers[str(r["center"]).strip().removesuffix(".0")][labels[n]] += 1
    report = {
        "dataset_id": "btxrd", "audit_scope": "offline_structure_and_declared_metadata",
        "archive": {"bytes": Path(path).stat().st_size, "md5": md5.hexdigest(), "sha256": sha.hexdigest(),
                    "reference_md5_checked": expected_md5 is not None, "crc_check": "passed"},
        "metadata": {"file": Path(metadata[0]).name, "fields": fields, "rows": len(rows)},
        "image_count": len(images), "annotation_count": len(annotations),
        "class_counts": dict(Counter(labels.values())),
        "center_class_counts": {c: dict(v) for c, v in sorted(centers.items())},
        "joins": {"image_ids_missing_file": sorted(set(ids) - set(image_names)),
                  "image_files_missing_row": sorted(set(image_names) - set(ids)),
                  "tumor_ids_missing_annotation": sorted(tumor_ids - set(annotation_ids)),
                  "annotation_ids_without_tumor": sorted(set(annotation_ids) - tumor_ids)},
        "exact_duplicates": {"groups": duplicates,
                             "pair_count": sum(len(g) * (len(g) - 1) // 2 for g in duplicates),
                             "conflicting_label_groups": [g for g in duplicates if len({labels.get(n) for n in g}) > 1],
                             "cross_center_groups": [g for g in duplicates if len({str(by_id.get(n, {}).get("center")) for n in g}) > 1]},
        "annotations": {"shape_types": dict(shapes), "labels": dict(annotation_labels),
                        "invalid_json_or_structure": bad_json, "image_path_mismatch": bad_paths,
                        "subtype_label_sets_checked": subtype_checked,
                        "subtype_label_set_mismatch": subtype_mismatches},
        "split_lists": _split_audit(train_list, validation_list, ids, duplicates),
        "exif": {"checked": inspect_exif, "tag_presence_counts": dict(exif_counts),
                 "nonempty_raw_tag_counts": dict(exif_nonempty), "values_exported": False},
        "ready_for_training": False, "patient_grouping_verified": False,
        "reference_standard_verified": False, "medical_validation_established": False,
        "limitations": ["No patient or lesion identity is inferred from metadata, hashes or split lists.",
                        "Labels, reference standards, permissions and scientific protocol need independent review.",
                        "Exact-byte checks miss re-encoding, crops, other views and other patient overlap.",
                        "Annotation geometry, pixel privacy and EXIF values are not reviewed."]}
    if include_evidence_rows:
        flags = defaultdict(set)
        for group in duplicates:
            conflict = len({labels.get(n) for n in group}) > 1
            for name in group:
                flags[name].add("exact_duplicate_label_conflict" if conflict else "exact_duplicate_family")
        for mismatch in subtype_mismatches:
            flags[mismatch["image_id"]].add("subtype_label_set_mismatch")
        for name in ids:
            if name not in image_digests:
                flags[name].add("image_file_missing")
            if labels[name] in {"invalid_flags", "conflicting_flags"}:
                flags[name].add(labels[name])
            if Path(name).stem in report["joins"]["tumor_ids_missing_annotation"]:
                flags[name].add("tumor_annotation_missing")
        evidence = []
        for name in sorted(ids):
            source = by_id[name]
            row = {column: "" for column in EVIDENCE_COLUMNS}
            row.update(image_id=name, center=str(source["center"]).strip().removesuffix(".0"),
                       sha256=image_digests.get(name, ""), review_status="unreviewed",
                       review_flags=";".join(sorted(flags[name])))
            for column in ("tumor", "benign", "malignant"):
                value = str(source[column]).strip().lower()
                row[column] = {"0": "0", "0.0": "0", "false": "0",
                               "1": "1", "1.0": "1", "true": "1"}.get(value, "")
            evidence.append(row)
        report["evidence_rows"] = evidence
    return report


def prepare_btxrd_evidence_template(path, *, expected_md5=None):
    """Measured file identities with blank custodian evidence; no cohort or groups."""
    report = audit_btxrd_release(path, expected_md5=expected_md5, include_evidence_rows=True)
    if not report["evidence_rows"]:
        raise ValueError("Cannot prepare an evidence template from empty metadata")
    if any(row["center"] not in {"1", "2", "3"} for row in report["evidence_rows"]):
        raise ValueError("Evidence template requires original BTXRD centers 1, 2 or 3")
    return report["evidence_rows"]
