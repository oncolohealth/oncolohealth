# PROGRESS

Legend: `[x]` done and verified · `[~]` partial or stub with a contract · `[ ]` not started · 🔒 blocked (reason given)
Evidence states (`cataloged → access_obtained → runnable → locally_reproduced → externally_evaluated`) change only through a reviewed PR to `catalog/*.json`.

## How to work concurrently

1. Pick a workstream below and put your name next to its **Owner** cell.
2. Work only inside your module(s). Treat other modules as fixed interfaces: if you need a change, open an issue or PR and tag that owner.
3. `cancer_workbench/common/` and the manifest contract (`datasets/manifest.py`) are shared. Changes there need review from two workstreams.
4. Each stub module's docstring is its contract. Implement against it, and say so in the PR if you change it.
5. Use synthetic fixtures for tests (mark them SYNTHETIC). Never report synthetic results as medical performance.
6. Put deliverables (reports, protocols) in `docs/reports/<workstream>-<topic>.md`.
7. Run `python3 -m unittest discover -s tests` before pushing. The core must stay standard-library only.

| WS | Focus | Module(s) | Depends on | Owner |
|---|---|---|---|---|
| A | Dataset & evidence curator | `datasets/`, `acquisition/`, `catalog/datasets.json` | none | |
| B | Bone-model experiment design | `experiments/`, `docs/reports/B-*` | A (endpoint, grouping) | Inam Qasimi (planner + protocol draft) |
| C | Registry & specialist adapters | `registry/`, `routing/`, `adapters/`, `catalog/models.json` | none | |
| D | Coordinator & retrieval | `coordinator/`, `retrieval/`, `curriculum/` | C (tool schemas) | |
| E | Transfer learning & distillation | `learning/` | A (manifest), F (metrics) | |
| F | Evaluation & scientific quality | `evaluation/`, audit rules in `datasets/audit.py` | A | Inam Qasimi (utilities + protocol draft) |
| G | Researcher UI & API | `api/` (new), `ui/` (new) | C, D interfaces | |
| H | Independent review | `docs/reports/H-*` | all | Inam Qasimi (source check only; independent review pending) |

## Phase 0: Foundation (done in this session)

- [x] Project layout, `pyproject.toml` (stdlib core; `ml`/`imaging`/`clip` extras pinned to exact versions checked 2026-10-23)
- [x] Shared types: `ResultEnvelope`, `EvidenceState`, `Permission`, `ResultStatus`
- [x] Catalog: 16 model and 14 dataset records, with revisions, sizes, gating and licenses checked against HF, Zenodo, figshare and TCIA APIs
- [x] Catalog validation (`catalog validate`)
- [x] Acquisition: resumable downloads verified against publisher checksums, 40 GB budget guard, cross-host token stripping, zip-slip-safe extraction, PROVENANCE.json per artifact
- [x] Router: task/modality/anatomy/channels/dims checks; separate `runnable` verdict; never auto-selects
- [x] `execute_specialist` + clearly SYNTHETIC adapter; catalog-only models cannot execute
- [x] Dataset manifest contract, `audit_dataset` (patient/duplicate leakage, missing ids, labels, file hashes), deterministic `grouped_split`
- [x] Coordinator: multi-profile OpenAI-compatible providers (vLLM/SGLang/Ollama/LM Studio/llama.cpp), tool box with argument validation, tool loop that feeds back only observed results, CLI `coordinator profiles|ping|ask --profile A --profile B`
- [x] Foundation synthetic unit tests; see Local source takeover verification below for the current suite count and environment-specific skips
- [x] Default-tier download: 13 artifacts fetched and checksum-verified (HF sha256 / Zenodo md5 / figshare md5; the 3 TCIA series are trust-on-first-use sha256), 6.35 GB used including extracted copies
- [ ] Review each `PROVENANCE.json`, then PR evidence_state `cataloged → access_obtained`
- [x] Local app (`python3 -m cancer_workbench app`): catalog + router, downloads with live progress/cancel/budget, dataset inventory + audit + grouped splits, multi-model assistant chat with visible tool calls, editable PROGRESS checklist. Standard library only, localhost-only, per-launch token
- [x] Install the `ml` extra into `.venv` (`uv venv --python 3.12 .venv; uv pip install --python .venv/bin/python --exclude-newer <two weeks ago> -e ".[ml]"`). Installed 2026-10-23 after a supply-chain check; `--exclude-newer 2026-10-09` keeps transitive dependencies at least two weeks old
- [x] Local Git repository and first commit available: `7d4bf64c47946439691bcaa02883aebb2ec296d2`; local source access confirmed. GitHub push verified: merge commit `e986ad2` is on `origin/main`

