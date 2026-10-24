# B: Experiment draft contract

Implemented against `experiments/__init__.py` at source commit
`7d4bf64c47946439691bcaa02883aebb2ec296d2`. Owner: Inam Qasimi, taking over the
unclaimed B planning work. The callable and its two output states are preserved.

`plan_experiment(path, model, dataset_audit=None, budget=None)` is a pure library
function. It never downloads weights, trains, calls a specialist, changes a
catalog record, or grants execution permission. The Experiments screen now
provides UI/API draft preview, save and history; CLI integration remains absent.
`ready_for_review` means the draft passed these limited checks; a reviewed
endpoint, population, preprocessing, split, overlap assessment and execution
scope are still needed.

| Check | Required evidence |
|---|---|
| Path | `specialist_tools`, `transfer_learning` or `distillation`; unknown paths raise `ValueError` |
| Identity | Nonempty model `id` and `acquisition.revision` containing a 40/64-character hexadecimal commit/digest; moving tags are blocked |
| Specialist | Existing router's exact runnable checks: locally reproduced, reviewed allowed inference, installed adapter declaration |
| Transfer/distillation | Recorded model access plus `reuse_permissions[path] = {"status": "allowed", "evidence": "review reference"}` |
| Dataset | Positive row count, `ready_for_training: true`, well-formed findings, no errors, no unresolved-evidence or missing-patient warnings |
| Storage | Explicit finite nonnegative `used_bytes`, `planned_bytes`, `limit_bytes`; their sum must fit |

The rights dictionary is a caller-supplied **reviewed overlay**, not a catalog
promotion or a new assumption about any existing license. Inference rights do
not stand in for adaptation or teacher/student rights. No real catalog model
has been marked allowed by this work. Storage bytes are caller-supplied;
`resource_profile` remains reserved for measurements and is not populated with
estimates. The planner does not verify that an adapter is actually installed
or an artifact present; the executor must enforce those checks again.

Every returned draft includes `execution_authorized: false`, its blockers and
the checked storage inputs. A partial missing-patient warning blocks this
planner even if the current dataset audit's aggregate boolean is true. BTXRD
therefore remains blocked here. Its existing explicitly authorized exploratory
baseline is a separate path, not silently converted into a patient-valid run.

Eight synthetic tests cover all three paths, unchanged inputs, catalog-only
models, unresolved permissions, mutable references, missing/partial audits and
storage refusal. No real experiment was launched.

The later [workspace](B-experiment-workspace.md) adds 16 integration/storage
regressions and uses this library contract without promoting draft readiness
to permission. Model rights are read from the actual catalog or the explicitly
synthetic fixture, not accepted as a caller-supplied browser overlay.
