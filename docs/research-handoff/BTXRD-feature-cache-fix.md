# BTXRD feature-cache image binding repair

A local repair candidate now detects changed source-image bytes before cached features are reused. It addresses the cache defect reproduced in the [baseline input review](BTXRD-baseline-input-review.md), across baseline fitting, source-shift experiments, near-duplicate ranking and legacy head rebuilding. The [patch](BTXRD-feature-cache-fix.patch) and [verification manifest](BTXRD-feature-cache-fix.json) are ready for receiving-branch review.

The target is inspected shared commit `c13a74a15fdd636249899a587a239cb000107e6d`. The patch remains local, unpushed and unmerged. The team's newer unpushed branch has not been supplied or independently inspected here; compatibility with that branch is not established.

## What changes

- **New caches record input identity.** Measured image SHA-256 values are aligned with unique sample IDs, with a functional binding schema and a canonical mapping digest. Declared manifest hashes must agree with actual bytes. Where a declaration is absent, the measured bytes can still bind the cache, without establishing curated source provenance.
- **Every existing cache reader checks it.** The baseline, source-shift experiment, near-duplicate ranker and legacy head-rebuild path reject old caches lacking bindings, changed images, mismatched IDs/hashes, malformed shapes and inconsistent declared encoder/revision/variant/preprocessing identities before fitting or ranking. Unknown encoder revision is refused.
- **Failed extraction preserves prior output.** Source bytes are measured before and after the encoder call. Detected persistent changes, invalid feature arrays or write failures prevent publication. A temporary NPZ replaces the target only after writing succeeds.
- **Unchanged pixels remain reusable.** Manifest row order may change without breaking ID alignment. Labels, groups and partitions come from the current manifest; editing them alone need not recompute embeddings. Their correctness and scientific eligibility still require review.

Cache names remain locators, not proof of input identity. An unbound existing cache now fails with a recomputation requirement; that refusal does not itself run an encoder or authorize a new job. The patch does not acquire files or change specialist eligibility, study endpoints, model-selection policy or catalog state.

## Verification actually performed

| Check | Result |
|---|---|
| New targeted tests, NumPy available | 20 pass; synthetic byte files, mocked embeddings and actual NPZ I/O |
| Standalone candidate, plain Python | 126 discovered: 107 pass, 19 optional checks skip |
| Standalone candidate, NumPy available | 126 discovered: 115 pass, 11 optional ML checks skip |
| All three local patches, plain Python | 160 discovered: 140 pass, 20 optional checks skip |
| All three local patches, NumPy and Pillow available | 160 discovered: 149 pass, 11 optional ML checks skip |
| Refusal timing | All four consumers reject both stale and legacy caches before fitting/ranking; no automatic extraction occurs for these existing-cache refusals |
| Catalog | 16 models and 14 datasets validate |
| Fresh application | Whitespace/apply checks pass; applied files equal the candidate byte-for-byte |
| Patch composition | This patch, the [audit/evidence patch](BTXRD-shared-integration.md) and the [model-folder provenance patch](BTXRD-model-provenance-fix.md) apply in all six orders to the inspected base and produce identical source trees |

No test failures or errors occurred. The 160-test discovery is 106 shared-source tests plus 25 audit/evidence, nine folder-provenance and 20 input-binding tests. These counts describe a combined local candidate, separate from the foundation's 72 tests and the team's independently reported branch results.

The tests also exercise source/hash drift, missing/duplicate/extra IDs, escaping paths and symlinks, mapping digest inconsistency, feature-row mismatch, identity mismatch, changed inputs during a mocked encoder call, and preservation of existing outputs on embedding/write failure. No medical source files or model weights were read or acquired. No actual image-model inference, model training, cluster compute or external service call was used for these checks.

## Review and apply

Review/rebase against the actual receiving checkout before applying. The verified six-order compatibility applies to the stated inspected base, not arbitrary team branches. With the patch at the placeholder path:

```sh
git apply --check --whitespace=error BTXRD-feature-cache-fix.patch
git apply --whitespace=error BTXRD-feature-cache-fix.patch
python3 -B -m unittest discover -s tests -q
python3 -B -m cancer_workbench catalog validate
```

NumPy enables the NPZ checks; it is not installed or downloaded automatically. Full supported ML/Torch checks are still required before merge or authorized real execution. Previously acquired medical feature caches were not inspected or recomputed in this step.

## Limits and next step

Input hashing is a consistency check. It does not authenticate patient/lesion mappings, diagnostic labels, a cache's claimed origin, permissions or actual weight bytes. Declared revision and preprocessing fields are checked for agreement; the weight files and processor implementation still need independent identity binding. The before/after hash checks do not lock files or rule out every transient edit-and-restoration race. Low-level NPZ reading and direct feature-head APIs remain available, so this is not a security or authorization boundary.

Next software work: reconcile the receiving branch, verify actual weight/configuration identities, and complete the full ML runtime checks. Patient/lesion grouping, per-row diagnostic reference standards, contradictory-label adjudication and an agreed independent evaluation protocol remain scientific blockers. This repair does not make BTXRD training-ready or establish cancer-detection performance.
