# BTXRD model-folder provenance repair

A local repair candidate now addresses one defect from the [baseline input review](BTXRD-baseline-input-review.md): an encoder using a custom model directory previously reported revision metadata from the default directory. The [patch](BTXRD-model-provenance-fix.patch) reads that metadata from the adapter's configured model root. The [verification manifest](BTXRD-model-provenance-fix.json) records source/patch hashes, exact changed files and checks.

The target is inspected shared commit `c13a74a15fdd636249899a587a239cb000107e6d`. Shared main and Inam's unavailable unpushed branch were not changed or independently reconciled. This is an unmerged source candidate, ready for receiving-branch review.

## Resulting behavior

- Existing calls without a custom root retain their default-folder behavior.
- Calls with a custom root use that folder's encoder subdirectory for revision metadata, matching the configured loading root.
- Missing custom provenance returns unknown (`None`), even when the default folder has a revision. No identity is borrowed.
- Malformed custom JSON raises before an embedding call.

The patch changes the adapter helper/result path, adds nine regression tests and includes candidate progress/report notes. It does not change preprocessing, cache identity, fitting, scoring, catalog eligibility or evidence promotion. A provenance file remains an assertion: the repair does not authenticate actual weight bytes or establish permissions or scientific validity.

## Verification actually performed

| Check | Result |
|---|---|
| Nine new regression tests against original source | One passes; three assertions fail and five calls error as expected, demonstrating sensitivity to the old behavior/API |
| Standalone candidate suite, plain Python | 115 discovered: 102 pass, 13 optional ML checks skip; no failures/errors |
| Combined with the earlier audit/evidence patch, with Pillow | 140 discovered: 127 pass, 13 optional ML checks skip; no failures/errors |
| Catalog | 16 models and 14 datasets validate |
| Fresh patch application | Whitespace/apply checks pass; the applied copy equals the tested candidate byte-for-byte |
| Patch compatibility | This patch and the [earlier audit/evidence patch](BTXRD-shared-integration.md) apply in either order to the inspected base and produce identical source trees |
| Full ML/Torch execution, actual weight loading, inference and medical validation | Not performed |

The new tests use temporary synthetic provenance files and mocked embedding vectors. No medical images or weights were acquired/read, no model inference or training was run, and no cluster resources were used. The combined 140-test discovery includes the original shared tests, 25 earlier audit/evidence tests and nine new provenance tests; it is not an additional independent medical result or the foundation's separate 72-test suite.

## Review and apply

Inspect the receiving checkout and reconcile any team changes first. Do not force this patch over another branch's adapter or progress edits. From a compatible checkout, with the patch at the placeholder path:

```sh
git apply --check --whitespace=error BTXRD-model-provenance-fix.patch
git apply --whitespace=error BTXRD-model-provenance-fix.patch
python3 -B -m unittest discover -s tests -q
python3 -B -m cancer_workbench catalog validate
```

The apply checks and both patch orders were verified against the stated base, not the unavailable team branch. Complete the full supported dependency/runtime checks before merge or real execution.

A separate [image-binding repair candidate](BTXRD-feature-cache-fix.md) now addresses source-image/hash consistency and legacy-cache refusal across all cache readers. Both repairs remain local/unmerged. Actual model/processor authentication, receiving-branch reconciliation and full ML checks remain open. Patient/lesion grouping, per-row diagnostic reference standards, contradictory-label adjudication and an agreed independent evaluation protocol remain scientific blockers. These repairs do not make BTXRD training-ready.
