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
| B | Bone-model experiment design | `experiments/`, `docs/reports/B-*` | A (endpoint, grouping) | |
| C | Registry & specialist adapters | `registry/`, `routing/`, `adapters/`, `catalog/models.json` | none | |
| D | Coordinator & retrieval | `coordinator/`, `retrieval/`, `curriculum/` | C (tool schemas) | |
| E | Transfer learning & distillation | `learning/` | A (manifest), F (metrics) | |
| F | Evaluation & scientific quality | `evaluation/`, audit rules in `datasets/audit.py` | A | |
| G | Researcher UI & API | `api/` (new), `ui/` (new) | C, D interfaces | |
| H | Independent review | `docs/reports/H-*` | all | |

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
- [x] 30 synthetic unit tests passing (`python3 -m unittest discover -s tests`)
- [x] Default-tier download: 13 artifacts fetched and checksum-verified (HF sha256 / Zenodo md5 / figshare md5; the 3 TCIA series are trust-on-first-use sha256), 6.35 GB used including extracted copies
- [ ] Review each `PROVENANCE.json`, then PR evidence_state `cataloged → access_obtained`
- [ ] `git init` + first commit + shared remote (waiting on the user)

## Milestone 1: Bone X-ray workflow (BTXRD)

### A: Dataset curator
- [~] Inventory `data/btxrd/BTXRD/BTXRD/`: found `images/` (3,719 .jpeg + 27 .jpg = 3,746, matching the paper), `Annotations/` (1,867 .json = tumor count), `dataset.xlsx`, plus a stray Office lock file `~$dataset(total).xlsx` in the release. Still to do: metadata columns, annotation format, `describe_release`
- [ ] Recover patient grouping if the release provides it. If it doesn't, document which claims become unsupported and propose an alternative (e.g. near-duplicate clustering + per-center grouping)
- [ ] Near-duplicate / same-patient detection (perceptual hash on images)
- [ ] Confirm label meanings and reference standard (histopathology vs. radiologic) from the paper
- [ ] Check source overlap with other public bone X-ray sets
- [ ] `build_manifest` → `data/btxrd/manifest.csv`, with `partition=unassigned`
- [ ] Readiness report `docs/reports/A-btxrd-readiness.md` with an acquire/defer/catalog-only recommendation

### B: Experiment design
- [ ] **Endpoint decision** (record in report): tumor-vs-normal *or* benign-vs-malignant (342 malignant images, source-reported) at image or patient level
- [ ] Protocol: eligibility, preprocessing policy, grouped split fractions + seed, threshold rule, metrics, error review
- [ ] Arms: frozen encoder (RAD-DINO now; MedSigLIP once gated access is granted) + linear head vs. ResNet-50 (and DINOv2) matched baseline
- [ ] Check MedSigLIP/RAD-DINO pretraining overlap with BTXRD sources
- [ ] Implement `experiments/plan.py::plan_experiment`

### C: Registry and adapters
- [ ] Encoder adapter (`adapters/encoder.py`) wrapping a frozen backbone → embedding envelope
- [ ] Bone classifier adapter once E produces a head
- [ ] Full input validation: geometry, bit depth, channels, normalization
- [ ] Promote models' `evidence_state` via PR as each one is actually run

### E: Transfer learning
- [ ] `learning/features.py::extract_features` (RAD-DINO, ResNet-50, DINOv2 over the BTXRD manifest)
- [ ] `learning/heads.py::train_feature_head` / `evaluate_head` (logistic / linear head)
- [ ] Optional: teacher-student distillation, after a baseline exists and with teacher rights checked

### F: Evaluation
- [ ] Protocol `docs/reports/F-evaluation-protocol.md`: patient-level aggregation, grouped bootstrap CIs, calibration, threshold from dev only
- [ ] `evaluation/metrics.py`: `binary_report`, `calibration`; leakage check vs. pretraining data
- [ ] Error review template (per-site, per-age, per-anatomy subgroups)

### D: Coordinator
- [ ] 🔒 Live Qwen endpoint. Blocked on the GPU machine: confirm its VRAM to choose BF16 (~80 GB) or FP8 (~40–48 GB). See `docs/big-machine.md`
- [ ] Develop locally against a small model via an Ollama/LM Studio profile meanwhile
- [ ] Held-out workflow evaluation set: missing inputs, unknown models, catalog-only models, tool failures, unsupported requests, conflicting sources
- [ ] Compare profiles on that set (routing accuracy, invalid args, invented results, latency)
- [ ] `retrieval/`: PubMed E-utilities search + MedCPT rerank; citation-support check
- [ ] Demo: bone specialist call + incompatible-input rejection + honest failure

### G: Interface
- [ ] API/state contract around `route_models`, `execute_specialist`, `audit_dataset`, `run_turn`
- [ ] Researcher flow mock (clearly labeled mock data)

### H: Review
- [ ] Review of this foundation: interfaces, gaps, smallest next experiment

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
