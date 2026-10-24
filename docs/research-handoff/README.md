# Complete research and implementation handoff

Start with [the integration plan](Team-integration-plan.md), [research context](Collaboration-context.md), [current project status](Project-context.md) and [the evidence/readiness record](BTXRD-readiness.md). The [research index](Research-index.md) links the broader design, model research, dataset inventory and checks.

## What is here

The repository root contains the tested combined code, not just patch attachments: portable release/evidence review, custom-model-folder provenance correction and measured source-image/cache binding across four consumers. There are 160 discovered tests, with 149 passing and 11 optional ML checks skipped in the NumPy/Pillow environment. The shipped example coordinator configuration now selects Gemma 4 31B; it is not a demonstrated running endpoint. Existing alternative profiles remain available.

The three original patches and their hash manifests remain for provenance and alternate application to the stated base. Do not apply those patches again on top of this branch. They are already incorporated. The latest hub reports `codex/demo-readiness` at `d8066fb0ffdeeba34b1b1d6f5ea9b3e6eaa8fcdf` (218 discovered, 216 pass, two Torch skips) and newer main `7bbb9032ec1d3f8c2d00ff56a434ec7a5f5e5615` with the desktop UI redesign. Those are contributor reports, not independently inspected source here. Reconcile both newer workstreams and preserve the desktop UI before merge; the reported branch and its tests are not independently verified here.

[Download the complete source archive](complete-source-handoff.zip) for the standalone 72-test foundation, the separate 84-test OncoCopilot source (Gemma coordinator/UI/training scripts and corrected BTXRD preparation), the combined receiving source and all shareable research notes. Standalone modules are reference components, not extra canonical applications. Run each source tree from its own directory to avoid the two `cancer_workbench` packages shadowing one another. The [publication manifest](publication-manifest.json) records exact file/archive hashes.

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
