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
- [x] Catalog: 16 model and 14 dataset records, with revisions, sizes, gating and licenses checked against HF, Zenodo, figshare and TCIA APIs (17 dataset records since the 2026-10-24 subset work below)
- [x] Catalog validation (`catalog validate`)
- [x] Acquisition: resumable downloads verified against publisher checksums, optional storage cap (`CW_STORAGE_BUDGET_GB`, unlimited by default), cross-host token stripping, zip-slip-safe extraction, PROVENANCE.json per artifact
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

Run `python3 -m cancer_workbench fetch list` for live status. Storage: unlimited unless `CW_STORAGE_BUDGET_GB` is set.

| Tier | Status |
|---|---|
| default (~5.3 GB) | ✅ fetched 2026-10-23 |
| optional (~9.1 GB) | not fetched: two items are non-commercial; MSD is 7.6 GB. `fetch get --tier optional`. Subset-only records in this tier (ISIC, CAMELYON16, TCGA-SARC slides, Soft-tissue-Sarcoma, CBIS-DDSM) are skipped by `--tier` and need a chosen subset |
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

## Gemma 26B A4B selection and Claude inspection

- [x] The user selects `google/gemma-4-26B-A4B-it` instead of 31B, targeting an RTX 5070 Ti 16 GB / Ryzen 9 / 32 GB RAM desktop. The shipped example defaults to `gemma-26b-local` with an explicit llama.cpp alias, reasoning enabled and a 1024-token output cap; a separate `gemma-26b-vllm` profile covers large-memory serving. Existing local configs, other profiles, catalog and model permissions are unchanged.
- [x] [The current guide](docs/gemma-coordinator.md) binds publisher estimates to their limits, identifies Google's QAT Q4_0 candidate and gives an unexecuted local-file-only example plus exact runtime/tool/reasoning acceptance checks. Q4 loading is estimated at 14.4 GB before context/serving memory; 4B active does not mean 4B resident memory. Desktop fit, offload speed and quantized quality remain unmeasured.
- [x] Read Claude's existing visible progress: fixture-tested tools and a training recipe/spec retargeting are reported in its isolated workspace; container source/tests were not independently obtained. The account is usage-limited. No new Claude request or credits. Preserve contributor `d/pubmed-retrieval` at `aedd36a`; model-selection work uses a linked review worktree from `a7f8ff4` without changing that checkout.
- [x] Profile parsing/construction, endpoint environment override and preservation of existing provider fields pass offline. Combined suite: **253 discovered, 213 pass, 40 optional ML skips**; catalog 16 models / 14 datasets valid. All eight scripted coordinator development scenarios pass, with model-quality scores intentionally unset. These checks do not verify a real Gemma tokenizer/parser or reasoning.
- [ ] Real model loading, a live tool round trip, supported ML/Torch verification and any fine-tuning remain separate execution milestones. Patient/lesion grouping, diagnostic references and protocol/permissions remain open. No weights, medical pixels, actual model execution, installation, cluster workload or outreach occurred.


## Experiment execution-review summary

- [x] Reuse the existing preview/save/detail path to show one derived execution-review summary: task/protocol, actual artifact checks, source/reference evidence and rights, bounded resources, logs/output/checkpoint/cancel behavior and specific human execution scope. The existing planner states are unchanged; no additional client approval fields or dispatcher.
- [x] The summary always reports execution unauthorized and dispatch unavailable. Current manifest bytes are distinguished from medical source checks; reopened drafts describe saved snapshots, without rechecking current files. Legacy/tampered saved summaries are recomputed without rewriting records; existing blockers and save-time identity rechecks are preserved.
- [x] Seven new synthetic regressions pass; all 16 existing workspace tests pass. Current combined suite: **260 discovered, 220 pass, 40 optional ML skips**; catalog 16 models / 14 datasets valid. JavaScript/whitespace checks pass. Browser synthetic preview/save/reload/reopen displays the limits with no console errors. Details: [B-execution-review.md](docs/reports/B-execution-review.md).
- [ ] Full supported ML/model loading, genuine grouping/diagnostic references, scientific review and execution scope remain open. No medical pixels, weights, model execution, acquisition, training, cluster run or outreach occurred. Team-hub guarded editing is unavailable; the own check-in is prepared locally. Preserve the separate contributor root and inspect Inam's reported evidence follow-up when its actual source becomes available.

## Subset downloads (2026-10-24)

