# Complete research and implementation handoff

Start with [the integration plan](Team-integration-plan.md), [research context](Collaboration-context.md), [current project status](Project-context.md) and [the evidence/readiness record](BTXRD-readiness.md). The [research index](Research-index.md) links the broader design, model research, dataset inventory and checks.

## What is here

The active branch is rebased onto main `79c51d5ac9d508b602193fd0e457a8a5eecec3c5`, including Inam's demo-readiness integration and Sebastian's desktop UI/Experiments reconciliation. The newer upstream model, processor, source-image, feature-payload and fitted-head provenance implementation is preserved. The older overlapping folder/cache repairs are superseded, with the current upstream regression coverage retained. The offline release/evidence review and its 25 tests are added to that receiving source. Gemma 4 31B remains the example coordinator default; no live endpoint is established.

Current local verification discovers 243 tests: 203 pass and 40 optional ML checks skip in the available environment. Catalog validation reports 16 models and 14 datasets. Coordinator profiles parse with Gemma selected; whitespace checks pass. Full supported Torch/model-loading checks remain open. Read [the rebase verification](rebase-verification.json) for source identity and preservation checks.

The three original patches, their hash manifests and the [complete source archive](complete-source-handoff.zip) are immutable historical c13a74a-based handoff artifacts. They are not the current rebased source tree; do not reapply their narrower cache/provenance contracts. The archive retains the separate 72-test foundation and 84-test OncoCopilot prototype plus the earlier 160-test combined snapshot for reference. Its [publication manifest](publication-manifest.json) verifies that original export, not current source files. Use the repository root for current development and selectively consult the standalone components without shadowing packages.

## Reproduce the software checks

From the repository root:

```sh
python3 -B -m unittest discover -s tests -q
python3 -B -m cancer_workbench catalog validate
python3 -B -m cancer_workbench coordinator profiles
```

Optional dependency availability determines skips. Tests do not need medical data, weights or credentials. The real release audit and evidence-return reports were previously reproduced on the already-local original BTXRD archive, separately from synthetic software tests.

## Scientific and execution state

BTXRD has 3,746 source images, 21 exact duplicate pairs and two normal/benign copy conflicts; seven pairs cross the authors' public classification lists. The evidence template contains public release image IDs/flags and measured hashes, with patient/lesion/reference fields blank. It contains no source images, demographics or EXIF values. There is no genuine patient/lesion map or per-row diagnostic-reference record. Source binding and passing software tests do not establish cancer accuracy. Any earlier authorized image-level experiment remains exploratory; already-seen external sources are not an untouched final test set.

No actual weights, source medical images, credentials, private messages, private transcript links or private account/access details are included. Source/hash checks are not actual weight/processor authentication and do not eliminate every transient file race. No additional acquisition, model inference, training or cluster job was performed to publish this handoff. Use the plan's explicit resource/authorization and scientific gates before execution.

## Context for another assistant

Read this README, the integration plan, project context, readiness record and relevant source/tests. Preserve researcher-first reasoning, reliable specialist calls, direct reuse, transfer learning, permitted distillation and dataset evidence review. Report changes with exact source identity and actual test results; distinguish proposed designs, publisher claims, team reports, independent audits and medical validation. Record branch reconciliation rather than assuming shared chat memory. The source archive and this branch make the previous local deliverables available to the team.

Optional author/tool/machine metadata is omitted from new artifacts. ZIP requires timestamp fields; these are normalized format placeholders, not authoring dates. GitHub retains account identity, commit timestamps and service-managed history; Drive retains its managed edit history.
