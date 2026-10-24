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
| A | Dataset & evidence curator | `datasets/`, `acquisition/`, `catalog/datasets.json` | none | Inam Qasimi (data/evidence workspace); Jordi (offline audit/evidence handoff) |
| B | Bone-model experiment design | `experiments/`, `docs/reports/B-*` | A (endpoint, grouping) | Inam Qasimi (planner + protocol draft) |
| C | Registry & specialist adapters | `registry/`, `routing/`, `adapters/`, `catalog/models.json` | none | |
| D | Coordinator & retrieval | `coordinator/`, `retrieval/`, `curriculum/` | C (tool schemas) | |
| E | Transfer learning & distillation | `learning/` | A (manifest), F (metrics) | |
| F | Evaluation & scientific quality | `evaluation/`, audit rules in `datasets/audit.py` | A | Inam Qasimi (utilities + protocol draft) |
| G | Researcher UI & API | `app/`, `experiments/workspace.py` | B, C, D interfaces | Sebastian (local app); Inam Qasimi (Experiments + dataset evidence review) |
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
- [~] Near-duplicate / same-patient detection. Exact duplicates done: 21 byte-identical pairs now share a `duplicate_group`; 2 pairs have conflicting labels (IMG000591 benign = IMG003456 normal, IMG000707 benign = IMG003346 normal) and all 4 images are unlabeled. Near-duplicate search done 2026-10-24 (`near-duplicates` CLI, [E-btxrd-source-shift.md](docs/reports/E-btxrd-source-shift.md)): besides the 21 exact pairs, IMG002677/IMG002686 (same radiograph with an added text label) and IMG000155/IMG000157 (same image re-cropped), plus many likely same-patient pairs; of the top 279 new pairs, 131 cross the image-stratified split. Candidates only: no `duplicate_group` changed yet. Next: a person reviews the list and adds confirmed same-image pairs
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
- [x] Experiments UI/API: current catalog/manifest/storage draft preview, save-time rechecks, durable non-authorizing drafts and read-only recorded-run history. Synthetic example covers the three reuse paths. Sixteen integration/storage regressions; details in `docs/reports/B-experiment-workspace.md`. No training dispatch

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

- [x] Pre-fit validation (H source check): `learning/heads.py::validate_head_inputs` runs before any C is tried and refuses misaligned or non-finite features, repeated or blank sample ids, unknown partitions, a train or val partition missing a class, and any patient or duplicate group (`group_ids`, now passed from `duplicate_group`) spanning train/val/test. Synthetic tests confirm no fit starts on bad input; both existing runs' real inputs pass and their heads still rebuild to the stored val predictions
- [x] Source-shift check (2026-10-24, [E-btxrd-source-shift.md](docs/reports/E-btxrd-source-shift.md)): preprocessing variants `pad_pstretch` and `native_crop` (`adapters/encoder.py::VARIANTS`; default `pad` hash unchanged), one variant picked per encoder × endpoint on center-1 val, test only for the pick and `pad`. Contrast stretch never won; native crop won for ResNet-50 only (test ROC-AUC benign vs malignant 0.623 → 0.690, three-class 0.609 → 0.637, tumor vs normal 0.621 → 0.623, overlapping image-level CIs). The gap to center-1 val (0.84–0.94) stays. Centers 2 + 3 were already seen in the first baseline run, so this is a hint, not a held-out result; a fair test needs an unseen source
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
- [x] Images screen handles preprocessing variants (2026-10-24): run results show their variant (`· native_crop (selected)`), and live scoring loads the encoder with the head's own variant, so source-shift heads score instead of being refused. A head whose variant doesn't match its result is still refused before any image is embedded. Live scores of 4 real test images matched the source-shift run's stored test predictions within 1e-16 for both the `native_crop` and `pad` ResNet-50 heads. Not yet checked in a browser
- [ ] "Analyze an image" through a validated adapter → native result envelope. Still blocked until C ships a reviewed adapter and the catalog promotes a model; until then the assistant must say no model can run
- [x] Experiments screen: draft checks/save plus recorded states, lineage, scope and blockers. Full guided execution/queueing remains separate. Ported into the desktop-tool shell when the demo-readiness branch was merged (2026-10-24): form in the side panel, draft review, history and record detail in the workspace, Alt+5
- [x] Desktop-tool redesign (2026-10-24): app shell with title bar, icon activity bar (now Alt+1–7), per-screen side panel / workspace / inspector panes that scroll on their own, a bottom dock for live scoring results on Images, and a status bar for storage, HF token and running downloads or scoring. Neutral graphite dark theme by default with a light toggle (remembered per browser), one blue accent, compact 13px type, inline SVG icons, still no build step or external assets. Inline `style=` attributes, which the page's CSP blocked, were replaced, so download meters, checklist bars and the large evidence ladder now render. Progress screen gained a section outline. API untouched; 106 unit tests passed at the time
- [~] Visual QA pass in a real browser (light + dark, phone width). After the redesign every screen was checked at about 1360 px wide in dark, Images, Assistant and Progress also in light, and Datasets at 800 px (stacked layout); a 2-image live RAD-DINO batch ran through the new dock with no console errors. Before the redesign, the branch's updated Images screen was checked at 1440×1000 and 390×844 in both palettes. Not yet checked: phone width (390 px) after the redesign, the ported Experiments screen beyond a smoke check, uploads, profile editing, and a running download

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