- [x] Catalog records can declare `acquisition.subset`; the user fetches whole groups (patients, cases or slides) as a seeded random sample or by ID. Sampling shuffles every group with the seed and skips groups already on disk, so asking for more continues the same order. `PROVENANCE.json` now accumulates files across fetches and records each selection (mode, seed or IDs, chosen groups, a hash of the source listing).
- [x] Listers: TCIA (series grouped by patient, optional modality filter and patient regex), Zenodo/figshare (file picker), ISIC API v2 (search that can only narrow a CC-0/CC-BY filter; 5,000-image listing cap), GDC (open-access files only, grouped by case, publisher MD5), public S3 with `checksums.md5` (CAMELYON16 slides plus their annotations).
- [x] Catalog (16 models, 17 datasets valid): `lidc-idri-sample` can add patients (1,010 patients, 1,018 CT series in the collection); the four MedMNIST records can pick resolutions; `isic-archive` and `camelyon16` moved from manual to subset-only optional records; new `soft-tissue-sarcoma` (51 patients, 9.9 GB), `cbis-ddsm` (1,566 patient groups, 163.5 GB) and `tcga-sarc-slides` (890 open slides, 261 cases, 1,095 GB). Counts come from the publisher APIs on 2026-10-24. CAMELYON16's bucket `license.txt` says CC0. None of these are bone-tumor data, and all records stay `cataloged`.
- [x] CLI `fetch units <id>` and `fetch plan|get <id> --sample N [--seed S] | --pick ID… [--query Q]`; app Downloads screen subset panel (random or pick, checklist with filter, pasted IDs, exact size check before use); `/api/fetch/units`; schema checks for subset blocks.
- [x] 17 synthetic tests in `tests/test_subsets.py`. Suite: **267 discovered**; ML environment 263 pass with 4 opt-in skips; plain Python 222 pass, 45 skips. Live checks: planning against every new source, a real tiny fetch (2 + 1 ISIC patients, one Soft-tissue-Sarcoma RTSTRUCT series) into a scratch directory, and the Downloads screen in headless Chromium (desktop, phone width, light theme; no console errors). No subset was downloaded into `data/`.
- [x] Finding: ISIC's reported file size can differ from the served image (ISIC_0911264: 358,612 vs 361,785 bytes), so ISIC images are hashed on arrival (trust on first use) and sizes are estimates.
- [x] Network fix: this machine resolves IPv6 addresses but cannot reach them (zenodo.org, api.figshare.com and huggingface.co all time out over IPv6). `download.open_url` now alternates IPv6 and IPv4 addresses with a 5 s connect timeout each, and once one family fails and the other connects, it tries the working family first for the rest of the process. A Zenodo plan took 6 s instead of minutes; later requests connect at once. Two synthetic tests use a fake socket.
- [x] Label files: catalog records can list `acquisition.supporting` files (https URL, relative path, size), fetched with every subset or whole download (integrity `size_only`; hashed on arrival). `cbis-ddsm` fetches the four case-description CSVs into `labels/` and `soft-tissue-sarcoma` fetches `clinical/INFOclinical_STS.xlsx`, both from the TCIA collection pages. Fetched live into a scratch directory; hashes matched an independent download.
- [x] CBIS-DDSM grouping verified: the TCIA collection page says each participant has several patient IDs (6,671 IDs, 1,566 participants), and the CSVs' `patient_id` column holds exactly the 1,566 `P_xxxxx` values the group regex extracts. Dataset finding: the official train/test split was made separately for mass and calcification cases, so 31 participants have rows in both a train and a test CSV. The sarcoma spreadsheet's 51 `STS_xxx` IDs match the TCIA PatientIDs.
- [x] Suite: **271 discovered**; ML environment 267 pass with 4 opt-in skips; plain Python 226 pass, 45 skips. Acquisition and subset tests also pass on Python 3.11, 3.12 and 3.13.
- [ ] Next: review the TCGA/GDC open-access terms; review RTSTRUCT ROI names and the sarcoma outcome columns; review the CBIS-DDSM pathology reference standard per row.

## Inam: current-source integration and independent CPU checks (2026-10-24)

- [x] Combined Inam's published-evidence panel with the pending identity guard,
  coordinator profiles and execution-review work, preserving original commits
  and authors. Integrated main through `94f99eb`, including Sebastian's processor,
  JPEG, subset acquisition and network fixes. Separate review branch:
  `codex/research-integration-followup`; pre-report integration `50f024f`.
  Only appended progress records conflicted; both sides were retained. Pending
  PRs #2–4 remain reviews, not approvals or a shared-main merge.