## Milestone 1: Bone X-ray workflow (BTXRD)

### A: Dataset curator
- [x] Inventory `data/btxrd/BTXRD/BTXRD/` (`python3 -m cancer_workbench btxrd describe`): 3,746 images (3,719 .jpeg + 27 .jpg), 1,867 LabelMe 5.4.1 annotation JSONs (2,324 rectangles + 2,318 polygons, one file per tumor image), `dataset.xlsx` (Sheet1 only; Sheet2/3 empty), plus a stray 165-byte Office lock file. Every image, row and annotation ID reconciles. 37 columns: image_id, center (1/2/3: 2,938/549/259), age, gender, 15 site flags, tumor/benign/malignant, 9 subtype flags, region (upper/lower limb, pelvis), view (frontal/lateral/oblique). Exactly one region and one view per row
- [~] Recover patient grouping if the release provides it. **Checked 2026-10-23: it does not.** `dataset.xlsx` has no patient, case or lesion column. Many consecutive rows share center, age and gender (e.g. IMG000002/3), consistent with several views per patient, but grouping must not be derived from that (Hub D04). Next: ask the maintainers for a pseudonymous mapping (Hub Q01). If it doesn't, document which claims become unsupported and propose an alternative (e.g. near-duplicate clustering + per-center grouping)
- [~] Near-duplicate / same-patient detection. Exact duplicates done: 21 byte-identical pairs now share a `duplicate_group`; 2 pairs have conflicting labels (IMG000591 benign = IMG003456 normal, IMG000707 benign = IMG003346 normal) and all 4 images are unlabeled. Near-duplicates (re-saved, cropped) not searched yet; feature similarity is the next tool
- [ ] Confirm label meanings and reference standard (histopathology vs. radiologic) from the paper. Indicators are clean: only 000 (1,879 normal), 110 (1,525 benign), 101 (342 malignant). One row, IMG001276, lists two benign subtypes (osteochondroma + synovial osteochondroma) while its annotation says synovial osteochondroma only; it is flagged in the manifest
- [ ] Check source overlap with other public bone X-ray sets
- [x] `build_manifest` → `data/btxrd/manifest.csv`, with `partition=unassigned` (`python3 -m cancer_workbench btxrd manifest [--endpoint three_class|tumor_vs_normal|benign_vs_malignant]`). 3,746 rows, all image sha256s verified by the audit; `patient_id` empty everywhere, so the audit reports `missing_patient_id` and `ready_for_training: false`
- [ ] Readiness report `docs/reports/A-btxrd-readiness.md` with an acquire/defer/catalog-only recommendation

### B: Experiment design
- [ ] **Endpoint decision** (record in report; Hub Q02, still open): three-class, tumor-vs-normal *or* benign-vs-malignant (342 malignant images, confirmed in `dataset.xlsx`). Without patient IDs only image-level, exploratory evaluation is supported. The manifest builder supports all three; `three_class` is its default, not a decision
- [~] Protocol: eligibility, preprocessing policy, grouped split fractions + seed, threshold rule, metrics, error review. Exploratory version implemented in `experiments/btxrd_baseline.py` (two split protocols, Youden threshold on val); a reviewed protocol is still needed
- [~] Arms (Hub Q03, decided 2026-10-23): frozen RAD-DINO + linear head vs. frozen ResNet-50 + linear head, both already downloaded. MedSigLIP joins as a second medical arm once its gated access is granted
- [~] Check MedSigLIP/RAD-DINO pretraining overlap with BTXRD sources. RAD-DINO: chest X-rays only per its card (no overlap expected; `training_images.csv` not checked). MedSigLIP: not acquired
- [x] `experiments/plan.py::plan_experiment`: side-effect-free draft gates for three reuse paths, pinned identity, reviewed rights, dataset findings and storage. Eight synthetic tests. Contract: `docs/reports/B-plan-contract.md`; no execution or catalog promotion