- Based on clean merged main `bff6ea43ca8996d1a6959ebbb1a1bea5bc274089`.
- B/F ownership and source-check attribution corrected to Inam Qasimi. `.mailmap` maps the earlier assistant author identity for Git reporting; future branch commits use the repository's configured human email. Existing shared commit objects are unchanged.
- `docs/reports/F-metric-hardening.md` describes the fix, compatibility changes and verification. Scientific endpoint/patient/source evidence and independent review remain unresolved. E/C/D source findings remained open at that checkpoint and are addressed in the subsequent demo-readiness branch below.
- Verified with a temporary test environment: NumPy 2.5.4, scikit-learn 1.9.1 and SciPy 1.18.1. **122 tests: 121 pass, 1 skipped** (Torch preprocessing unavailable), including all 24 new tests. Before this change, merged main ran **98 tests: 97 pass, 1 skipped** in the same environment and emitted single-class metric warnings; the patched suite does not emit those warnings.
- Plain `python3`: **122 tests: 93 pass, 29 skipped** because optional scikit-learn/Torch tests are unavailable; the newly added plain-Python summary tests pass. Before this change: **98 tests: 91 pass, 7 skipped**.
- Catalog remains 16 models and 14 datasets. No UI/learning/coordinator/adapter/catalog/shared-contract changes, medical data downloads, inference, training or evidence promotions.

## Inam Qasimi: execution checks and presentation follow-up (2026-10-24)

- Separate `codex/demo-readiness` branch, based on `df45e78`, in an isolated local
  clone. The user's existing checkout and checked-out
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

- The incoming main checkpoint reported Hub sign-in blocked. Inam has since synchronized the Local build checklist through the connected document tools.

### Pre-fit checks and source-shift run (2026-10-24)

