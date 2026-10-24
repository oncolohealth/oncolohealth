# Offline BTXRD release and evidence review candidate

This is an unmerged integration candidate against main `c13a74a15fdd636249899a587a239cb000107e6d`. It ports the independently checked local archive/evidence utilities into the shared package without changing model training, evaluation, scoring, registry state or acquisition code. The new modules are `datasets/release_audit.py`, `datasets/evidence.py` and `datasets/btxrd_review.py`.

## Local commands

```sh
python3 -B -m cancer_workbench btxrd-review audit BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df
python3 -B -m cancer_workbench btxrd-review template BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df > evidence-template.csv
python3 -B -m cancer_workbench btxrd-review check BTXRD.zip evidence-template.csv --expected-md5 59132a5036d030580ccade8add8f13df
```

The paths are placeholders for already-local files. These commands make no network request, extract no images, create no partitions, and do not launch or train a model. A completed audit/check returns a structured report even when its status is `blocked`; exit code zero does not establish scientific eligibility. The audit additionally accepts paired `--train-list` / `--validation-list` CSV/XLSX files. Optional `--inspect-exif` uses Pillow to count tags without returning their values. The core remains standard-library only.

The [original Figshare record](https://api.figshare.com/v2/articles/27865398) supplies the release MD5. The [source paper](https://www.nature.com/articles/s41597-024-04311-y) permits different views of one lesion and describes mixed diagnostic-reference methods. Neither a file checksum nor complete declared text establishes patient identity or label truth.

## Behavior and boundaries

- The archive audit checks CRC/digests, XLSX/CSV structure, exact-byte image families, table/image/annotation joins, annotation subtype-label sets and optional source split lists. It rejects unsafe paths, ambiguous IDs and spreadsheet formulas. Limits are 50,000 archive members, 2 GB uncompressed content and 20 MB per table/annotation/EXIF input.
- The template contains source IDs/flags and measured image hashes; all patient, lesion and diagnostic-reference fields start blank. Review flags are advisory and never filter records automatically. Image pixels, demographics, EXIF values and local input paths are omitted.
- The return checker detects source-field/hash/coverage drift, incomplete evidence/review status, exact-copy patient conflicts and source-label conflicts inside one declared lesion. It returns no supplied patient IDs or reference values. Complete declarations reach only `declared_evidence_requires_review`; all patient/medical/training-readiness attestations remain false.
- The existing shared manifest importer and audit remain the canonical dataset path. A synthetic bridge test confirms that blank patient IDs from the template still fail that audit. This candidate does not import the separate foundation's split planner, alter the shared manifest schema, or automatically insert reviewed evidence into training.

## Verification

The combined suite discovers 131 synthetic software tests: 117 pass and 14 skip in plain Python; 118 pass and 13 skip with optional Pillow available. The 25 added tests cover archive/evidence behavior and the shared missing-patient audit boundary. Optional ML/Torch checks remain skipped in this environment. Catalog validation still reports 16 models and 14 datasets.

The candidate's `check` command was also run on the already-local original release and 3,746-row evidence template. Its result is checked against the earlier independent foundation report: source fields/hashes match, every patient/lesion/reference field remains missing, the four contradictory exact-copy labels remain blockers, and no cohort is created. No image-model training, model-weight acquisition, cluster workload, medical-performance reproduction or clinical validation was performed.

The original release has 21 exact duplicate pairs, two contradictory label pairs, seven exact pairs crossing the authors' public classification split lists, 27 split-list extension mismatches, and a subtype-label-set difference at IMG001276.jpeg. These independent offline findings do not replace custodian grouping evidence or diagnostic-reference review. The source images' privacy/rights review remains open; this candidate contains no image export.

## Review before merge

Review the new modules and CLI schema, reconcile with any newer main or unpushed team branch, rerun the required environment checks, and keep the team hub's candidate status aligned with PROGRESS. No catalog promotion or medical eligibility follows from merging this utility. Patient/lesion mapping, per-row reference evidence, endpoint/protocol approval, label adjudication and an independent test plan remain open.
