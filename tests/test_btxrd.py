import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cancer_workbench.datasets import audit_dataset, btxrd
from cancer_workbench.datasets.xlsx import read_sheet


def _cell(ref, value, shared):
    if value.isdigit():
        return f'<c r="{ref}"><v>{value}</v></c>'
    if value in shared:
        return f'<c r="{ref}" t="s"><v>{shared.index(value)}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path, table):
    """SYNTHETIC workbook: header via shared strings, other text inline, numbers as values."""
    shared = list(table[0])
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rows = "".join(
        f'<row r="{n + 1}">' + "".join(_cell(f"{_col(i)}{n + 1}", v, shared) for i, v in enumerate(r) if v != "") + "</row>"
        for n, r in enumerate(table))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/><sheet name="Sheet2" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{rows}</sheetData></worksheet>")
        z.writestr("xl/worksheets/sheet2.xml", f"<worksheet {ns}><sheetData/></worksheet>")


def row(image_id, tumor, benign, malignant, subtypes=(), site="femur", region="lower limb", view="frontal"):
    r = {c: "0" for c in btxrd.REQUIRED_COLUMNS}
    r.update(image_id=image_id, center="1", age="30", gender="F", tumor=tumor, benign=benign, malignant=malignant)
    for c in (*subtypes, site, region, view):
        r[c] = "1"
    return r


def make_release(root: Path, rows, annotations):
    """SYNTHETIC release with the BTXRD layout. Image bytes are placeholders, not radiographs."""
    (root / "images").mkdir(parents=True)
    (root / "Annotations").mkdir()
    header = list(btxrd.REQUIRED_COLUMNS)
    write_xlsx(root / "dataset.xlsx", [header] + [[r[c] for c in header] for r in rows])
    for r in rows:
        (root / "images" / r["image_id"]).write_bytes(b"synthetic " + r["image_id"].encode())
    for stem, labels in annotations.items():
        (root / "Annotations" / f"{stem}.json").write_text(json.dumps(
            {"version": "5.4.1", "shapes": [{"label": l, "shape_type": "rectangle", "points": [[0, 0], [1, 1]]} for l in labels]}))


ROWS = [
    row("IMG000001.jpeg", "0", "0", "0"),
    row("IMG000002.jpeg", "1", "1", "0", ["osteochondroma"]),
    row("IMG000003.jpg", "1", "0", "1", ["osteosarcoma"]),
    row("IMG000004.jpeg", "1", "1", "1", ["osteochondroma"]),  # contradictory indicators
    row("IMG000005.jpeg", "1", "1", "0", ["osteochondroma", "synovial osteochondroma"]),
]
ANNOTATIONS = {"IMG000002": ["osteochondroma"], "IMG000003": ["osteosarcoma"], "IMG000004": ["osteochondroma"],
               "IMG000005": ["synovial osteochondroma"]}


class BtxrdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_release(self.root, ROWS, ANNOTATIONS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_xlsx_reader_resolves_shared_and_inline_strings(self):
        table = read_sheet(self.root / "dataset.xlsx")
        self.assertEqual(table[0][0], "image_id")
        self.assertEqual(table[3][0], "IMG000003.jpg")
        self.assertEqual(len(table), len(ROWS) + 1)

    def test_describe_release(self):
        d = btxrd.describe_release(self.root)
        self.assertEqual(d["rows"], 5)
        self.assertEqual(d["grouping_columns"], [])
        self.assertEqual(d["files"]["images"], {".jpeg": 4, ".jpg": 1})
        self.assertEqual(d["derived_classes"], {"normal": 1, "benign": 2, "malignant": 1, "quarantined": 1})
        self.assertTrue(all(v == 0 for v in d["id_checks"].values()))
        self.assertIn("label_combination:111", d["flagged_rows"]["IMG000004"])
        self.assertIn("annotation_subtype_mismatch", d["flagged_rows"]["IMG000005"])
        self.assertNotIn("IMG000002", d["flagged_rows"])

    def test_manifest_keeps_contradictions_unlabeled_and_never_invents_patients(self):
        rows = btxrd.build_manifest(self.root)
        by_id = {r["sample_id"]: r for r in rows}
        self.assertEqual([by_id[f"IMG00000{i}"]["label"] for i in (1, 2, 3, 4)], ["normal", "benign", "malignant", ""])
        self.assertTrue(all(r["patient_id"] == "" and r["partition"] == "unassigned" for r in rows))
        self.assertEqual(by_id["IMG000003"]["file"], "images/IMG000003.jpg")
        self.assertEqual(len(by_id["IMG000001"]["sha256"]), 64)
        rep = audit_dataset({"id": "btxrd", "classes": ["benign", "malignant", "normal"]}, rows, files_root=self.root)
        codes = {f["code"] for f in rep["findings"]}
        self.assertIn("missing_patient_id", codes)
        self.assertIn("unknown_label", codes)
        self.assertEqual(rep["file_checks"]["hash_mismatch"], 0)

    def test_exact_duplicates_grouped_and_conflicts_cleared(self):
        img = self.root / "images"
        (img / "IMG000003.jpg").write_bytes((img / "IMG000002.jpeg").read_bytes())  # benign == malignant copy
        rows = {r["sample_id"]: r for r in btxrd.build_manifest(self.root)}
        a, b = rows["IMG000002"], rows["IMG000003"]
        self.assertTrue(a["duplicate_group"] and a["duplicate_group"] == b["duplicate_group"])
        self.assertEqual((a["label"], b["label"]), ("", ""))
        self.assertIn("duplicate_label_conflict", b["audit_flags"])
        self.assertEqual(rows["IMG000001"]["duplicate_group"], "")
        self.assertEqual(btxrd.build_manifest(self.root, hash_files=False)[1]["duplicate_group"], "")

    def test_reviewed_same_image_pairs_join_exact_groups_and_clear_conflicts(self):
        img = self.root / "images"
        (img / "IMG000003.jpg").write_bytes((img / "IMG000002.jpeg").read_bytes())  # exact copy, conflicting labels
        reviewed = self.root / "reviewed.json"
        reviewed.write_text(json.dumps({"same_image": [{"a": "IMG000001", "b": "IMG000002", "evidence": "SYNTHETIC"},
                                                       {"a": "IMG000005", "b": "IMG999999", "evidence": "not in this endpoint"}]}))
        rows = {r["sample_id"]: r for r in btxrd.build_manifest(self.root, reviewed_pairs=reviewed)}
        group = {rows[s]["duplicate_group"] for s in ("IMG000001", "IMG000002", "IMG000003")}
        self.assertEqual(group, {"reviewed:IMG000001+IMG000002+IMG000003"})
        self.assertTrue(all("reviewed_same_image" in rows[s]["audit_flags"] for s in ("IMG000001", "IMG000002", "IMG000003")))
        self.assertEqual(rows["IMG000001"]["label"], "")  # normal joined a benign/malignant group
        self.assertEqual(rows["IMG000005"]["duplicate_group"], "")
        unreviewed = {r["sample_id"]: r for r in btxrd.build_manifest(self.root, reviewed_pairs=None)}
        self.assertEqual(unreviewed["IMG000001"]["duplicate_group"], "")

    def test_endpoints(self):
        tvn = btxrd.build_manifest(self.root, "tumor_vs_normal", hash_files=False)
        self.assertEqual({r["label"] for r in tvn}, {"normal", "tumor", ""})
        bvm = btxrd.build_manifest(self.root, "benign_vs_malignant", hash_files=False)
        self.assertNotIn("IMG000001", {r["sample_id"] for r in bvm})
        self.assertEqual(len(bvm), 4)
        with self.assertRaises(ValueError):
            btxrd.build_manifest(self.root, "cancer_or_not")


if __name__ == "__main__":
    unittest.main()
