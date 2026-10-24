"""Subset fetches: selection rules, source listers, provenance merging. All fixtures are SYNTHETIC."""
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from cancer_workbench.acquisition import fetch as fetch_mod
from cancer_workbench.acquisition import sources, subsets
from cancer_workbench.acquisition.sources import AccessError, FilePlan, Listing, Unit
from cancer_workbench.app import api
from cancer_workbench.registry.schema import validate_dataset
from helpers import LocalServer


def _units(groups: dict[str, int]) -> Listing:
    """SYNTHETIC listing: group -> number of units, each a 3-byte file."""
    units = []
    for g, n in groups.items():
        for i in range(n):
            units.append(Unit(id=f"{g}-u{i}", group=g, plans=[FilePlan(url=f"http://x/{g}/{i}", relpath=f"{g}/{i}.bin", size=3, group=g)]))
    return Listing(units)


class SelectionTests(unittest.TestCase):
    SUB = {"unit": "patient"}

    def test_parse_rejects_bad_input(self):
        for raw in ({"mode": "sample", "count": 0}, {"mode": "sample", "count": True}, {"mode": "ids", "ids": []},
                    {"mode": "ids", "ids": [""]}, {"mode": "everything"}, {"mode": "sample", "count": 1, "extra": 1}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                subsets.parse_selection(raw, self.SUB)

    def test_query_only_where_the_record_allows_it(self):
        with self.assertRaises(ValueError):
            subsets.parse_selection({"mode": "sample", "count": 1, "query": "x"}, self.SUB)
        sel = subsets.parse_selection({"mode": "sample", "count": 1, "query": " x "}, {"unit": "patient", "query": True})
        self.assertEqual(sel.query, "x")

    def test_sample_takes_whole_groups_deterministically(self):
        lst = _units({"P1": 2, "P2": 1, "P3": 3, "P4": 1})
        root = Path(tempfile.mkdtemp())
        sel = subsets.parse_selection({"mode": "sample", "count": 2, "seed": 3}, self.SUB)
        a, sa = subsets.choose(lst, sel, root)
        b, sb = subsets.choose(lst, sel, root)
        self.assertEqual([u.id for u in a], [u.id for u in b])
        self.assertEqual(len(sa["groups"]), 2)
        for g in sa["groups"]:  # every unit of a chosen group comes along
            self.assertEqual(sum(u.group == g for u in a), sum(u.group == g for u in lst.units))

    def test_sample_skips_groups_on_disk_and_continues_the_order(self):
        lst = _units({f"P{i}": 1 for i in range(6)})
        root = Path(tempfile.mkdtemp())
        all_six, _ = subsets.choose(lst, subsets.parse_selection({"mode": "sample", "count": 6, "seed": 1}, self.SUB), root)
        order = [u.group for u in all_six]
        first, _ = subsets.choose(lst, subsets.parse_selection({"mode": "sample", "count": 2, "seed": 1}, self.SUB), root)
        for u in first:
            (root / u.plans[0].relpath).parent.mkdir(parents=True, exist_ok=True)
            (root / u.plans[0].relpath).write_bytes(b"abc")
        more, summary = subsets.choose(lst, subsets.parse_selection({"mode": "sample", "count": 2, "seed": 1}, self.SUB), root)
        self.assertEqual([u.group for u in first + more], order[:4])
        self.assertEqual(summary["skipped_on_disk"], 2)
        _, summary = subsets.choose(lst, subsets.parse_selection({"mode": "sample", "count": 9, "seed": 1}, self.SUB), root)
        self.assertEqual(summary["short_by"], 5)

    def test_ids_match_groups_or_units_and_reject_unknown(self):
        lst = _units({"P1": 2, "P2": 1})
        root = Path(tempfile.mkdtemp())
        units, summary = subsets.choose(lst, subsets.parse_selection({"mode": "ids", "ids": ["P1", "P2-u0"]}, self.SUB), root)
        self.assertEqual(sorted(u.id for u in units), ["P1-u0", "P1-u1", "P2-u0"])
        self.assertEqual(summary["groups"], ["P1", "P2"])
        with self.assertRaisesRegex(ValueError, "not in this source: nope"):
            subsets.choose(lst, subsets.parse_selection({"mode": "ids", "ids": ["P1", "nope"]}, self.SUB), root)

    def test_population_hash_changes_with_the_listing(self):
        self.assertNotEqual(subsets.population_sha256(_units({"P1": 1}).units), subsets.population_sha256(_units({"P1": 2}).units))


class ListerTests(unittest.TestCase):
    def setUp(self):
        subsets._cache.clear()

    def test_tcia_filters_modality_and_groups_by_regex(self):
        series = [
            {"SeriesInstanceUID": "1.1", "PatientID": "Calc-Test_P_00038_LEFT_CC", "Modality": "MG", "FileSize": 100, "ImageCount": 1},
            {"SeriesInstanceUID": "1.2", "PatientID": "Calc-Test_P_00038_LEFT_CC_1", "Modality": "MG", "FileSize": 50},
            {"SeriesInstanceUID": "1.3", "PatientID": "Mass-Train_P_00001_LEFT_MLO", "Modality": "SEG", "FileSize": 5},
        ]
        acq = {"collection": "X", "extract": True, "subset": {"unit": "patient", "modalities": ["MG"], "group_regex": r"P_\d{5}"}}
        with mock.patch.object(sources, "_get_json", return_value=series):
            lst = sources.units_tcia(acq)
        self.assertEqual([(u.id, u.group) for u in lst.units], [("1.1", "P_00038"), ("1.2", "P_00038")])
        plan = lst.units[0].plans[0]
        self.assertEqual((plan.size, plan.approx_size, plan.integrity), (None, 100, "trust_on_first_use"))
        with mock.patch.object(sources, "_get_json", return_value=series), self.assertRaisesRegex(AccessError, "choose a subset"):
            sources.resolve_tcia({"collection": "X"})

    def test_remaining_bytes_counts_the_extracted_copy_of_estimates(self):
        plans = [FilePlan(url="u", relpath="a.zip", extract=True, approx_size=100), FilePlan(url="u", relpath="b", size=7)]
        with mock.patch.object(fetch_mod, "target_dir", return_value=Path(tempfile.mkdtemp())):
            self.assertEqual(fetch_mod.remaining_bytes({"acquisition": {}}, plans), 207)

    def test_gdc_refuses_filters_without_open_access(self):
        with self.assertRaisesRegex(AccessError, "access = open"):
            sources.units_gdc({"filters": {"op": "and", "content": []}})

    def test_gdc_keeps_only_open_files_and_groups_by_case(self):
        payload = {"data": {"pagination": {"total": 2}, "hits": [
            {"file_id": "f1", "file_name": "a.svs", "file_size": 10, "md5sum": "0" * 32, "access": "open", "cases": [{"submitter_id": "C1"}]},
            {"file_id": "f2", "file_name": "b.svs", "file_size": 10, "md5sum": "0" * 32, "access": "controlled", "cases": [{"submitter_id": "C2"}]},
        ]}}
        acq = {"filters": {"op": "and", "content": [{"op": "=", "content": {"field": "access", "value": "open"}}]}}
        with mock.patch.object(sources, "_get_json", return_value=payload):
            lst = sources.units_gdc(acq)
        self.assertEqual([(u.id, u.group) for u in lst.units], [("a.svs", "C1")])
        self.assertEqual(lst.units[0].plans[0].url, f"{sources.GDC_API}/data/f1")

    def _isic_page(self, results, count=None, next_url=None):
        return {"count": count, "next": next_url, "results": results}

    def _isic_img(self, iid, lic, clinical=None):
        return {"isic_id": iid, "copyright_license": lic, "metadata": {"clinical": clinical or {}},
                "files": {"full": {"url": f"https://isic-archive.s3.amazonaws.com/images/{iid}.jpg", "size": 9}}}

    def test_isic_enforces_licenses_paginates_and_groups(self):
        pages = {
            "first": self._isic_page([self._isic_img("ISIC_1", "CC-0", {"patient_id": "IP_9"}), self._isic_img("ISIC_2", "CC-BY-NC")],
                                     count=3, next_url=f"{sources.ISIC_API}/images/search/?cursor=abc"),
            "second": self._isic_page([self._isic_img("ISIC_3", "CC-BY", {"lesion_id": "IL_4"})]),
        }
        calls = []

        def fake(url, headers=None):
            calls.append(url)
            return pages["second" if "cursor=" in url else "first"]

        acq = {"licenses": ["CC-0", "CC-BY"], "query": "diagnosis_1:Malignant", "subset": {"unit": "patient", "query": True}}
        with mock.patch.object(sources, "_get_json", side_effect=fake):
            lst = sources.units_isic(acq, "age_approx:60")
        self.assertEqual([(u.id, u.group) for u in lst.units], [("ISIC_1", "IP_9"), ("ISIC_3", "IL_4")])
        self.assertIn("age_approx", calls[0])
        self.assertEqual([p.relpath for p in lst.units[0].plans], ["images/ISIC_1.jpg", "metadata/ISIC_1.json"])

    def test_isic_refuses_large_searches_and_off_host_pages(self):
        acq = {"licenses": ["CC-0"], "subset": {"unit": "patient", "max_listing": 10}}
        with mock.patch.object(sources, "_get_json", return_value=self._isic_page([], count=11)), self.assertRaisesRegex(AccessError, "listing cap"):
            sources.units_isic(acq)
        with mock.patch.object(sources, "_get_json", return_value=self._isic_page([], count=1, next_url="https://evil.example/x")), \
                self.assertRaisesRegex(AccessError, "off the API host"):
            sources.units_isic(acq)

    def test_s3_reads_listing_checksums_and_companions(self):
        listing = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated>
<Contents><Key>D/README.md</Key><Size>5</Size></Contents>
<Contents><Key>D/images/tumor_001.tif</Key><Size>100</Size></Contents>
<Contents><Key>D/images/normal_001.tif</Key><Size>90</Size></Contents>
<Contents><Key>D/annotations/tumor_001.xml</Key><Size>7</Size></Contents>
<Contents><Key>D/checksums.md5</Key><Size>40</Size></Contents></ListBucketResult>"""
        sums = b"abc *images/tumor_001.tif\ndef *README.md\n"

        @contextmanager
        def fake_open(url, headers=None):
            yield io.BytesIO(sums if url.endswith("checksums.md5") else listing)

        acq = {"bucket": "b", "region": "r", "prefix": "D/", "units_prefix": "images/", "checksums": "checksums.md5",
               "companions": ["annotations/{stem}.xml"], "shared": ["README.md", "missing.txt"]}
        with mock.patch.object(sources, "open_url", fake_open):
            lst = sources.units_s3(acq)
        by_id = {u.id: u for u in lst.units}
        self.assertEqual(sorted(by_id), ["normal_001", "tumor_001"])
        self.assertEqual([p.relpath for p in by_id["tumor_001"].plans], ["images/tumor_001.tif", "annotations/tumor_001.xml"])
        self.assertEqual((by_id["tumor_001"].plans[0].md5, by_id["normal_001"].plans[0].integrity), ("abc", "size_only"))
        self.assertEqual([p.relpath for p in lst.shared], ["README.md"])


class SubsetFetchTests(unittest.TestCase):
    """End to end against a local server: plan, fetch, then fetch more into the same record."""

    def setUp(self):
        subsets._cache.clear()
        self.srv = LocalServer({f"/{g}": f"SYNTHETIC-{g}".encode() for g in ("P1", "P2", "P3", "P4")})
        self.root = Path(tempfile.mkdtemp())
        listing = Listing(
            [Unit(id=f"{g}-s", group=g, plans=[FilePlan(url=f"{self.srv.url}/{g}", relpath=f"{g}/s.bin", size=len(f"SYNTHETIC-{g}"),
                                                          integrity="size_only", group=g)]) for g in ("P1", "P2", "P3", "P4")],
            shared=[FilePlan(url=f"{self.srv.url}/P1", relpath="README", integrity="size_only")])
        self.record = {"id": "synthetic-subset", "_kind": "dataset", "name": "SYNTHETIC", "license": {"id": "none"},
                       "acquisition": {"tier": "optional", "fetcher": "fake", "subset": {"unit": "patient", "required": True},
                                       "supporting": [{"url": f"{self.srv.url}/P2", "relpath": "labels/table.csv", "size": len("SYNTHETIC-P2")}]}}
        self.patches = [mock.patch.dict(sources.LISTERS, {"fake": lambda acq, query=None: listing}),
                        mock.patch.object(fetch_mod, "target_dir", return_value=self.root)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.srv.close()

    def _get(self, sel):
        row = fetch_mod.plan([self.record], {self.record["id"]: sel})[0]
        self.assertIsNone(row["error"])
        fetch_mod.fetch(self.record, row["plans"], quiet=True, selection=row["selection"])
        return row

    def test_required_subset_blocks_a_plain_plan(self):
        self.assertIn("subset", fetch_mod.plan([self.record])[0]["error"])

    def test_second_sample_adds_new_patients_and_provenance_accumulates(self):
        first = self._get({"mode": "sample", "count": 2, "seed": 5})
        second = self._get({"mode": "sample", "count": 1, "seed": 5})
        self.assertFalse(set(first["selection"]["groups"]) & set(second["selection"]["groups"]))
        prov = json.loads((self.root / "PROVENANCE.json").read_text())
        paths = {f["path"] for f in prov["files"]}
        self.assertEqual(paths, {"README", "labels/table.csv"} | {f"{g}/s.bin" for g in first["selection"]["groups"] + second["selection"]["groups"]})
        self.assertEqual([s["mode"] for s in prov["selections"]], ["sample", "sample"])
        self.assertEqual(prov["selections"][1]["skipped_on_disk"], 2)
        self.assertEqual(prov["selections"][0]["seed"], 5)
        self.assertTrue(all(f.get("group") for f in prov["files"] if f["path"] not in ("README", "labels/table.csv")))

    def test_supporting_files_come_with_ids_and_whole_fetches(self):
        row = fetch_mod.plan([self.record], {self.record["id"]: {"mode": "ids", "ids": ["P3"]}})[0]
        self.assertEqual([p.relpath for p in row["plans"]], ["labels/table.csv", "README", "P3/s.bin"])
        self.assertEqual(row["plans"][0].integrity, "size_only")
        whole = {"fetcher": "url", "files": [{"url": "https://x/a", "relpath": "a"}], "supporting": [{"url": "https://x/b", "relpath": "b", "size": 1}]}
        self.assertEqual([p.relpath for p in sources.resolve(whole)], ["a", "b"])

    def test_api_plan_validates_subset_keys(self):
        with self.assertRaises(api.ApiError):
            api._subsets({"subsets": {"other": {}}}, ["synthetic-subset"])
        self.assertEqual(api._selection_brief({"groups": ["P1"], "units": ["a", "b"]}), {"groups": ["P1"], "unit_count": 2})


class SchemaTests(unittest.TestCase):
    BASE = {"id": "x", "name": "x", "license": {}, "access": "open", "evidence_state": "cataloged", "citation": "",
            "modality": [], "anatomy": [], "counts": {}, "labels": {}}

    def errs(self, acq):
        return validate_dataset({**self.BASE, "acquisition": acq})

    def test_subset_rules(self):
        self.assertEqual(self.errs({"tier": "optional", "fetcher": "tcia", "subset": {"unit": "patient", "required": True}}), [])
        self.assertTrue(self.errs({"tier": "default", "fetcher": "tcia", "subset": {"unit": "patient", "required": True}}))
        self.assertTrue(self.errs({"tier": "optional", "fetcher": "url", "subset": {"unit": "file"}}))
        self.assertTrue(self.errs({"tier": "optional", "fetcher": "tcia", "subset": {"unit": "series"}}))
        self.assertTrue(self.errs({"tier": "optional", "fetcher": "isic", "subset": {"unit": "patient"}}))
        gdc = {"tier": "optional", "fetcher": "gdc", "subset": {"unit": "patient", "required": True}, "filters": {"content": []}}
        self.assertTrue(any("access = open" in e for e in self.errs(gdc)))

    def test_supporting_rules(self):
        ok = {"url": "https://x/a.csv", "relpath": "labels/a.csv", "size": 3}
        self.assertEqual(self.errs({"tier": "optional", "fetcher": "url", "files": [], "supporting": [ok]}), [])
        for bad in ({**ok, "url": "http://x/a.csv"}, {**ok, "relpath": "../a.csv"}, {**ok, "relpath": "/etc/a"}, {**ok, "size": None}, "a.csv"):
            with self.subTest(bad=bad):
                self.assertTrue(self.errs({"tier": "optional", "fetcher": "url", "files": [], "supporting": [bad]}))


if __name__ == "__main__":
    unittest.main()
