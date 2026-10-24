# Experiment workspace and recorded run history

The **Experiments** screen connects the existing side-effect-free planner to the
local app and adds durable draft records plus a read-only view of existing
`ExperimentRecord` files. It is a planning and review workflow. It does not
implement training dispatch, a general job queue or model promotion.

The [execution-review follow-up](B-execution-review.md) adds a derived review summary to preview/save/reopen, explicitly distinguishing current manifest checks from a saved snapshot and keeping job dispatch unavailable. Earlier counts below describe the original workspace checkpoint.

## Researcher workflow

1. Enter an unreviewed research question and choose a reuse path, catalog model,
   local CSV manifest and planned additional storage reservation.
2. Preview the draft. The server loads the current catalog, reads and hashes
   the exact manifest bytes, computes the audit and checks the actual local
   storage budget. It accepts no client audit, rights overlay, budget override
   or execution authorization. Ambiguous identity whitespace and missing labels
   in assigned partitions remain visible errors rather than silently normalized
   identities or inferred reference labels.
3. Save a blocked or review-ready draft. The server repeats the checks at save
   time, so a changed manifest/storage state is not replaced by a stale preview.
   The saved JSON includes the audit, manifest SHA-256, source revision, UTC
   creation time, synthetic flag, question and computed draft. Every draft has
   `execution_authorized: false`. A changed question/model does not silently
   reuse the previous preview in the browser.
4. Inspect saved drafts and existing `runs/<run>/records.json` entries. The
   history is searchable and shows state, task and model. Details retain cohort,
   split, source, scope, outputs and blockers. Full JSON can be expanded and
   downloaded. A recorded completed state is not a scientific approval.

The synthetic example has 12 invented rows, unique declared patient IDs, two
classes and train/validation/test partitions. Its fixture rights and immutable
all-zero revision apply only to this software example. It can illustrate all
three reuse paths without medical data or weights. It never grants rights to a
real model or claims a trained/distilled model exists.

## Files and API

| Interface | Behavior |
|---|---|
| `GET /api/experiments/options` | Current model choices, local manifest paths and storage |
| `POST /api/experiments/preview` | Compute a fresh non-authorizing draft |
| `POST /api/experiments/save` | Recompute, then exclusively create `runs/drafts/<uuid>.json` |
| `GET /api/experiments/history` | Bounded local history with explicit warnings |
| `POST /api/experiments/record` | Read one draft or established ExperimentRecord |

All endpoints retain the existing local server Host/per-launch-token boundary.
The existing exploratory Images `/api/runs` interface is unchanged. Drafts are
not inserted into baseline `results.json`, and browsing history never loads or
refits a head. The workspace does not register an execution tool with the
coordinator.

Record reads remain inside the runs directory, reject external symlink targets
and non-finite/malformed JSON, and retain other valid records when one file is
bad. The preview caps individual files at 2 MB, aggregate reads at approximately
8 MB, run files at 100 and displayed items at 500. CSV preview is limited to
16 MB. History is ordered by file modification time, which is not asserted to
be the experiment's actual completion time. Older records stay on disk. UUID
collisions do not overwrite existing drafts.

## Verification

Sixteen synthetic regressions cover all paths, no preview writes/dispatch,
durability, save-time manifest changes and identity hashes, forbidden supplied
authority, invalid storage/types, malformed CSV/JSON, blocked real catalog
models, missing/ambiguous identities, saved scope/outputs/blockers, path and
symlink refusal, exclusive creation and bounded history/error reads.

The desktop browser check exercised the synthetic preview, save, history
filtering, detail view and reload/restart persistence. The first visual pass
led to a simpler synthetic form and a readable lineage summary above expandable
JSON. Screenshots use synthetic draft data from a disposable QA folder. This
does not establish mobile/light-theme coverage or scientific correctness.

Current full-suite checkpoint: 178 discovered, 176 pass, two Torch preprocessing
skips in the available ML environment. Plain Python: 178 discovered, 138 pass,
40 optional-ML skips. No medical execution or hosted model call occurred.

Next: independent implementation/protocol review and a properly authorized job
execution path after actual data/model eligibility evidence is supplied. The
existing exploratory baseline remains a separate explicitly limited route.