### C: Registry and adapters
- [x] Encoder adapter (`adapters/encoder.py`) wrapping a frozen backbone → embedding envelope (RAD-DINO, ResNet-50; contract in `docs/reports/C-model-cards.md`)
- [ ] Bone classifier adapter once E produces a head. Heads now persist (`learning/heads.py::save_head`/`load_head`, plain arrays, no pickle) and the Images screen scores with them through a separate exploratory path (`experiments/explore.py`); a gated adapter through `execute_specialist` still needs a reviewed catalog promotion
- [ ] Full input validation: geometry, bit depth, channels, normalization
- [x] Convert exceptions from adapter validation into failed result envelopes (H source check); synthetic regression verifies that `run` is not called after validation throws
- [ ] Promote models' `evidence_state` via PR as each one is actually run

### E: Transfer learning
- [x] `learning/features.py::extract_features` (RAD-DINO and ResNet-50 over all 3,746 BTXRD images; cached in `runs/features/`)
- [x] `learning/heads.py::train_feature_head` / `evaluate_head` (logistic / linear head). Existing exploratory report: `docs/reports/E-btxrd-exploratory-baseline.md`. Reported image-level and source-holdout estimates have not been independently reproduced in this checkout; they do not establish equivalence between encoders or medical performance
- [x] Pre-fit train/val identity, duplicate, shape, finite-feature and class-coverage validation (H source check); reject declared overlap before C selection. Duplicate groups and file hashes now pass from the BTXRD manifest to this check. Unknown patient identity still prevents independence claims
- [ ] Optional: teacher-student distillation, after a baseline exists and with teacher rights checked

### F: Evaluation
- [~] Review draft `docs/reports/F-evaluation-protocol.md`: actual baseline recipe, patient aggregation policy, paired grouped CIs, calibration, development-only choices and overlap review. Endpoint/patient/reference-standard evidence still unresolved; protocol not approved
- [x] Stdlib `evaluation/aggregate.py`, `leakage.py`, `comparison.py`: explicit binary patient aggregation, declared split/pretraining overlap and paired patient-cluster ROC-AUC/AP differences. 22 new synthetic tests, including 1,134 small metric oracle cases; no patient identities inferred
- [x] F metric/threshold follow-up against merged main `bff6ea4`: validated inputs/groups, explicit undefined metrics, invalid-bootstrap draw accounting and null-safe baseline summaries; 24 synthetic regression tests pass. Patient aggregate/paired utilities remain separate from the baseline
- [x] Empty error-review template `docs/reports/F-error-review-template.csv` and subgroup policy in F protocol; no real cases reviewed

### D: Coordinator
- [ ] 🔒 Live Qwen endpoint. Blocked on the GPU machine: confirm its VRAM to choose BF16 (~80 GB) or FP8 (~40–48 GB). See `docs/big-machine.md`
- [ ] Develop locally against a small model via an Ollama/LM Studio profile meanwhile
- [x] Enforce coordinator tool argument types/enums and the documented nested schema subset before calling handlers (H source check); synthetic tests cover rejected values and unchanged valid arguments
- [ ] Held-out workflow evaluation set: missing inputs, unknown models, catalog-only models, tool failures, unsupported requests, conflicting sources
- [ ] Compare profiles on that set (routing accuracy, invalid args, invented results, latency)
- [ ] `retrieval/`: PubMed E-utilities search + MedCPT rerank; citation-support check
- [ ] Demo: bone specialist call + incompatible-input rejection + honest failure

