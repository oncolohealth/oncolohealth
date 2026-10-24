# BTXRD shared-code integration candidate

The offline archive/evidence utilities are now prepared as a [reviewable patch](BTXRD-shared-integration.patch) for the shared repository. The [verification manifest](BTXRD-shared-integration.json) records the exact file hashes, patch hash, checks performed and unmerged status. This consolidates the useful local work without creating another evaluation implementation.

The target is the inspected `oncolohealth/oncolohealth` source snapshot at `c13a74a15fdd636249899a587a239cb000107e6d`. The shared repository and Inam's reported unpushed `codex/demo-readiness` branch were not modified. That branch was not available for independent inspection here; its changes may need reconciliation before this patch is applied to a newer base.

## What the patch adds

- Read-only release auditing in `datasets/release_audit.py`: archive integrity, actual XLSX/CSV metadata, image/annotation joins, exact-copy label conflicts, subtype-label sets, optional source split lists and optional EXIF tag counts.
- Evidence collection and return checks in `datasets/evidence.py`: measured image hashes, blank patient/lesion/reference fields, source-record binding, completeness and consistency findings. Supplied patient IDs and reference values are omitted from reports.
- A separate `btxrd-review audit|template|check` command and 25 synthetic tests. The existing manifest/audit path is reused for the missing-patient boundary rather than importing the local foundation's split planner.
- A scoped source report and candidate-only progress/architecture notes. The patch does not change training, evaluation, scoring, acquisition, model catalog records, dependencies or evidence-state promotion.

No medical images, datasets, model weights, private identity/reference values, authoring timestamps or absolute local paths are embedded in the patch.

## Verification actually performed

| Check | Result and limit |
|---|---|
| Combined candidate suite, plain Python | 131 discovered: 117 pass, 14 optional checks skip; no failures |
| Combined candidate suite with Pillow | 131 discovered: 118 pass, 13 optional ML checks skip; no failures |
| Catalog | Still validates at 16 models and 14 datasets; catalog contents unchanged |
| Real local release/evidence check | All 3,746 rows match source fields and measured hashes. The JSON result is exactly equal to the canonical [foundation check report](BTXRD-evidence-check.json), including its blocked state |
| Patch application | Clean whitespace/apply check against the base snapshot; applying to a fresh copy reproduces the tested candidate byte-for-byte |
| Full ML/Torch environment, GPU inference and model training | Not performed |
| Patient-independent or medical validation | Not established |

The original [foundation's 72-test verification](complete-source-handoff.zip) remains a separate result. The candidate's 131-test suite is the shared snapshot's 106 tests plus 25 ported tests; these counts must not be added together or presented as medical evidence.

## Review and apply locally

First compare the receiving repository state with the target above. For another commit or an unmerged team branch, review/rebase the patch rather than forcing it over conflicting work. From the receiving checkout, with the patch available at the placeholder path:

```sh
git apply --check --whitespace=error BTXRD-shared-integration.patch
git apply --whitespace=error BTXRD-shared-integration.patch
python3 -B -m unittest discover -s tests -q
python3 -B -m cancer_workbench catalog validate
```

These apply checks were verified against the inspected source snapshot. No remote publication or merge was performed. Review the new CLI/input contract and run the full supported dependency environment before merging.

The new offline commands, after review/application, are:

```sh
python3 -B -m cancer_workbench btxrd-review audit BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df
python3 -B -m cancer_workbench btxrd-review template BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df > evidence-template.csv
python3 -B -m cancer_workbench btxrd-review check BTXRD.zip evidence-template.csv --expected-md5 59132a5036d030580ccade8add8f13df
```

Inputs are already-local files. A completed command can return exit code zero with a `blocked` report; evaluate its explicit findings and readiness fields. It never downloads, extracts, submits, trains, splits a cohort, accepts terms or promotes a specialist. The [evidence handoff](BTXRD-evidence-handoff.md) and [readiness record](BTXRD-readiness.md) explain the scientific gaps and the [original release checksum](https://api.figshare.com/v2/articles/27865398).

Patient/lesion grouping, per-row diagnostic references, contradictory-label adjudication, endpoint/protocol review and a defensible independent test remain unresolved. Merging an offline utility would not resolve any of those evidence requirements.
