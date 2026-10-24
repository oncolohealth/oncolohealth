# Architecture

A map of the code: what each part does, how the parts depend on each other, and the contracts between them. For background see [Cancer-AI-Research-Context.md](Cancer-AI-Research-Context.md). For status and who owns what, see [PROGRESS.md](PROGRESS.md). For setup, see [README.md](README.md).

## At a glance

```text
catalog/*.json ──► registry ──► routing ──► adapters ──► ResultEnvelope
      │                            ▲            ▲
      ▼                            └── coordinator (LLM tool loop) ◄── configs/coordinator*.json
 acquisition ──► data/<id>/, models/<id>/ + PROVENANCE.json
                         │
                         ▼
                 datasets (manifest → audit → grouped split) ──► learning ──► evaluation   [stubs]
                                                                    └──── experiments   [partial]

app (local web UI + JSON API) and __main__ (CLI) sit on top and call everything above.
```

- **Core is standard library only.** ML libraries (`ml`, `imaging` and `clip` extras in `pyproject.toml`) are optional and must be imported lazily inside the modules that need them.
- **Data flows from catalog records.** `catalog/models.json` and `catalog/datasets.json` are the single source of truth for what exists. Code reads them; it never changes a record's `evidence_state` on its own.
- **Nothing runs silently.** The router lists options with reasons and never picks one. Specialists run only through `execute_specialist`, which returns a rejection or failure instead of an invented answer.

## Package layout

