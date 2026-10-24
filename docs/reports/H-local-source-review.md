# H: Local source check and next integration work

Source reviewed: `7d4bf64c47946439691bcaa02883aebb2ec296d2`, local checkout
`/home/inamqasimi/Documents/BETA_TEST`. Codex reviewed source and implemented
the B/F additions in this change. This is not an independent review of those
new additions. No medical data, cached embeddings, downloaded weights or
reported training run outputs were available in this checkout to reproduce
the collaborator's baseline results.

## Reconciliation

The earlier Team Hub takeover handoff was prepared before source access. The
actual repo already contains encoders, train-only feature standardization,
validation-selected logistic heads, an exploratory baseline, a local app and
coordinator tools. Those are existing team work, not new Codex implementations.
The F protocol now describes the actual lbfgs/C-grid recipe rather than the
earlier handoff's suggested optimizer. B/F additions fill previously stubbed
interfaces; they do not replace the existing training pipeline.

## Concrete source findings

| Priority | Evidence at reviewed commit | Needed next |
|---|---|---|
| High | `learning/heads.py::train_feature_head` validates required keys and labels, but does not reject overlapping train/val sample or patient IDs before using val for C selection. `evaluate_head` detects overlap only later. | E: validate train/val identity, duplicates, shapes, finite features and class coverage before fitting any candidate. Call overlap checks before selection. |
| High | `experiments/btxrd_baseline.py::run` records audit errors as blockers but continues an explicitly authorized exploratory run; new planner is not called. | B/E: keep exploratory scope conspicuous; do not expose it as a general audited training endpoint. Freeze endpoint and new untouched evaluation before stronger claims. |
| Medium | `evaluation/metrics.py::_ci` catches ValueError but does not filter non-finite statistics or report rejected draws. Public functions lack aligned-length, finite-score and complete-group validation. | F: harden legacy metrics with ML-extra tests before confirmatory use. The new paired comparator implements its own stricter checks; it does not repair legacy reports. |
| Medium | `experiments/btxrd_baseline.py` records “each image is its own group”; `datasets/splits.py` actually preserves declared duplicate groups. Its source-holdout split does not itself verify cross-center duplicate isolation. | B/A: make recorded grouping accurate and audit all partitions before execution; missing patients still prevent independence claims. |
| Medium | `adapters/base.py::execute_specialist` calls `adapter.validate` outside the exception handler around `run`. | C: convert validation exceptions into a failed result envelope and cover it with a synthetic throwing adapter. |
| Medium | `coordinator/tools.py::ToolBox.call` checks JSON, required fields and unknown arguments, but not declared types, enums or nested schema constraints. | D: validate schema types/enums and run the previously prepared held-out workflow cases against actual endpoints. |

These are source-level correctness gaps, not measured exploitability or medical
performance findings. Other owners' implementation modules and shared
`common/`/manifest interfaces are unchanged, per the repository workstream rule.

## Smallest useful next experiment

Do not start another broad model search. First resolve the primary endpoint,
patient/reference-standard evidence and overlap review. E can implement the
pre-fit validation above on synthetic features without GPU access. C can test
validation-failure envelopes; D can execute its scripted failure scenarios.
Once grouping or an independent evaluation cohort is available, B/F can freeze
one comparison of the existing two frozen encoders, with matched membership,
development-only choices, paired differences and explicit limitations. A live
Qwen endpoint, new model downloads and a GPU are not prerequisites for those
software fixes.
