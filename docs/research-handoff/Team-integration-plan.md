# Integration and first-training plan

The target is a runnable researcher workbench and one bounded bone-X-ray baseline by noon–2 PM Pacific on October 24. This is a planning target, not a measured runtime promise or a claim that a medically validated model can be finished by that time. A frozen-encoder classifier is the first training target. Gemma 4 31B remains the reasoning coordinator candidate; coordinator fine-tuning follows measured workflow failures rather than being a prerequisite for the first image experiment.

## Immediate shared-source handoff

Use the organization repository's `research/overnight-integration` branch and `docs/research-handoff/README.md`. At the user's corrected rebase handoff, it was based on main `79c51d5ac9d508b602193fd0e457a8a5eecec3c5` and remained unmerged at that checkpoint. Inam's demo-readiness work and Sebastian's updated desktop/Experiments integration are included from that main checkpoint. That rebase preserved their broader provenance implementation, UI, coordinator/evaluation code and original regression coverage byte-for-byte. The older narrow folder/cache repairs are superseded; the offline release/evidence utilities and 25 tests are retained.

The team subsequently merged PR #1, advancing remote main to `e22234c8cf1356a4845e8f60da76fc2f8434d627`. That external action supersedes the handoff's draft/unmerged status. The continuation keeps new work on the research branch for separate review. Its identity formatting guard changes only audit/head checks and ten regressions, preserving the broader integrated implementation.

Current local checks: **253 tests discovered, 213 pass, 40 optional ML skips**, including all ten identity regressions. Catalog: 16 models and 14 datasets. The available bundled NumPy/Pillow environment differs from the full pinned ML extra and lacks scikit-learn/Torch. Full supported ML/Torch, real model loading and medical execution remain unverified here. Original patches, manifests and source archive are immutable historical records; their earlier counts do not describe the current tree.

The source archive retains both standalone implementations for reference, including the Gemma coordinator, training scripts and data-preparation corrections. They are reference components for selective integration, not extra canonical applications. The shared root package is the receiving implementation. Public research notes, audit JSON, patch/file hashes, the blank evidence template and characterization checks accompany it. Source medical images, model weights, credentials, private messages and private account/access details are excluded.

## Work that can proceed together

| Workstream | Proposed lead, based on existing contributions | Concrete next output | Acceptance check |
|---|---|---|---|
| Integration | Inam, with this integration handoff | Review the rebased source/diff, preserving upstream Images/Experiments/evaluation and broader provenance checks | One review branch, one source commit, old and new regression suites passing; list any skipped checks |
| Model/runtime | Sebastian | Inspect existing RAD-DINO/ResNet-50 weight and processor files, bind their actual hashes, and complete the full supported Torch checks | Exact artifacts and preprocessing recorded; one measured tiny extraction test before estimating time or resources |
| Scientific protocol | Moshe if available; otherwise an explicitly named reviewer | Choose the first endpoint, evaluation unit, exclusions, class order and primary metric | Written prospective protocol; patient-independent status remains blocked without genuine grouping/reference evidence |
| Dataset/evidence | Inam or an explicitly named data reviewer | Review contradictions and near-duplicate candidates; prepare the custodian evidence request | No invented patient IDs, pathology claims or grouping from filenames/similarity; retain source flags and adjudication records |
| Coordinator/product | An available developer | Run the shared assistant against a real approved Gemma endpoint; connect registry/evidence tools and preserve failure handling | One real tool-call/result roundtrip plus unavailable/malformed-tool refusal; retain ordinary reasoning/coding checks |

These are proposed responsibilities, not claims that anyone accepted a deadline. Contributors should record their source commit, completed checks, blockers and next action in the hub rather than claiming other people's work is applied.

## Before noon: converge and establish runtime readiness

1. Make the handoff files available in GitHub and update the team hub with the branch/review link. Every teammate's assistant should read the handoff, current source and relevant tests before changing anything. Chat memory does not synchronize automatically.
2. Review the rebased combined source and run its tests in the actual ML environment. Inspect real weight/configuration identities; a declared revision is not a verified weight file.
3. Keep the smallest experiment: compare existing frozen RAD-DINO and ResNet-50 representations with matched small classifiers. The proposed first endpoint is normal/benign/malignant; confirm it instead of mixing binary and three-class results. Use current labels and exclusions consistently.
4. Treat legacy feature caches as unbound. Do not append newly measured hashes to old embeddings merely to satisfy the guard. Recompute under a recorded, authorized extraction or establish trustworthy original provenance with explicit independent review. Select preprocessing on development data only.
5. Verify execution authorization, hardware, usable storage, resource/time limits, logs, checkpoint destination and cancellation behavior. Public NPS guides and draft scripts do not establish that the account, container or workload is ready.

## Noon–2 PM: conditional first run

If runtime/artifact checks and explicit execution scope are ready, run a tiny extraction/fitting smoke test, measure it, then run the bounded baseline under the frozen protocol. Record data/model/processor/source identities, exact eligibility and exclusions, seeds, failures, timing, metrics and output locations. Preserve a reproducible result even if a candidate fails.

BTXRD currently has no trustworthy image-to-patient/lesion map or per-row diagnostic reference record. A run before those are resolved must be explicitly authorized and labeled an exploratory image-level/source-shift research probe. It cannot establish patient-independent cancer detection. Centers 2 and 3 have already been examined and cannot be relabeled as an untouched final test set. Conflicting labels and visual-overlap candidates need an explicit review policy.

If the runtime or scientific gate cannot be met in the window, finish the integrated software demonstration and report the exact blocker. Do not fabricate performance, silently relax checks, infer patient identity, or spend unbounded compute to meet the clock. A defensible patient-independent comparison requires custodian evidence or a genuinely suitable independently grouped cancer cohort.

## Required handoff from each contributor

Return the source branch/commit (the shared branch remains separate from main), changed files, checks actually run with pass/skip/failure counts, whether any real model/data execution occurred, the result's evidence level, blockers and the next action. Preserve general reasoning, reliable specialist calls, direct reuse, transfer learning and permitted distillation; dataset evidence review supports all three paths.
