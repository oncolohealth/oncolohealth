# Experiment execution-review summary

The existing Experiments preview/save/detail path now exposes one derived `execution_review` summary. It binds its displayed model revision, manifest SHA-256 and existing blockers to the draft inputs, while listing the task/protocol, artifacts, scientific evidence/reuse rights, resources, logs/outputs/checkpoints/cancellation and human execution scope still requiring review.

The planner's existing `blocked` / `ready_for_review` states are unchanged. The summary always says `execution_authorized: false` and `dispatch_available: false`; a passing record audit and storage-budget check are not medical evidence or runtime approval. No new browser inputs, permissions overlay, dispatcher or competing planner are introduced. The UI uses the same summary for current previews and saved draft details, with escaped text.

Save-time preview recomputation remains intact. Saved summaries are regenerated from their recorded inputs on write and read, so a hand-edited summary cannot claim authorization or current file checks. Legacy drafts without a summary gain the same read-only view without rewriting their files. Saved records explicitly say current files have not been rechecked. The original plan/audit schema, history bounds and run-record behavior remain intact.

## Verification

Against the Gemma-profile review source `3e369d63b02d25fd1635a82c84695daa41dd8bb7`:

- Seven new synthetic regressions pass: requirements remain open after passing draft checks, pure/no-file-read summary, declared-record versus source authentication, exact blockers, refusal of browser-supplied approval, save/read summary recomputation, legacy/tampered record handling and malformed-blocker visibility.
- Existing 16 workspace tests pass. The changed-manifest regression also checks that the saved review uses the new manifest identity and blockers.
- Combined suite: **260 discovered, 220 pass, 40 optional ML skips** in the existing NumPy/Pillow environment. Catalog: 16 models / 14 datasets valid. JavaScript syntax and Git whitespace checks pass. No full supported ML/Torch or real model-loading result follows.
- Browser: a synthetic preview displayed the limits despite passing draft checks; save and reload/reopen retained review-only scope and the saved-snapshot warning. No browser console errors. This was a bounded desktop dark-theme check, not a full visual/mobile audit.

Only synthetic records were used in an isolated QA storage directory. No source medical pixels, weights, acquisition, inference, actual fitting/training, live model call, cluster run or outreach occurred. The read-only summary itself performs no file, network or model operation. The local app server used for QA is stopped after inspection.

## Current limits and next action

Patient/lesion mapping, diagnostic references, conflicting-source adjudication and protocol/permission review remain unresolved. Storage reservation is a configured budget, not measured physical free space; the added SSD is not detected or configured. Desktop hardware and model execution remain deferred. No reported contributor suite counts are added to these independently verified counts.

The team hub has no text changes since the preceding check. Inam's `7405810` evidence-panel follow-up is still reported but unavailable in the fetched source; the root contributor checkout `d/pubmed-retrieval` at `aedd36a` is preserved. This work reuses the existing linked Git review worktree on `research/experiment-readiness`. Review newly available contributor source before implementing overlapping dataset-evidence UI.

The guarded Docs editing connector is unavailable. An own check-in is prepared in the canonical research outputs, not claimed inserted into the live hub. GitHub retains required commit identity/times and service-managed history; optional artifact author/tool/machine metadata is omitted. Original patches, archives and historical manifests are unchanged.
