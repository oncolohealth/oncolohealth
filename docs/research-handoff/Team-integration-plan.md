# Integration and first-training plan

The target is a runnable researcher workbench and one bounded bone-X-ray baseline by noon–2 PM Pacific on October 24. This is a planning target, not a measured runtime promise or a claim that a medically validated model can be finished by that time. A frozen-encoder classifier is the first training target. Gemma 4 31B remains the reasoning coordinator candidate; coordinator fine-tuning follows measured workflow failures rather than being a prerequisite for the first image experiment.

## Immediate shared-source handoff

Use the organization repository's `research/overnight-integration` branch and its `docs/research-handoff/README.md`. It consolidates the inspected shared main `c13a74a15fdd636249899a587a239cb000107e6d` with the release/evidence utilities, custom-model-folder provenance repair and source-image/cache binding repair. All three patches have already been tested together: 160 tests discovered, 149 pass and 11 optional ML checks skip with NumPy/Pillow. The foundation's 72 tests and the separate OncoCopilot build's 84 tests describe different source trees; do not add those totals or call them medical evidence.

The complete source archive retains both standalone implementations for reference, including the Gemma coordinator, training scripts and data-preparation corrections. They are reference components for selective integration, not extra canonical applications. The shared root package is the receiving implementation. Public research notes, audit JSON, patch/file hashes, the blank evidence template and the characterization checks accompany it. Source medical images, model weights, credentials, private messages and private account/access details are excluded.

The hub reports Inam's unpushed `codex/demo-readiness` branch at `d8066fb0ffdeeba34b1b1d6f5ea9b3e6eaa8fcdf`, with Experiments planning/history, measured feature/head provenance repairs and a reported 218-test suite (216 pass, two Torch skips). That branch has not been independently inspected here. The hub also reports main `7bbb9032ec1d3f8c2d00ff56a434ec7a5f5e5615` with Sebastian's desktop UI redesign, newer than this handoff's c13a74a base. Preserve and reconcile both workstreams; do not replace the newer UI with this earlier source snapshot. Reconcile its actual source with this receiving branch before declaring the team build integrated; a hub report is not a source merge.

## Work that can proceed together

| Workstream | Proposed lead, based on existing contributions | Concrete next output | Acceptance check |
|---|---|---|---|
| Integration | Inam, with this integration handoff | Reconcile the actual demo-readiness source, preserve Images/Experiments/evaluation work and the three repairs | One review branch, one source commit, old and new regression suites passing; list any skipped checks |
| Model/runtime | Sebastian | Inspect existing RAD-DINO/ResNet-50 weight and processor files, bind their actual hashes, and complete the full supported Torch checks | Exact artifacts and preprocessing recorded; one measured tiny extraction test before estimating time or resources |
| Scientific protocol | Moshe if available; otherwise an explicitly named reviewer | Choose the first endpoint, evaluation unit, exclusions, class order and primary metric | Written prospective protocol; patient-independent status remains blocked without genuine grouping/reference evidence |
| Dataset/evidence | Inam or an explicitly named data reviewer | Review contradictions and near-duplicate candidates; prepare the custodian evidence request | No invented patient IDs, pathology claims or grouping from filenames/similarity; retain source flags and adjudication records |
| Coordinator/product | An available developer | Run the shared assistant against a real approved Gemma endpoint; connect registry/evidence tools and preserve failure handling | One real tool-call/result roundtrip plus unavailable/malformed-tool refusal; retain ordinary reasoning/coding checks |

These are proposed responsibilities, not claims that anyone accepted a deadline. Contributors should record their source commit, completed checks, blockers and next action in the hub rather than claiming other people's work is applied.

## Before noon: converge and establish runtime readiness

1. Make the handoff files available in GitHub and update the team hub with the branch/review link. Every teammate's assistant should read the handoff, current source and relevant tests before changing anything. Chat memory does not synchronize automatically.
2. Reconcile the unpushed team branch and run the combined tests in the actual ML environment. Inspect real weight/configuration identities; a declared revision is not a verified weight file.
3. Keep the smallest experiment: compare existing frozen RAD-DINO and ResNet-50 representations with matched small classifiers. The proposed first endpoint is normal/benign/malignant; confirm it instead of mixing binary and three-class results. Use current labels and exclusions consistently.
4. Treat legacy feature caches as unbound. Do not append newly measured hashes to old embeddings merely to satisfy the guard. Recompute under a recorded, authorized extraction or establish trustworthy original provenance with explicit independent review. Select preprocessing on development data only.
5. Verify execution authorization, hardware, usable storage, resource/time limits, logs, checkpoint destination and cancellation behavior. Public NPS guides and draft scripts do not establish that the account, container or workload is ready.

## Noon–2 PM: conditional first run

If runtime/artifact checks and explicit execution scope are ready, run a tiny extraction/fitting smoke test, measure it, then run the bounded baseline under the frozen protocol. Record data/model/processor/source identities, exact eligibility and exclusions, seeds, failures, timing, metrics and output locations. Preserve a reproducible result even if a candidate fails.

BTXRD currently has no trustworthy image-to-patient/lesion map or per-row diagnostic reference record. A run before those are resolved must be explicitly authorized and labeled an exploratory image-level/source-shift research probe. It cannot establish patient-independent cancer detection. Centers 2 and 3 have already been examined and cannot be relabeled as an untouched final test set. Conflicting labels and visual-overlap candidates need an explicit review policy.

If the runtime or scientific gate cannot be met in the window, finish the integrated software demonstration and report the exact blocker. Do not fabricate performance, silently relax checks, infer patient identity, or spend unbounded compute to meet the clock. A defensible patient-independent comparison requires custodian evidence or a genuinely suitable independently grouped cancer cohort.

## Required handoff from each contributor

Return the source branch/commit, changed files, checks actually run with pass/skip/failure counts, whether any real model/data execution occurred, the result's evidence level, blockers and the next action. Preserve general reasoning, reliable specialist calls, direct reuse, transfer learning and permitted distillation; dataset evidence review supports all three paths.