| Path | Role | Status |
|---|---|---|
| `cancer_workbench/__main__.py` | CLI dispatcher: `app`, `fetch`, `catalog`, `route`, `coordinator`, `btxrd`, `baseline` | done |
| `common/types.py` | Shared types: `EvidenceState`, `Permission`, `ResultStatus`, `ResultEnvelope` | done; changes need cross-workstream review |
| `common/paths.py` | `PROJECT_ROOT`, `CATALOG_DIR`, `CONFIG_DIR`, `DATA_DIR`, `MODELS_DIR` (env-overridable) | done |
| `registry/store.py` | `load_catalog()` → `Catalog` (models + datasets tagged with `_kind`, duplicate-id check, lookup, search) | done |
| `registry/schema.py` | `validate_model` / `validate_dataset`: required fields, enums, adapter/evidence consistency | done |
| `routing/router.py` | `route_models`, `compatibility_reasons`, `runnable_blockers` | done (basic checks only, see docstring) |
| `adapters/base.py` | `Adapter` protocol + `execute_specialist`, the only way a model runs | done |
| `adapters/synthetic.py` | `SyntheticThresholdAdapter` + `SYNTHETIC_MODEL_RECORD`, test-only fakes | done |
| `adapters/encoder.py` | `FrozenEncoderAdapter` (RAD-DINO, ResNet-50): shared pad-to-square preprocessing, safetensors-only loading; `ml` extra, import explicitly | done |
| `acquisition/sources.py` | Per-publisher resolvers (Hugging Face, Zenodo, figshare, TCIA, plain URL) → `FilePlan`s | done |
| `acquisition/download.py` | Resumable download, checksum verification, safe zip extraction, cross-host auth stripping | done |
| `acquisition/fetch.py` | Plan/fetch catalog records, write `PROVENANCE.json`; `fetch` CLI | done |
| `acquisition/budget.py` | Storage budget (40 GB default, `CW_STORAGE_BUDGET_GB`) | done |
| `datasets/manifest.py` | Manifest CSV contract (`FIELDS`, `PARTITIONS`), read/write | done |
| `datasets/audit.py` | `audit_dataset`: leakage, missing patient ids, labels, file integrity | done (no pixel/near-duplicate checks) |
| `datasets/splits.py` | `grouped_split`: deterministic, group-preserving, label-stratified | done |
| `datasets/btxrd.py` | BTXRD release → `describe_release` inventory and `build_manifest` (endpoints: `three_class`, `tumor_vs_normal`, `benign_vs_malignant`) | done |
| `datasets/xlsx.py` | Read-only stdlib `.xlsx` reader for metadata sheets | done |
| `coordinator/providers.py` | `OpenAICompatibleProvider` (any `/chat/completions` server), `ScriptedProvider` for tests | done |
| `coordinator/config.py` | Named profiles from `configs/coordinator.json` or `configs/coordinator.example.json` | done |
| `coordinator/tools.py` | `ToolBox` with argument validation; `default_toolbox`: `search_catalog`, `get_record`, `route_models`, `run_specialist` | done |
| `coordinator/loop.py` | `run_turn`: model proposes tool calls, results are fed back, up to `max_steps` | done |
| `experiments/records.py` | `ExperimentRecord`, `JobState`, `REUSE_PATHS` | done (schema only) |
| `experiments/plan.py` | `plan_experiment` | stub |
| `experiments/btxrd_baseline.py` | Exploratory BTXRD runs: split protocols × endpoints × encoders → `runs/<id>/` results, predictions, heads, records; `baseline` CLI | done (`ml` extra) |
| `experiments/explore.py` | Images screen backend: `list_runs`, `review` (stored val/test predictions joined with the split, stdlib), `head_for` (load or verified refit of a run's head), `score` (live encoder + head on chosen images; refuses training images). Bypasses `execute_specialist` on purpose; not in the coordinator tool box | done (`score`/`head_for` need `ml`) |
| `learning/features.py` | `extract_features` → `.npz` cache keyed by encoder revision + preprocessing hash | done (`ml` extra) |
| `learning/heads.py` | `train_feature_head` (logistic regression, C chosen on val), `evaluate_head` with leakage refusals, `save_head`/`load_head` (plain-array `.npz`, no pickle) | done (`ml` extra; distillation not implemented) |
| `evaluation/metrics.py` | `binary_report`, `multiclass_report` (bootstrap CIs), `calibration` | done (`ml` extra) |
| `evaluation/thresholds.py` | `choose_threshold` on development data (`youden`, `sensitivity>=X`) | done (`ml` extra) |
| `evaluation/` (rest) | Patient-level aggregation, leakage vs. pretraining data | stub (contracts in package docstring) |
| `retrieval/` | PubMed search + MedCPT rerank | stub (contract in docstring) |
| `curriculum/` | Export reviewed tool-use transcripts | stub (contract in docstring) |
| `app/server.py` | Stdlib HTTP server on `127.0.0.1`, Host check + per-launch token (header for `/api/`, `?t=` for `/media/` images), 32 MB body cap | done |
| `app/api.py` | JSON endpoints as plain functions; `GET_ROUTES`, `GET_PARAM_ROUTES`, `POST_ROUTES` | done |
| `app/jobs.py` | `JobManager`: one background fetch at a time, progress, cancel | done |
| `app/scoring.py` | `ScoringJobs`: one live UI scoring batch at a time, observed progress and partial results, latest-batch recovery after reload, bounded in-memory history | done |
| `app/progress_md.py` | Parse and edit `PROGRESS.md` checkboxes and owner cells | done |
| `app/static/` | `index.html`, `app.js`, `style.css`: no build step, no external assets | done |

Stub modules raise `NotImplementedError`. Their package docstring is the contract to implement against.

## Internal dependencies

```text
common          ◄── everything
registry        ◄── acquisition.fetch, coordinator.tools, app, __main__
routing         ◄── adapters.base, coordinator.tools, app, __main__
adapters        ◄── coordinator.tools, app, learning.features (encoder)
acquisition     ◄── datasets.audit + datasets.btxrd (hash_file), app, __main__
datasets        ◄── app, __main__, experiments.btxrd_baseline, experiments.explore
learning, evaluation ◄── experiments.btxrd_baseline, experiments.explore (learning only)
experiments.explore ◄── app
coordinator     ◄── app, __main__
app             ◄── __main__
```

Imports flow one way: nothing below `app` imports `app`, and `common` imports nothing from the package. Keep it that way.

## Contracts

### Catalog record (`catalog/*.json`, validated by `registry/schema.py`)

Common fields: `id`, `name`, `license`, `access`, `evidence_state`, `acquisition`, `citation`.
Models add `kind`, `tasks`, `modality`, `anatomy`, `input`, `outputs`, `inference_permission`, and optionally `adapter`.
Datasets add `modality`, `anatomy`, `counts`, `labels`, and optionally `unresolved`.

`acquisition.tier` is one of `default`, `optional`, `gated`, `big_machine`, `manual`. `acquisition.fetcher` selects a resolver in `acquisition/sources.py`. Manual-tier records must have `instructions`.

### Evidence ladder (`common.types.EvidenceState`)

`cataloged → access_obtained → runnable → locally_reproduced → externally_evaluated`

Promotion happens only through a reviewed change to `catalog/*.json`. `routing.runnable_blockers` requires `locally_reproduced`, `inference_permission: allowed`, and an `adapter` before a model may run.

### Manifest row (`datasets/manifest.py`)

`sample_id, patient_id, duplicate_group, partition, label, file, sha256`, plus any extra metadata columns.
`partition` ∈ `train | val | test | unassigned`. An empty `patient_id` is allowed but is reported by the audit. Never invent one.
`grouped_split` groups rows by `patient_id`, falling back to `duplicate_group`, then to the sample itself.

### Result envelope (`common.types.ResultEnvelope`)

Every specialist call returns one: `model_id`, `task`, `status` (`ok | rejected | failed`), `adapter_id`, `input_refs`, native `outputs`, `errors`, `synthetic`, `evaluation_refs`, `run_id`, `created_at`. Keep outputs native. Do not merge different models into one cancer probability.

### Adapter (`adapters.base.Adapter`)

`id`, `synthetic`, `validate(inputs) -> list[str]`, `run(inputs) -> dict`. Register real adapters in their own module (for example `adapters/encoder.py`) and pass them to `execute_specialist` or `default_toolbox` by id.

## Key flows

**Fetch** (`fetch get` CLI or the Downloads screen):
`select` records → `sources.resolve` queries the publisher API for files, sizes and checksums → `budget.check` → `download` resumes `.part` files and verifies them → optional `safe_extract_zip` → `write_provenance` writes `<root>/<id>/PROVENANCE.json`. In the app, `JobManager` runs this in a background thread with progress callbacks and cancellation.

**Route and run a specialist:**
`route_models(request, models)` → `{compatible: [{id, runnable, blockers}], rejected: [{id, reasons}]}`.
`execute_specialist(model, request, adapters)` checks compatibility, runnable blockers and adapter presence, then `adapter.validate`, then `adapter.run`, and wraps the result in a `ResultEnvelope`. Exceptions become `status: failed`.

**Coordinator turn** (`coordinator ask` CLI or the Assistant screen):
`make_provider(profile)` → `run_turn(provider, default_toolbox(catalog), question)`. The model sees `SYSTEM_PROMPT` and tool schemas, and each tool call goes through `ToolBox.call`, which validates arguments and returns `{result}` or `{error}`. The turn ends when the model answers without tool calls, or after `max_steps`. The app runs several profiles in parallel for side-by-side comparison.

**Audit and split** (Datasets screen):
`read_manifest` → `audit_dataset(spec, rows)` → `grouped_split(rows, fractions, seed)` → re-audit. A saved split goes to `data/<id>/splits/<name>.csv` with a `.json` sidecar recording the source manifest hash, fractions, seed and audit.

**Images screen** (replay and live scoring):
`GET /api/images/btxrd` (manifest rows) + `/media/btxrd/<file>?t=<token>` (pixels, path-checked against the image root) + `/api/annotation/btxrd/<id>` (LabelMe shapes).
Replay: `POST /api/runs/review` → `explore.review` joins `runs/<id>/splits/<protocol>.csv`, the endpoint cohort and `predictions/<result>.json`; binary verdicts use the stored val threshold (`>=`, as in `binary_report`).
Live UI: `POST /api/score/start` validates inputs and starts a `ScoringJobs` worker → `explore.score` reports preparation stages and each processed image → browser polls `GET /api/score/jobs/<id>` for counts, partial results and final output. `GET /api/score/current` restores the latest batch, selected image keys and run context after a page reload, including completed results. Jobs live only in the app process; restart clears them, and history is capped at eight batches. `POST /api/score` keeps the synchronous API for existing clients. Scoring itself is unchanged: `head_for` loads `heads/<result>.npz` or refits from the split + feature cache and keeps it only if it reproduces the stored val probabilities → refuse training images → `FrozenEncoderAdapter.embed` per image → head probabilities. Uploads go to `data/uploads/<sha256[:16]>.<ext>` with a JSON sidecar via `POST /api/uploads/add`.

**App request:**
browser → `server.Handler` checks the Host header and `X-CW-Token` → looks up the path in `api.*_ROUTES` → plain function → JSON. `api.ApiError` maps to its HTTP status; other exceptions return 500.

## Data and config on disk

| Path | Contents | Tracked |
|---|---|---|
| `catalog/models.json`, `catalog/datasets.json` | Source-checked records | yes |
| `configs/coordinator.example.json` | Example endpoint profiles (vLLM, SGLang, Ollama, LM Studio, llama.cpp) | yes |
| `configs/coordinator.json` | Local profiles, written by the app | no |
| `data/<id>/`, `models/<id>/` | Downloaded artifacts + `PROVENANCE.json` (`CW_DATA_DIR`, `CW_MODELS_DIR`) | no |
| `data/uploads/` | Images uploaded in the app, hash-named, with a JSON sidecar | no |
| `runs/features/`, `runs/<run-id>/` | Cached features; per-run splits, predictions, heads, `results.json`, `records.json`, `summary.md` | no |
| `.venv/` | `uv venv` with the `ml` extra | no |
| `PROGRESS.md` | Checklist, also edited in place by the Progress screen | yes |
| `docs/` | `big-machine.md` (GPU setup), `reports/` (workstream deliverables) | yes |

Downloaded files are untrusted. Some weights are pickles, so load them with `torch.load(..., weights_only=True)` or use `.safetensors`.

## Tests

`python3 -m unittest discover -s tests` runs the standard-library suite; `.venv/bin/python -m unittest discover -s tests` also runs the ML tests. Synthetic fixtures only.

| File | Covers |
|---|---|
| `test_registry_routing.py` | Catalog validation, routing, `execute_specialist` |
| `test_acquisition.py` | Download, resume and verification; zip safety |
| `test_datasets.py` | Audit findings, grouped splits |
| `test_btxrd.py` | `.xlsx` reader, BTXRD describe and manifest on a synthetic release |
| `test_learning_eval.py` | Split protocols, heads (incl. save/load round trip), metrics, thresholds, preprocessing (ML tests skip without the `ml` extra) |
| `test_coordinator.py` | Tool loop with `ScriptedProvider`; OpenAI-compatible client against a local fake server |
| `test_app.py` | `PROGRESS.md` editing, API functions, uploads, media path checks, run replay, server Host and token guards (including scoring recovery) |
| `test_scoring.py` | Scoring progress across success/refusal/error, concurrent-batch refusal, failure preservation, recovery snapshots, bounded history and API input resolution |
| `helpers.py` | `LocalServer` fixture |

## Where new work plugs in

| To add | Put it in | Wire it through |
|---|---|---|
| A model or dataset | `catalog/*.json` record | `catalog validate`; resolver in `acquisition/sources.py` if the publisher is new |
| A real specialist | `adapters/<name>.py` implementing `Adapter` | catalog `adapter` field; pass the instance in the `adapters` dict |
| Another frozen encoder | an entry in `adapters/encoder.py::ENCODERS` (+ loader if new architecture) | `--encoder` choice in `experiments/btxrd_baseline.py::ENCODERS` |
| Another dataset's manifest | `datasets/<name>.py`, following `btxrd.py` | Datasets screen picks up `data/<id>/*.csv` automatically |
| A new split protocol or endpoint | `experiments/btxrd_baseline.py` (`PROTOCOLS`, `CLASSES`) and `datasets/btxrd.py::ENDPOINTS` | `baseline --protocol/--endpoint` |
| A coordinator tool | `coordinator/tools.py::default_toolbox` | JSON schema + handler returning observed data |
| An app endpoint | function in `app/api.py` + entry in a route table | call it from `app/static/app.js` via `api()` |
| A CLI command | `__main__.py` | add to `commands` |