- [x] Installed the eight pinned ML dependencies in a task-only CPU environment;
  official CPU wheel SHA-256 checks and actual imports pass. Full current suite:
  **305 discovered, 301 pass, four opt-in actual-weight skips**. System Python:
  **305 discovered, 257 pass, 48 skips**. Catalog: **16 models, 17 datasets**.
  JavaScript syntax/whitespace checks and eight scripted coordinator cases pass.
  Reasoning quality is unscored; no live coordinator was called.
- [x] Three independent synthetic native-crop comparisons against timm and the
  transformers PIL/Torchvision backends pass. The default tensor backend has a
  measured two-gray-level sharp-edge difference on this finite fixture set;
  exact/universal equivalence is not claimed. All three tests detect the old
  JPEG draft-decoding regression at `66562ea`. No new encoder production edit.
- [x] Current restarted backend displays the evidence panel and reopens the
  earlier synthetic draft with original source identity, saved-snapshot limits
  and no execution authorization/dispatch. No console warnings/errors. Earlier
  phone/light-mode QA and API CSV checks remain distinct preceding checkpoints.
- [x] Prepared an unsent custodian evidence-request draft and a scientific-review
  decision worksheet. No medical data, actual weights, fitting, cloud workload
  or outreach used here. Sebastian's own actual-weight/MPS checks are recorded
  in his report and are not repeated or claimed as ours.
- [x] Published the separate candidate as draft PR #5 under Inam's account:
  https://github.com/oncolohealth/oncolohealth/pull/5 . No merge performed.
- [ ] Team review/merge of this candidate; named scientific
  decisions, genuine grouping/reference evidence, a real coordinator endpoint
  and specific medical execution scope remain task-specific next steps.
  Current report: `docs/reports/F-current-integration-review.md`. Earlier source,
  environment and test-count paragraphs above are historical checkpoints.

## Sebastian: main status check (2026-10-24)

- [x] `main`, `origin/main` and `codex/research-integration-followup` all point at `2e3f759`, so PR #5's head is now main (fast-forward; no merge commit). `research/overnight-integration`, `research/gemma-26b-coordinator` and `research/experiment-readiness` have no commits that main lacks. The PR #5 "no merge performed" entry above describes the earlier checkpoint.
- [x] Rechecked on `2e3f759`: **305 discovered**; ML environment 301 pass with 4 opt-in actual-weight skips; plain Python 257 pass, 48 skips. Catalog: 16 models, 17 datasets valid.
- [x] Finding: all six caches in `runs/features/` are legacy (no measured-input binding), so both baseline runs and the source-shift run are replay-only and live scoring refuses them. A new exploratory baseline run with bound features is under way (next section).

## Sebastian: storage cap removed by default (2026-10-24)

- [x] Removed the 40 GB default storage budget. Datasets and weights are now unlimited unless `CW_STORAGE_BUDGET_GB` is set, which restores a cap for the CLI fetcher, download jobs and uploads. The UI shows usage only when no cap is set. The experiment plan accepts `limit_bytes: null` as "no cap" (key still required).
- [x] Plain Python: **307 discovered**, 259 pass, 48 skips (two new regressions). `node --check` on `app.js` passes.
## Jordi: NPS coordinator artifact recovery (2026-10-24)