### G: Interface
- [~] API/state contract: `cancer_workbench/app/api.py` wraps routing, acquisition, audit/splits, coordinator, progress
- [x] Images screen (exploratory): browse BTXRD (filters by label, center, view, region, annotations, audit flags), full-size viewer with LabelMe box/polygon overlay and manifest metadata, browser upload of JPEG/PNG to `data/uploads/` (hash-named, magic-byte check, 20 MB cap, budget check)
- [x] Replay of baseline runs: pick run → protocol · endpoint · encoder, see each val/test image's stored probabilities, val threshold and right/wrong; filter by wrong, sort by confidence. Checked against the run report (source_holdout · tumor_vs_normal · RAD-DINO: confusion 395/127/114/172 matches)
- [x] Live scoring of up to 24 selected images with a run's frozen encoder + head (`ml` extra). Runs made before heads were saved are refit from their split + feature cache and used only if they reproduce the stored val probabilities (both existing runs do). Refuses training images; flags val images (optimistic), out-of-cohort images and uploads (no label, not BTXRD). Live RAD-DINO embeddings matched the feature cache exactly on MPS. Labeled EXPLORATORY; bypasses `execute_specialist` on purpose and is not exposed to the assistant
- [x] Images UI cleanup: baseline context and selection actions above the gallery; batch selection caps at 24; visible readiness guidance; background scoring reports preparation stages, current image, processed/total counts, scored/refused/failed outcomes, elapsed time and incremental results. The latest batch and results recover after page reload while the app process stays running; reconnect handles interrupted progress requests. One live UI batch at a time, with bounded in-memory history; app restart clears it. Verified a 24-image live RAD-DINO batch, reload during and after scoring, training-image refusal, an unreadable SYNTHETIC upload and simulated progress-connection failure/reconnect in the browser
- [ ] "Analyze an image" through a validated adapter → native result envelope. Still blocked until C ships a reviewed adapter and the catalog promotes a model; until then the assistant must say no model can run
- [ ] Experiment runs screen (plans, states, records), once B/E land
- [~] Visual QA pass in a real browser (light + dark, phone width). Updated Images screen checked at 1440×1000 and 390×844 in light and dark palettes; no page-width horizontal overflow. Light mode was exercised with the existing `data-theme="light"` CSS hook because browser media emulation did not change the preferred color scheme. Other screens remain unchecked. Repeated inline-style CSP console warnings were also present before this change; no scoring API failures during the successful flow

Team Hub checklist update for this UI work is prepared in `DOCS.md` for the project lead to paste; direct editing is blocked by Google sign-in.

### H: Review
- [x] Source check of existing foundation: `docs/reports/H-local-source-review.md`, with evidence-backed E/C/D/F gaps and next experiment prerequisites
- [ ] Independent review of new B/F additions and fixes to the remaining source findings

## Later milestones (only once their adapters, data and evaluation hold up)
- [ ] Lung CT: MONAI nodule-detection adapter on `lidc-idri-sample` (smoke test only, since LIDC is in its training data); NoduleMNIST3D prototyping
- [ ] Brain MRI: MONAI BraTS adapter on `msd-brain-tumour` (smoke test only, overlaps BraTS training); explicit label mapping
- [ ] Pathology: Phikon/UNI2-h features on PathMNIST, then real WSIs on the big machine
- [ ] Coordinator fine-tuning, only after measured recurring failures

## Local artifacts

Run `python3 -m cancer_workbench fetch list` for live status. Budget: 40 GB (`CW_STORAGE_BUDGET_GB`).

| Tier | Status |
|---|---|
| default (~5.3 GB) | ✅ fetched 2026-10-23 |
| optional (~9.1 GB) | not fetched: two items are non-commercial; MSD is 7.6 GB. `fetch get --tier optional` |
| gated (~22 GB) | 🔒 needs you to accept HF terms per model + `HF_TOKEN` |
| big_machine | GPU machine only |
| manual | registration / size; see each record's `instructions` |

