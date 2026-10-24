# Declared identity formatting guard

Sample, patient and duplicate-group tokens differing only in surrounding whitespace could bypass the dataset audit's declared-overlap checks at `e22234c8cf1356a4845e8f60da76fc2f8434d627`. The public head preflight accepted equivalent formatting aliases in its identity channels. Whitespace-only patient values could also count as patients and produce audit readiness. This finding used synthetic records; it does not establish that medical data or earlier scores were affected.

The integrated guard refuses ambiguous formatting rather than rewriting identities. The audit reports `invalid_identity`, blocks readiness and excludes whitespace-only or padded patient tokens from patient counts. The head validator rejects surrounding whitespace in `sample_ids`, `patient_ids`, `group_ids`, `duplicate_groups` and `image_hashes`. Internal spaces and case are preserved. Empty optional identities remain unknown, exact declared overlap still fails, and the audit's existing partial-missing-patient policy is unchanged.

The change is limited to `datasets/audit.py`, `learning/heads.py` and ten synthetic regressions in `tests/test_identity_whitespace.py`. The shared manifest contract, UI, planner, coordinator, model/processor provenance and cache consumers are unchanged. The three files match the reviewed isolated candidate byte-for-byte. Original patch and candidate verification records remain historical artifacts.

## Verification

In the existing bundled Python 3.12.14 environment with NumPy 2.3.5 and Pillow 12.3.0:

```sh
python -B -m unittest discover -s tests -p test_identity_whitespace.py -v
python -B -m unittest discover -s tests -q
python -B -m cancer_workbench catalog validate
git diff --check
```

All **10 targeted tests pass**. The combined suite discovers **253 tests: 213 pass, 40 optional ML skips**. Catalog: 16 models and 14 datasets valid. The final whitespace check passes. These are synthetic software checks, with no medical pixels, weights, actual model inference, training, acquisition or cluster run. NumPy arrays exercise the public head preflight without constructing a learner.

## Supported-runtime verification path

Read-only inventory found no repository `.venv`. System Python has none of the checked ML packages. The existing research imaging environment has Pillow 13.0.0 but no NumPy, scikit-learn or Torch. The bundled environment has NumPy/Pillow, but lacks scikit-learn, Torch, TorchVision, timm, Transformers and safetensors. Its NumPy version also differs from the repository's pinned `ml` extra. Package discovery is not proof that imports, binary operators or model loading work. Exact inventory and source hashes are in [the verification record](../research-handoff/identity-guard-integration.json).

1. In an existing approved environment, compare installed versions with `pyproject.toml` and verify required imports and Torch/TorchVision operators offline. Record mismatches and failures. No installation, download or repair is implied by this checklist.
2. Run the targeted identity checks and combined synthetic suite there once. Record pass/fail/skip totals and skip reasons; require the intended scikit-learn/Torch tests to execute before calling the supported ML path verified. Revalidate the catalog. Keep these results separate from other contributors' reports.
3. Treat real artifact authentication/loading and any tiny extraction/fitting run as a separate milestone requiring specific human execution authorization. Bind actual permitted model/processor/source identities, freeze the protocol and resource scope, and verify logs, checkpoint destinations and cancellation before dispatch.

Patient/lesion identity, diagnostic references, contradictory-label adjudication, protocol review and permissions remain independent evidence requirements. A formatting guard does not authenticate declarations or establish patient-independent performance. Experiments drafts remain non-authorizing.

## Publication boundary

The browser and authenticated desktop fetch show that a teammate merged PR #1 and remote main now equals `e22234c`. That external team action supersedes the earlier draft/unmerged status. This work adds a review commit on the research branch; it performs no merge or history rewrite. Git and the connected services retain required commit identity/times and managed edit history; optional author/tool/machine metadata is omitted from new report content.