- [x] Recovered the existing `gemma26b-workflow-adapter.zip` to this PC and verified its 48,083,099 bytes and SHA-256 `4f717c5adb8771a3f7d28698283bd55849e4b5b1d795ea4e7cee999c1c03733e`. The archive and recovery notes are in `C:\Users\Jordi nieves\Documents`.
- [x] Completed NPS `onco-gemma26b-main3-91c6320e` using the saved NPS pipeline and the same 83 constructed training / 21 held-out examples, 42 optimizer steps and rank-16 text-attention LoRA. This is a reproducibility/export-check correction, not a larger corpus or full-parameter fine-tune. One GPU was allocated; measured training time was 273.5 seconds. The root curriculum implementation and separate pending candidate curricula are not promoted by this run.
- [x] A separate fresh process matched all 230 saved adapter tensors and saved reference logits exactly, reproduced held-out loss 2.3003649711608887, and completed four catalog workflows. General controls stayed 10/12 and the strict initial-tool-request score stayed 0/6. These are bounded technical/development observations, not broad model-quality or medical findings.
- [x] NPS packaged `exports/main3/gemma26b-workflow-main3.zip`: 48,515,881 bytes, SHA-256 `52c13b9840d9df6a5154adbbebd12b58acf6d067e42072a3de9b86b6c516c0c2`. Complete training/validation log and source scripts are saved in Documents. Prior source, checkpoints, failed in-process comparison and `onco-env-preflight` are preserved.
- [x] Compatible public base is fully acquired and publisher-verified at `K:\oncolohealth\models\gemma-4-26B-A4B-it-4d7ae498`: ten files, 51,644,338,194 bytes, pinned to parent revision `4d7ae4984b7db7de8f8457170b3f1a419ee76d52`. `PROVENANCE.json` records per-file identities. This establishes artifact integrity, not local inference or full app integration.
- [x] New package fully recovered to `C:\Users\Jordi nieves\Documents\gemma26b-workflow-main3.zip`: exact 48,515,881 bytes and SHA-256 `52c13b9840d9df6a5154adbbebd12b58acf6d067e42072a3de9b86b6c516c0c2` match; all 33 ZIP entries pass CRC checks. Reused completed CPU export x, then created only the final zero-GPU y/z exports. Recovery automation is paused; original remote files, failures and `onco-env-preflight` remain preserved.
- [~] Preparing actual PC inference against the verified base plus main3 adapter. Official llama.cpp b11870 release assets match publisher SHA-256; its CUDA runtime detects the RTX 5070 Ti. Adapter conversion exported all 230 tensors to BF16 GGUF; exact-parent base conversion is running with bounded RAM. Runtime/dependencies are isolated in `K:\oncolohealth-runtime`; no duplicate base download. Local serving, fit/speed, tool round trips and the real Assistant demo remain unverified.
- [~] User subsequently authorized a parallel improvement candidate: `onco-gemma26b-main4-91c6320e` is Running on NPS with one GPU, continuing the preserved main3 adapter. CPU admission/token checks passed for 229 constructed text workflows: original 83 plus 132 first-tool-focused exact-ID requests on 22 training-only records, eight actual missing-record errors and six actual specialist refusals. Original 21 development rows remain excluded from new training and already inspected; pending 157/33 material was not used. Planned 96 steps at learning rate 2e-5, followed by independent reload, workflow and retention comparisons; no improvement or promotion established yet. A second verified main3 ZIP copy is retained on K: and both copies are read-only. The first local base-conversion attempt failed at tokenizer load; isolated Transformers now matches NPS 5.20.2, vocabulary precheck passed, and lazy-streaming conversion is running with the earlier failure log preserved.
- [ ] Complete local model serving and real Assistant/catalog/compatibility/refusal-failure checks, retaining actual traces and the strict 0/6 observation. These are text-workflow research adapters requiring the compatible base, not medically validated models. Assistant image-specialist integration and PubMed/scientific-evidence work remain separate unfinished items; genuine patient/lesion grouping and diagnostic-reference blockers remain unchanged.

## Jordi: verified PC inference and isolated continuation comparison (2026-10-24)