## Open decisions (owner: project lead)
- [ ] GPU machine VRAM → BF16 vs FP8 Qwen
- [ ] BTXRD endpoint (A + B)
- [ ] Fetch the optional tier? (non-commercial licenses; 7.6 GB brain MRI)
- [ ] Which gated models to request access for (MedSigLIP is the doc's primary bone candidate)
- [ ] Repository hosting + license for the project code (none established)

## Local source takeover verification

Historical verification from the incoming branch's source checkout:

- Source baseline: `7d4bf64c47946439691bcaa02883aebb2ec296d2`; user-provided untracked brief/walkthrough preserved.
- Source checkout verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests` discovered 85 tests: **79 pass, 6 skip** (optional ML dependencies absent), including 30 new stdlib synthetic B/F tests. Existing localhost tests passed after the sandbox permission grant. Before this change the same checkout ran 55 tests: 49 pass, 6 skip. `git diff --check` was clean.
- That checkout lacked the collaborator's downloaded medical data, weights, cached features and ML environment. No training, inference, patient evaluation or catalog state promotion was performed there.

### Merge verification in the current checkout

- Integrated `origin/codex/experiment-evaluation` at `d718b41195543c3bd7c1ef590c222dd3f9f53e4b` with main's existing Images screen, saved heads and scoring recovery. Resolved documentation conflicts by retaining both workstreams' additions.
- `.venv/bin/python -m unittest discover -s tests`: **98 tests, all passing**, including the optional ML tests. `python3 -m unittest discover -s tests`: **98 tests, OK with 7 optional ML tests skipped**.
- `.venv/bin/python -m cancer_workbench catalog validate`: **16 models, 14 datasets valid**. `git diff --check` is clean. These checks establish software behavior only; no medical workload or catalog promotion was performed during the merge.
- The connected Team Hub has since been read and already records the merge and 98-test results. The follow-up synchronized B/F verification and attribution in the Local build checklist; attribution-only corrections were also applied to the earlier contribution check-ins.


## Inam Qasimi: merged-main evaluation follow-up (2026-10-24)

- Based on clean merged main `bff6ea43ca8996d1a6959ebbb1a1bea5bc274089` at `/home/inamqasimi/Documents/BETA_TEST`.
- B/F ownership and source-check attribution corrected to Inam Qasimi. `.mailmap` maps the earlier assistant author identity for Git reporting; future branch commits use the repository's configured human email. Existing shared commit objects are unchanged.
- `docs/reports/F-metric-hardening.md` describes the fix, compatibility changes and verification. Scientific endpoint/patient/source evidence and independent review remain unresolved. E/C/D source findings remained open at that checkpoint and are addressed in the subsequent demo-readiness branch below.
- Verified with a temporary test environment: NumPy 2.5.4, scikit-learn 1.9.1 and SciPy 1.18.1. **122 tests: 121 pass, 1 skipped** (Torch preprocessing unavailable), including all 24 new tests. Before this change, merged main ran **98 tests: 97 pass, 1 skipped** in the same environment and emitted single-class metric warnings; the patched suite does not emit those warnings.
- Plain `python3`: **122 tests: 93 pass, 29 skipped** because optional scikit-learn/Torch tests are unavailable; the newly added plain-Python summary tests pass. Before this change: **98 tests: 91 pass, 7 skipped**.
- Catalog remains 16 models and 14 datasets. No UI/learning/coordinator/adapter/catalog/shared-contract changes, medical data downloads, inference, training or evidence promotions.

## Inam Qasimi: execution checks and presentation follow-up (2026-10-24)

- Separate `codex/demo-readiness` branch, based on `df45e78`, in an isolated local
  clone. The user's `/home/inamqasimi/Documents/BETA_TEST` checkout and checked-out
  branch are unchanged. This work is not merged or pushed.
- E: reject invalid feature tables and declared sample/patient/duplicate/hash
  overlap before fitting or selecting a head. Manifest duplicate/hash metadata
  reaches the head inputs. Missing patient IDs remain unknown.
- C: adapter validation exceptions become failed result envelopes, with identity
  and synthetic provenance retained. D: enforce the documented tool-schema
  subset before invoking handlers, without coercion.
- Added 17 synthetic regression tests. Available ML environment: **139 discovered,
  138 pass, 1 Torch preprocessing skip**. Plain Python: **139 discovered, 103 pass,
  36 optional-ML skips**. Catalog: 16 models and 14 datasets valid. The full socket
  tests passed after the sandbox network grant. No medical workload was run.
- Added `scripts/demo_observed_results.py`; actual catalog refusal, argument
  rejection, synthetic success/failure and scripted observed-result feedback
  execute offline. This does not evaluate live LLM reasoning.
- Browser navigation checked on all six screens in a source-only desktop app.
  Catalog compatibility/refusal and the built-in 240-row synthetic audit worked.
  Screenshots captured for the presentation. This is not a full light/dark/mobile
  QA pass; downloaded-image inference remains unavailable in this checkout.
- Prepared an editable 12-slide presentation (seven-slide pitch, four appendices,
  alternate cover), original conceptual artwork, native chart/tables, real app
  captures, speaker notes, a timed demo script, claims/source ledger, researcher
  feedback guide and proposed cloud sequence. These are separate chat outputs,
  not app features. Sponsor integrations/public cloud hosting remain proposed.
- Next: independent code review and full Torch regression checks before merging;
  genuine patient mapping or an independent cohort and protocol review before
  stronger scientific claims; configured live endpoint for held-out coordinator
  evaluation. `docs/reports/demo-readiness.md` records details and limits.