- `.venv/bin/python -m unittest discover -s tests`: **104 tests, all passing** (6 new: pre-fit refusals, accepted blank groups, preprocessing variants, variant selection, source-shift summary, near-duplicate pair scoring). `python3 -m unittest discover -s tests`: **104 tests, OK with 11 optional ML tests skipped**. `node --check` on `app.js` and `git diff --check` pass.
- Real runs: `runs/btxrd-source-shift-20261024T071226Z/` (its `pad` rows reproduce the first baseline's test numbers exactly) and `runs/btxrd-near-duplicates-20261024T071231Z/`. Four new feature files (RAD-DINO about 25 min each on MPS); `runs/features` is 123 MB. Software and exploratory image-level results only; no catalog promotion.

- Images variant fix: **106 tests** pass in the ML environment; plain `python3` runs 106 with 11 optional ML tests skipped. `node --check` on `app.js` and `git diff --check` pass.

### GitHub Actions tests

- [x] Add `.github/workflows/tests.yml`: core unittest suite on every push and pull request, Ubuntu, Python 3.11–3.14. Official actions pinned to verified release commits; read-only repository permission; no dependency installs or artifact downloads.
- [x] Local verification: workflow YAML parses and its triggers/matrix match the requested settings. Clean Python 3.12.13 and 3.14.3 environments each discover **98 tests, OK with 8 optional ML tests skipped**. `git diff --check` passes. These are synthetic software checks only.
- [ ] Verify the first GitHub-hosted run after the workflow is committed and pushed; Python 3.11/3.13 and Ubuntu have not been exercised locally.
- [x] The latest pushed CI/source-work checkpoint is recorded in the Team Hub; the new integrated branch verification is recorded separately below.

### Integrated with latest pushed team work

- Fetched and integrated `upstream/main` at `acb8e298e196cb86187d879b00a25bc1c50a2cd9`
  into the isolated demo-readiness branch. Retained Sebastian's source-shift
  variants, near-duplicate search, shared evaluation/record helpers, public
  `validate_head_inputs`, canonical `group_ids`, unassigned-row behavior and CI.
  His overlapping E checks are existing team work; this contribution adds the
  stricter identity/hash/option checks and C/D fixes.
- Resolved the baseline helper refactor with the earlier F null-safe rendering.
  Both baseline and source-shift summaries now use the same null-safe cells.
  Added one integration regression, bringing this follow-up to 18 new tests.
- Current integrated suite: **146 discovered, 144 pass, 2 Torch preprocessing
  skips** in the available ML environment; plain Python **146 discovered,
  106 pass, 40 optional-ML skips**. Earlier 139/122/104 counts are checkpoints,
  not the integrated count. No medical artifacts or reported scores reproduced.
- At this checkpoint, `c13a74a` was unavailable. It was subsequently pushed and
  reconciled in the autonomous refinement below. No remote branch was pushed.

### Autonomous refinement and five pitch alternatives (2026-10-24)

- [x] Fetched and integrated pushed main `c13a74a15fdd636249899a587a239cb000107e6d`,
  preserving Sebastian's Images preprocessing selection/refit/cache fix and
  variant UI labels. Two incoming regressions are included. The user checkout
  remains untouched; all work is on the isolated `codex/demo-readiness` branch.
- [x] Prepared `claude-research` through the compatible provider. Credentials
  and optional workspace header come from environment references; missing key
  refuses before transport and cross-origin redirects refuse. Seven local fake-
  server/profile tests pass. No real key, live Claude call or sponsor eligibility
  is claimed. See `docs/claude-profile.md`.
- [x] Added versioned public coordinator development fixtures and runner, with
  eight offline smoke cases and six optional live cases. Actual tool results and
  next-request feedback are checked, errors retain partial traces, and final
  answer quality stays unscored. Seven regressions pass. No held-out/live model
  reasoning score or medical execution was produced.
- [x] Reviewed primary BTXRD/CLAIM sources and re-read Figshare version/license
  metadata. Corrected baseline equivalence and patient-independence overclaims
  without altering reported scores. Recorded protocol/reference-standard gaps
  in `docs/reports/research-evidence-review.md`.
- [x] Prepared five additional seven-slide editable presentation alternatives:
  research evidence, product demo, public benefit, cloud collaboration and
  engineering reliability. Each has intro/evidence/conclusion, 180-second script
  and alternate opening/close. Added short fallback, Q&A and source/visual check.
  All 35 slides inspected, spacing fixes rechecked and numeric claims matched.
- [x] Integrated software checkpoint: **162 discovered, 160 pass, 2 Torch skips**
  in the available ML environment; plain Python **162 discovered, 122 pass,
  40 optional-ML skips**. The deck's 155-test chart is explicitly the earlier
  source-integration/hosted-profile checkpoint. Counts are never summed.
- [ ] Full Torch checks, independent code/protocol review, live coordinator
  evaluation and reviewed specialist promotion remain. Genuine patient mapping
  or an independent cohort, primary endpoint and reference-standard/protocol
  review require scientific evidence. Public cloud remains unprovisioned.

### Experiment planning and recorded-run workspace (2026-10-24)

- [x] Added a seventh local screen, Experiments, connecting the existing planner
  to current catalog models, on-disk manifests and the server's storage budget.
  Browser-supplied audit/rights/budget/authorization objects are refused. Audits
  and exact manifest-byte identity are recomputed at preview and save time.
- [x] Saved blocked or review-ready drafts have UUID identity, UTC time, source
  revision, manifest hash, audit and `execution_authorized: false`. Exclusive
  creation does not overwrite an existing draft. A synthetic 12-row example
  illustrates all three reuse paths without any training or medical execution.
- [x] Added searchable history and readable lineage/scope/blocker summaries for
  saved drafts and existing ExperimentRecord files, with expandable/downloadable
  JSON. Browsing does not load models, refit heads or change run states. Invalid
  files warn while valid records remain available; paths/read volumes are bounded.
- [x] Sixteen synthetic integration/storage regressions pass. The full suite
  checkpoint is **178 discovered, 176 pass, two Torch preprocessing skips** in
  the available ML environment; plain Python **178 discovered, 138 pass,
  40 optional-ML skips**. Earlier counts are separate dated checkpoints.
- [x] Desktop browser check: synthetic preview/save, history search, readable
  details and page-reload/app-restart persistence. Simplified the example form
  and moved raw JSON behind an expandable section after visual review. Screenshots
  use an isolated QA folder. Mobile/light-theme coverage is not claimed.
- [ ] Authorized job dispatch, a complete guided training workflow, independent
  code/protocol review and scientific eligibility remain open. This screen is a
  completed planning/review component; it does not turn unresolved data or model
  permissions into approval. No cloud or hosted-model call was made.

### Measured input/cache/head repair (2026-10-24)

- [x] Independently reproduced custom model-root revision and stale source-cache
  defects at `96f2fb2` using synthetic files and mocked fitting boundaries. No
  medical inference, actual fitting, model weights or historical score changes.
- [x] Bound new feature caches to measured image bytes, actual model/config files,
  processor/source/version context and ordered feature payloads. Atomic writes,
  later-arm source hashes and per-variant result references preserve consistency.
- [x] Baseline/source-shift, near-duplicate ranking and head rebuilding check the
  binding before downstream work. Review-only ranking never extracts a cache.
  Fitted head fingerprints and identity-aware memory caches guard live scoring.
- [x] Legacy stored predictions remain replayable; unbound live scoring/refitting
  refuses until an explicitly reviewed new run is generated. Browser verified the
  replay-only explanation/disabled live button using an isolated synthetic fixture.
- [x] Current integrated suite: **218 discovered, 216 pass, two Torch skips** in
  the available ML environment. System Python: **218 discovered, 178 pass, 40
  optional-ML skips**. This adds 40 regressions to the 178-test workspace checkpoint.
  Catalog remains 16 model / 14 dataset records. JavaScript/whitespace checks pass.
- [ ] Independent review remains open. The full Torch/model-loading checks are done; see
  "Real model files, loading and tiny extraction" below.
  Hashing overhead is unbenchmarked; before/after checks are not file locks. Local
  hashes do not establish rights, authentic labels/patients, publisher trust or
  clinical validity. Migration/limits: `docs/reports/E-feature-provenance.md`.

### Demo-readiness branch merged into main (2026-10-24)

- [x] Merged `inam-demo-readiness-review` (head `d8066fb`) into main after the
  desktop-tool redesign. The branch's Experiments screen was ported into the new
  shell (activity bar entry, Alt+5; Assistant and Progress moved to Alt+6 and
  Alt+7) and the Images binding check kept main's wording.
- [x] `.venv/bin/python -m unittest discover -s tests`: **218 tests, all passing**
  on this machine (no skips). `node --check` on `app.js` passes. Browser smoke
  check: a synthetic draft previewed on the Experiments screen and saved history
  loaded, with no console errors. Phone width and light theme of that screen are
  not yet checked.


## Research handoff verification history

The following records the earlier c13a74a-based handoff. The active rebase preserves newer main's measured model/processor/image/payload/head provenance and UI; the older narrow cache repair is superseded where contracts overlap. Final combined verification follows after reconciliation.

### Earlier offline BTXRD review candidate


- [x] Candidate against main `c13a74a15fdd636249899a587a239cb000107e6d`: read-only ZIP audit, evidence-template CSV and evidence-return check under `datasets/`, exposed through `btxrd-review`. See [A-offline-release-review.md](docs/reports/A-offline-release-review.md).
- [x] Combined synthetic suite: 131 discovered, 117 pass / 14 skip in plain Python; 118 pass / 13 skip with optional Pillow. Catalog remains 16 models / 14 datasets. Optional ML/Torch tests are not claimed as run.
- [x] Real local evidence-check result compared with the independent foundation report: 3,746 source-bound rows, missing patient/lesion/reference evidence and four conflicting source-copy labels; no cohort created.
- [ ] Review/rebase the candidate, test the full supported environment, and merge only after review. This is a local proposal; shared main and the unpushed team branch are not changed. No acquisition, training, catalog promotion or medical validation is established.

## Organization handoff publication

The review branch consolidates all three local patches and provides readable research/evidence reports plus complete standalone source snapshots under `docs/research-handoff/`. The combined code passes 149 tests with 11 optional ML skips (160 discovered) with NumPy/Pillow. A proposed Gemma 4 31B coordinator profile is the shipped example default; no endpoint/model run is established. Main and the unavailable unpushed team branch remain unreconciled. Follow the integration plan before real execution.


## Main rebased onto the research handoff branch

The user corrected the operation to rebase `research/overnight-integration` onto main, leaving main unchanged. The branch now contains main `79c51d5ac9d508b602193fd0e457a8a5eecec3c5`, including Inam's demo-readiness and Sebastian's desktop/Experiments integration. Conflicts preserve upstream's broader model/processor/image/payload/head provenance and its existing tests; the earlier narrower overlapping repair commits and incompatible duplicate cache tests are superseded. The original patches/source archive remain historical artifacts. No shared main merge is performed.

The new offline release/evidence review adds 25 tests to main's 218. Current local suite: **243 discovered, 203 pass, 40 optional ML skips**. Catalog: 16 model / 14 dataset records valid. Gemma example default/profile parsing and whitespace checks pass. The current upstream app, coordinator, evaluation, learning, encoder and encoder-provenance test paths match the rebased main checkpoint byte-for-byte. Full supported ML/Torch checks remain open; no actual medical inference, training, acquisition or cluster run occurred. Patient/lesion grouping and per-row diagnostic-reference evidence remain unresolved.

### Current roles and receiving-branch evidence workspace (2026-10-24)

- [x] Corrected Inam's Hub check-in and T01–T04 contribution status with concrete
  implementation and merge references. Inam's d8066fb branch is ancestral to
  main via Sebastian's 79c51d5 integration; Jordi's additive release/evidence
  review is present in the current e22234c receiving tree. Historical claims of
  no source access or a still-unmerged contribution no longer describe this tree.
- [x] Independently verified e22234c: 243 discovered, 241 pass/two Torch skips
  in the available ML environment; system Python 203 pass/40 optional-ML skips.
  These counts preserve the distinction from Sebastian's all-218 ML checkpoint.
- [x] Added a read-only BTXRD published-evidence panel to the existing Datasets
  screen: source observations, missing evidence, next actions and snapshot hashes.
  Blank-only template export refuses returned patient/reference values. Published
  byte identities and report consistency are checked; changed/unavailable files
  degrade without disabling local manifest audits. No current archive is audited
  merely by viewing the panel, and no training/cohort/promotion is authorized.
- [x] Fourteen new SYNTHETIC snapshot/CSV/API regressions. Full follow-up suite:
  **257 discovered, 255 pass, two Torch skips** in the available ML environment;
  system Python **257 discovered, 217 pass, 40 optional-ML skips**. Catalog remains
  16 models/14 datasets; Gemma example remains selected. JavaScript/whitespace
  checks and eight scripted coordinator smoke cases pass. No live endpoint used.
- [x] Desktop browser check of panel loading, expanded review actions/provenance,
  and the existing 240-row synthetic audit alongside it; no console errors. CSV
  payload/blank-field behavior is tested through the API/library, not a completed
  browser download. Phone/light-theme coverage is not claimed.
- [ ] Receiving-branch review/merge of this follow-up; full supported Torch/model
  loading, real archive reruns and scientific/protocol evidence remain separate.
  Report: `docs/reports/A-evidence-workspace.md`. New work is on the isolated
  `codex/evidence-workspace-followup` branch; the user checkout is untouched.

## Identity guard integration and runtime inventory

- [x] Reviewed and applied the three-file identity formatting candidate to clean `e22234c8cf1356a4845e8f60da76fc2f8434d627`; implementation/test hashes match the isolated candidate exactly. Audit readiness refuses padded sample/patient/duplicate tokens; whitespace-only patients count as missing. Head preflight refuses padded identity channels. No silent normalization or identity inference.
- [x] All 10 targeted synthetic regressions pass. Combined suite in existing bundled NumPy/Pillow: **253 discovered, 213 pass, 40 optional ML skips**. Catalog: 16 models / 14 datasets valid. Whitespace check passes. See [the report](docs/reports/F-identity-formatting.md) and [exact verification](docs/research-handoff/identity-guard-integration.json).
- [x] Read-only runtime inventory: no repository `.venv`; system Python has none of the checked ML packages; the existing imaging environment has Pillow only; the bundled runtime has NumPy 2.3.5 and Pillow 12.3.0 but lacks scikit-learn/Torch and the other checked encoder dependencies. It differs from the complete pinned `ml` extra. No install or download was performed.
- [x] New team state: the browser shows `reverset` merged PR #1; authenticated desktop fetch now resolves remote main and the research branch to the preceding `e22234c` checkpoint. Earlier draft/unmerged statements above describe the handoff before that external merge. This follow-up remains on the research branch for separate review; no merge or history rewrite is performed here.
- [ ] Supported full ML/Torch and real model-loading verification, reviewed execution scope, patient/lesion mapping, per-row reference evidence and protocol review remain open. The report gives the offline runtime verification sequence. No medical pixels, weights, actual model inference, training, acquisition, cluster workload or outreach were used.

### Local evidence-panel and identity-guard integration (2026-10-24)

- [x] Reviewed the published identity-formatting guard a7f8ff4 and combined it
  with Inam's evidence-panel commit 7405810 on a separate local review branch,
  codex/evidence-identity-integration. Only PROGRESS.md conflicted; both histories
  and contributors' records are preserved. Main and BETA_TEST are unchanged.
- [x] Combined verification: **267 discovered, 265 pass/two Torch skips** in the
  available ML environment; system Python **227 pass/40 optional-ML skips**.
  Catalog remains 16 models/14 datasets. JavaScript and whitespace checks pass.
- [x] Evidence panel checked at phone width 390x844 in dark and light themes;
  document/page widths agree with no page-width horizontal overflow. Desktop
  light-mode display and export-button invocation also pass, with an observed
  3,746-row export confirmation and no console warnings/errors. CSV blank-field
  contents remain covered by the API/library tests; a completed downloaded file
  is not independently inspected in this browser pass. Viewport/theme restored.
- [ ] Review/publish/merge this combined candidate through the team's chosen
  process. Other published experiments-readiness and coordinator-profile branches
  belong to their existing workstreams and are not silently included here. Full
  supported Torch/model-loading, actual live endpoints and scientific evidence
  remain separate prerequisites. No actual inference, training or cloud workload.

## Real model files, loading and tiny extraction (2026-10-24)

- [x] Hashed every RAD-DINO and ResNet-50 file against its `PROVENANCE.json`: all match, and both weight files match the publisher checksum. The model identity now also binds each encoder's processor file (`preprocessor_config.json` / timm `config.json`). It refuses when that file's size, mean/std, interpolation or crop settings disagree with the code. All model fingerprints change; the six `runs/features` caches were already replay-only.
- [x] Real weights load completely: RAD-DINO has no missing/unexpected/mismatched keys (86.6 M parameters), and ResNet-50 loads strict, dropping only `fc`. Embeddings are finite, agree across batch sizes and agree between MPS and CPU.
- [x] Fixed `native_crop` rounding: the code rounded the long edge where both publishers truncate, and always floored the crop offset where timm rounds. ResNet-50 now matches timm exactly on synthetic images, and RAD-DINO matches transformers to within one gray level. On real JPEGs, reduced-scale draft decoding was the only remaining difference (embedding cosine down to 0.988).
- [x] `native_crop` now decodes JPEGs at full resolution like the publishers; `pad` and `pad_pstretch` keep draft decoding. On the 16 real images ResNet-50 matches timm exactly and RAD-DINO's embeddings match its processor's (cosine ≥ 0.99999). The extra decode costs a few ms per image, within run-to-run noise.
- [x] Measured tiny extraction, `scripts/extraction_smoke.py`: 16 label-free BTXRD images, both encoders × three variants on MPS, each variant timed separately in two runs. All six caches validate against their bindings. RAD-DINO runs at 2.2–2.6 images/s (about 24–28 min for all 3,746 images per variant); ResNet-50 at 31–43 images/s (about 2 min). Runtime measurement only; no fitting or scoring. Details: `docs/reports/E-model-runtime-check.md`.
- [x] `tests/test_model_loading.py` adds four opt-in real-weight checks (`CW_MODEL_TESTS=1`, synthetic images only), and three synthetic regressions were added (processor binding ×2, draft use per variant). Suite: **250 discovered**. In the ML environment, 246 pass with the 4 opt-in tests skipped; with `CW_MODEL_TESTS=1`, all 250 pass. Plain Python: 205 pass, 45 skips. Catalog: 16 models, 14 datasets.
- [ ] Independent review of the binding, rounding and full-resolution decode changes. Any new full extraction needs an explicitly authorized, reviewed run.