- [x] Exact-parent Q4_K_M base conversion is complete: `K:\oncolohealth\models\gemma-4-26B-A4B-it-4d7ae498-Q4_K_M.gguf`, 16,796,017,760 bytes, SHA-256 `4f199019e3a3a90f89b5c6be94fccab3cb925f016919c87c5299a6994071b933`. The provenance sidecar pins source/runtime identities. Main3 F32 GGUF adapter is loaded at scale 1; the original base/ZIPs remain preserved.
- [x] Real local GPU/model-driven app API checks completed for model and dataset lookup, compatibility rejection, specialist refusal and missing-record error. All five fed observed results back to the model and produced final answers matching the actual results. Latencies 2.625–13.141 seconds; measured generation about 38–59 tokens/second, sampled peak GPU memory 14,777/16,303 MiB, GPU utilization 83% and temperature 55 C. Reports/metrics are saved in Documents. The original strict initial-tool score remains 0/6 in local serving. These finite development checks do not establish broad generalization.
- [x] Three main3 ZIP copies are checksum-verified and read-only on C: and K:, as recorded in the recovery state file. This is on-PC redundancy, not an off-device backup. Existing Assistant default now selects `oncolo-main3-local` in the local gitignored config.
- [x] Separate main4 completed 96 steps in 600.7 seconds: inspected-development loss 2.3003649711608887 → 1.1153210401535034; strict initial-tool score 0/6 → 5/6; general controls 10/12 → 11/12, with no previous passing-control regression. Independent saved tensor/logit/loss checks passed. Complete catalog workflows regressed to 3/4: PANDA thinking retrieved the right record but omitted a final answer. Packaging correctly failed and main4 was not promoted. Its failure log and remote checkpoint remain preserved.
- [~] User authorized a two-hour improve/test/backup cycle, larger adapters and longer training when justified. Clarified scope: NPS only for training, testing and downloads; ongoing model use and the Assistant run entirely on this PC. Diagnose main4 generation-limit/tool-history behavior before preparing main5. Browser control reports disabled in Work settings; local shell/API work continues. Image-specialist Assistant integration, PubMed and scientific/medical validation remain unfinished and are not promoted.
- [x] Main3 local PANDA thinking diagnostics completed at 512 and 1536 response-token budgets, with and without preserving thinking inside the tool turn. No local reproduction of the main4 omission was observed. A separate NPS budget/history evaluation is prepared in Documents and has not been submitted while browser control is disabled.
- [~] Main5 is prepared, untrained and unpromoted: 393 constructed workflows (83 retained plus 310 new handler-observed trajectories), covering 13 models and 14 datasets in 27 training record groups. All original development groups excluded; pinned-tokenizer assistant masks pass, maximum 2,595 tokens, no truncation. ZIP `C:\Users\Jordi nieves\Documents\OncoloHealth-main5-training-inputs.zip` is 114,547 bytes, SHA-256 `53c991a88764098327a34f1fbc55a960cb3fb4eed6358c82ffd3d59a471c64e8`. Separate rank-32 capacity candidate has 22,978,560 adapter parameters, with source A/B blocks and scaling preserved and new B columns zero; no optimizer has run on it. Proposed 240 steps at 1.5e-5 require NPS admission and comparison checks first. Current working default remains main3.
- [x] Local Images upload blocker resolved: the app had 127,516,854,094 bytes under its default 40 GB storage cap. Set this PC user's `CW_STORAGE_BUDGET_GB=200`, restarted only the workbench app, and verified its storage endpoint now reports a 200 GB cap. The real BTXRD `IMG000001.jpeg` mirror image (478,245 bytes) uploads and appears in Images as `data/uploads/62c12500810db32f.jpeg`. This is a file-ingest check; no image classification or medical result is claimed.

## Jordi: local input-to-result implementation (2026-10-24)

- [x] Deployed app-specific input guidance and an Images link, refreshing existing conversation context without changing trained weights. Three real local-model input questions and five actual tool workflows completed after correcting an observed MRI-to-bone-workflow misdirection; the first failed guidance observation is preserved. Relevant checks: 17 app, 15 coordinator/evaluation and three new guidance tests pass with UTF-8 mode and the actual 200 GB storage setting. These are finite software checks, not medical findings.
- [x] Rechecked this PC: `data/` held only the uploaded image; no image run/head or specialist weights were present. Created an isolated pinned CPU ML/imaging runtime in `K:\oncolohealth-runtime\research-venv` after checking existing installations. Public BTXRD release and pinned ResNet-50 weights have now downloaded through the existing acquisition code. C: has about 11.9 GB free; K: about 2.05 TB. The active native Gemma CUDA server remains independent.
- [~] User authorizes restoring or fitting bounded exploratory specialists and complete local direct/Assistant inference paths. Preparing a ResNet plus trained three-class BTXRD head with IMG000001 and all declared exact duplicates reserved from training and validation. Public MedMNIST acquisitions are in progress. No new classifier result is claimed yet. Shared provenance/credit register and per-modality working demonstrations or evidenced blockers are in progress.
- [~] The oncoprep handoff contains blood/clinical workflow maps and resource catalogs, including CBC/marrow/flow-cytometry research targets; no trained structured-blood classifier or labeled patient-profile table has been located. Do not invent one or confuse blood-cancer images with CBC profiles. Browser control still reports disabled, so visible UI interaction is currently blocked; actual local HTTP inference checks can proceed.
- [x] The scheduled improve/test cycle was deleted at Jordi's request. Current work is manual continuation in this chat. Main3 stays protected; main4 remains unpromoted and main5 prepared/untrained. NPS is for training/testing/downloads only; no normal inference dependency on it.
