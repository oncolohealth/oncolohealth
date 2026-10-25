# Review: `sebastian/encoder-specialist` before merge

Inam Qasimi · October 24, 2026 · reviewed branch tip `b144a9a` against `origin/main` `15d79e2`.
Software review only; nothing here is a medical result.

## For teammates' assistants

- Branch `inam/encoder-specialist-route-fix` sits on top of `sebastian/encoder-specialist`
  `b144a9a`. Merge it into Sebastian's branch, not into `main` on its own; `main` reaches
  both through the encoder-specialist PR.
- It changes `runnable_blockers`, `route_models` and `plan_experiment` to take an
  optional `installed` set. Any new caller that reports whether a model is runnable
  should pass `set(installed_adapters(models))`.
- Verified here: plain-Python suite, catalog validation, `route` and `specialist`
  CLI behaviour without torch or weights. Not verified here: every real-weight result
  in Sebastian's handoff. Do not cite them as reproduced.
- Still open before merge: item 2 (a person confirms the same-image pair) and the
  real-weight rerun.

## Summary

The branch merges cleanly (fast-forward: its base is the current `origin/main` tip and
main has no commits the branch lacks). In plain Python the full suite passes and the
catalog validates. The real-encoder path could not be exercised here, so the
embedding-parity and ML-environment results stay **reported by Sebastian, not
independently reproduced**. Three items should be settled before merging (items 1 and 3 are now
fixed on `inam/encoder-specialist-route-fix`); the rest can follow.

## Checks run here

| Check | `origin/main` 15d79e2 | branch b144a9a |
|---|---|---|
| `python3 -B -m unittest discover -s tests` | 305 run, OK, 48 skipped | 320 run, OK, 49 skipped |
| New/changed suites (`test_specialist_adapters`, `test_curriculum`, `test_btxrd`) | n/a | 20 run, OK, 1 skipped (opt-in real-weight test) |
| `catalog validate` | ok: 16 models, 17 datasets | ok: 16 models, 17 datasets |
| `specialist status` / `specialist run --model rad-dino --image btxrd:IMG000001` | n/a | both adapters reported not installed with reasons; run returns `rejected` and logs to `runs/specialist-calls/` |

Environment: Linux, Python 3.12.3, NumPy 1.26.4, Pillow 10.2.0. No torch, timm,
transformers, safetensors or scikit-learn, and no `models/` or `data/` folders, so the
`CW_MODEL_TESTS=1` test and every real-weight claim were not run.

## Fix before merge

1. **The `route` CLI and the experiment planner report both encoders as runnable where they cannot run.**
   `route_models(..., installed=None)` skips the new installed-adapter check, and two
   callers don't pass it: `cancer_workbench/__main__.py:41` (`route` command) and
   `cancer_workbench/experiments/plan.py:38` (`specialist_tools` path, via
   `runnable_blockers`). Observed on this machine without torch or weights:
   `python -m cancer_workbench route --task feature_extraction --modality xray --anatomy bone`
   prints `rad-dino True []` and `resnet50-a1-in1k True []`. This contradicts the
   handoff's "under plain python3 the router shows both encoders as blocked". The new
   test `test_only_reviewed_models_are_runnable` asserts this default.
   **Fixed on `inam/encoder-specialist-route-fix`:** `runnable_blockers(model, installed)`
   now carries the installed check (`route_models` passes it through). The `route` CLI
   passes `installed_adapters(models)`. `plan_experiment` takes `installed`, and the app's
   experiment preview passes it (the synthetic adapter id in synthetic mode). Calling
   the library functions directly without `installed` still checks the catalog
   declaration only. New regressions: `test_route_cli_blocks_encoders_this_process_cannot_load`
   and `test_specialist_plan_blocks_an_adapter_this_process_cannot_load` (both fail
   without the fix). Suite: 322 run, OK, 49 skipped.

