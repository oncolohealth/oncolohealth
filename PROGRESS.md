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
| B | Bone-model experiment design | `experiments/`, `docs/reports/B-*` | A (endpoint, grouping) | Codex (planner + protocol draft) |
| C | Registry & specialist adapters | `registry/`, `routing/`, `adapters/`, `catalog/models.json` | none | |
| D | Coordinator & retrieval | `coordinator/`, `retrieval/`, `curriculum/` | C (tool schemas) | |
| E | Transfer learning & distillation | `learning/` | A (manifest), F (metrics) | |
| F | Evaluation & scientific quality | `evaluation/`, audit rules in `datasets/audit.py` | A | Codex (utilities + protocol draft) |
| G | Researcher UI & API | `api/` (new), `ui/` (new) | C, D interfaces | |
| H | Independent review | `docs/reports/H-*` | all | Codex (source check only; independent review pending) |

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
- [x] Local Git repository and first commit available: `7d4bf64c47946439691bcaa02883aebb2ec296d2`; local source access confirmed. Connected GitHub access/push has not been verified

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
- [ ] Bone classifier adapter once E produces a head
- [ ] Full input validation: geometry, bit depth, channels, normalization
- [ ] Convert exceptions from adapter validation into failed result envelopes (H source check)
- [ ] Promote models' `evidence_state` via PR as each one is actually run

### E: Transfer learning
- [x] `learning/features.py::extract_features` (RAD-DINO and ResNet-50 over all 3,746 BTXRD images; cached in `runs/features/`)
- [x] `learning/heads.py::train_feature_head` / `evaluate_head` (logistic / linear head). Existing exploratory report: `docs/reports/E-btxrd-exploratory-baseline.md`. Reported image-level and source-holdout estimates have not been independently reproduced in this checkout; they do not establish equivalence between encoders or medical performance
- [ ] Pre-fit train/val identity, duplicate, shape, finite-feature and class-coverage validation (H source check); reject leakage before C selection
- [ ] Optional: teacher-student distillation, after a baseline exists and with teacher rights checked

### F: Evaluation
- [~] Review draft `docs/reports/F-evaluation-protocol.md`: actual baseline recipe, patient aggregation policy, paired grouped CIs, calibration, development-only choices and overlap review. Endpoint/patient/reference-standard evidence still unresolved; protocol not approved
- [x] Stdlib `evaluation/aggregate.py`, `leakage.py`, `comparison.py`: explicit binary patient aggregation, declared split/pretraining overlap and paired patient-cluster ROC-AUC/AP differences. 22 new synthetic tests, including 1,134 small metric oracle cases; no patient identities inferred
- [~] Existing ML `evaluation/metrics.py` and `thresholds.py`: implemented but still need input/non-finite/invalid-bootstrap-draw hardening (see H source check); new utilities are not automatically wired into the baseline
- [x] Empty error-review template `docs/reports/F-error-review-template.csv` and subgroup policy in F protocol; no real cases reviewed

### D: Coordinator
- [ ] 🔒 Live Qwen endpoint. Blocked on the GPU machine: confirm its VRAM to choose BF16 (~80 GB) or FP8 (~40–48 GB). See `docs/big-machine.md`
- [ ] Develop locally against a small model via an Ollama/LM Studio profile meanwhile
- [ ] Enforce coordinator tool argument types/enums and nested schema constraints before calling handlers (H source check)
- [ ] Held-out workflow evaluation set: missing inputs, unknown models, catalog-only models, tool failures, unsupported requests, conflicting sources
- [ ] Compare profiles on that set (routing accuracy, invalid args, invented results, latency)
- [ ] `retrieval/`: PubMed E-utilities search + MedCPT rerank; citation-support check
- [ ] Demo: bone specialist call + incompatible-input rejection + honest failure

### G: Interface
- [~] API/state contract: `cancer_workbench/app/api.py` wraps routing, acquisition, audit/splits, coordinator, progress
- [ ] "Analyze an image" screen: upload a radiograph → validated adapter call → native result envelope. Blocked until C ships an adapter and E a trained head; until then the app and assistant must say no model can run
- [ ] Experiment runs screen (plans, states, records), once B/E land
- [ ] Visual QA pass in a real browser (light + dark, phone width)

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

- Source baseline: `7d4bf64c47946439691bcaa02883aebb2ec296d2`; user-provided untracked brief/walkthrough preserved.
- Actual checkout verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests` discovers 85 tests: **79 pass, 6 skip** (optional ML dependencies absent), including 30 new stdlib synthetic B/F tests. Existing localhost tests pass after the sandbox permission grant. Before this change the same checkout ran 55 tests: 49 pass, 6 skip. `git diff --check` is clean.
- This pulled checkout lacks the collaborator's downloaded medical data, weights, cached features and ML environment. No training, inference, patient evaluation or catalog state promotion was performed.