2. **The same-image grouping is applied automatically, but no person has reviewed it yet.**
   `catalog/reviews/btxrd-same-image.json` says the IMG002677/IMG002686 review was done
   "by Claude Code for Sebastian … pending a second human look". The handoff calls it
   "confirmed". `build_manifest` now applies the file by default. A named person
   should confirm the pair and be recorded in the file before merging. Until then,
   default `reviewed_pairs=None`. Also, rebuilding the manifest now changes duplicate
   groups and therefore splits. The presentation's historical baseline figures (0.846 →
   0.616) must keep citing their original run, not a rebuilt manifest.

3. **The README was stale** (fixed on `inam/encoder-specialist-route-fix`, which also brings ARCHITECTURE.md up to date with `adapters/installed.py`, `get_workflow` and the `installed` parameter). `README.md:17` said "no catalog model is cleared to
   run, and the assistant can't call them". After Sebastian's branch, two models are cleared
   for research-use feature extraction and the assistant can call them through
   `run_specialist`. The sentence now says so and names the `specialist` CLI.

## Merge gate (not a code change)

- **Reproduce the real-weight path in a full ML environment** (`uv pip install -e ".[ml]"`,
  fetch both encoders, `CW_MODEL_TESTS=1`). Do this on a second machine (CUDA or CPU,
  not only Sebastian's MPS run). Until then, record the 320/5-skip count, the
  bit-for-bit IMG000001 parity and the opt-in test pass as Sebastian's reported
  results. Merging without this is acceptable if PROGRESS.md and the Hub say so.

## Should fix (can follow the merge)

4. **Team sign-off on the catalog promotion.** Both encoders move from `cataloged`
   straight to `locally_reproduced` with `inference_permission: allowed`. The open
   PROGRESS item to review each `PROVENANCE.json` (`cataloged → access_obtained`) is
   still unchecked. The terms review was written by Sebastian with Claude Code. Per
   PROGRESS.md, evidence states change only through a reviewed PR, so the merging
   reviewer is the sign-off. Record who that is in `terms_review.reviewed`.
5. **Not every specialist call is logged.** `specialist_run` (`app/api.py`) says
   rejections and failures are logged. A tool-level error (bad argument type, unknown
   model id) returns `{"error": …}` with no `run_id`, so it is not written to
   `runs/specialist-calls/`. Log those too, or narrow the docstring.
6. **Each call rehashes the weights.** One call hashes the weights three times: twice in
   `FrozenEncoderAdapter.run` and once in `EncoderSpecialist.run`. For RAD-DINO that is
   about 1 GB of reads (3 × 346 MB). The image is also hashed three or four times
   across validate and run. This is fine for the demo. Later, cache by the stat
   fingerprint that `measured_file` already compares.
7. **Branch history keeps the curriculum files that were later removed.** Commit
   `b6f7ad8` adds the 37 Claude-written curriculum candidates and `2e1bb0f` removes
   them. To keep them out of main's history, squash-merge (Sebastian's handoff plans no
   rewrite).

## Merge procedure

1. `git pull` on local `main` (it is one commit behind `origin/main`, `15d79e2`).
2. Merge `inam/encoder-specialist-route-fix` (items 1 and 3) into the branch, settle item 2, and rerun the suite.
3. Open the PR on GitHub (`gh` is not installed on Sebastian's machine). Choose squash
   or merge commit per item 7.
4. After merging, update PROGRESS.md and the Hub's Local build checklist with the
   merged commit, test counts and which results remain reported rather than reproduced.

## Looked at and fine

- Image references: the `btxrd:`/`uploads:` regex, resolve-then-`is_relative_to` check,
  manifest SHA-256 check, and before/after input hashing. `../../etc/passwd` is rejected.
- App endpoint: goes through the coordinator's own `run_specialist` argument
  validation. POSTs keep the server's 127.0.0.1 binding and Host check. Logs go to
  `runs/`, which is gitignored.
- UI panel: all server values pass through `esc()` before `innerHTML`.
- `_merge_reviewed_pairs`: union-find also pulls in exact copies and clears labels on
  conflict. Pairs with one side outside the endpoint are skipped.
- Teammate test edits (`test_hosted_profile.py`, `coordinator-evaluation.json`) follow
  the catalog and tool-list changes without weakening what they check.
