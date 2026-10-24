# Cancer AI research workbench

A researcher-focused workspace: **question → evidence → eligible data → compatible model → reproducible experiment → measured result**. Background and scientific ground rules: [Cancer-AI-Research-Context.md](Cancer-AI-Research-Context.md). Status and task checklist: [PROGRESS.md](PROGRESS.md).

> Research prototype. The team has reported exploratory frozen-encoder/head experiments on BTXRD. No clinical validation or patient-independent performance is established. Synthetic fixtures test software only.

## Quick start (no installs needed for the core)

```fish
python3 -m cancer_workbench app                  # opens the researcher app at http://127.0.0.1:8765
```

The app has seven screens. **Catalog** finds compatible models. **Downloads** fetches data and weights within the budget. **Datasets** inspects files and audits or splits manifests. **Images** browses BTXRD and uploaded images with their annotations and metadata, replays a baseline run's stored predictions image by image (filter by errors, sort by confidence), and scores selected images live with that run's frozen encoder and head. **Experiments** previews and saves non-authorizing drafts and inspects recorded run lineage, scope and blockers. **Assistant** chats with or compares any OpenAI-compatible model. **Progress** shows the team checklist. It runs on localhost only. Everything except live scoring needs nothing installed; live scoring needs the `ml` extra, so start the app with `.venv/bin/python -m cancer_workbench app`. Live scores are exploratory: they do not go through `execute_specialist`, no catalog model is cleared to run, and the assistant can't call them.

The [experiment workspace](docs/reports/B-experiment-workspace.md) includes a
synthetic planning example. Saving a draft does not start training or grant
execution permission. Existing run records retain their stated limitations.

[Measured feature provenance](docs/reports/E-feature-provenance.md) binds new
exploratory caches and heads to measured inputs. Existing unbound runs retain
stored-prediction replay; live scoring/refitting requires a newly generated bound
run. Regeneration is an explicit reviewed ML operation, not an automatic migration.

Command-line equivalents:

```fish
python3 -m unittest discover -s tests            # synthetic software tests
python3 -m cancer_workbench catalog validate
python3 -m cancer_workbench fetch list           # catalog, tiers, sizes, local status
python3 -m cancer_workbench fetch plan --tier default
python3 -m cancer_workbench fetch get --tier default
python3 -m cancer_workbench route --task feature_extraction --modality xray --anatomy bone
python3 -m cancer_workbench coordinator profiles
python3 scripts/demo_observed_results.py       # offline SYNTHETIC software demo; no live LLM
python3 scripts/evaluate_coordinator.py        # versioned public development trace suite, offline by default
```

The offline demo exercises actual catalog/execution calls and a scripted
coordinator feedback cycle. It needs no medical data or model weights and does
not demonstrate live model reasoning. See [demo readiness](docs/reports/demo-readiness.md).

[Coordinator evaluation](docs/coordinator-evaluation.md) separates scripted smoke
checks, optional live trace checks and unscored human answer review. The
[Claude example profile](docs/claude-profile.md) is locally tested preparation;
no real hosted call has been verified.

ML work needs the pinned extras: `uv venv; uv pip install -e ".[ml]"` (add `imaging`, `clip` as needed).

## Automated tests

[GitHub Actions](.github/workflows/tests.yml) runs `python -m unittest discover -s tests -v` on every push and pull request using Ubuntu and Python 3.11, 3.12, 3.13 and 3.14. CI installs no optional dependencies; ML tests skip when their packages are absent. No datasets, model weights or secrets are needed.

## Layout

```text
catalog/              models.json, datasets.json: source-checked records (one canonical copy)
configs/              coordinator.example.json: named OpenAI-compatible endpoint profiles
cancer_workbench/
  common/             shared types (ResultEnvelope, EvidenceState), paths      [all, reviewed]
  acquisition/        verified resumable downloads, budget, PROVENANCE.json    [A + C]
  registry/           catalog loading + validation                            [C]
  routing/            compatibility router                                    [C]
  adapters/           specialist adapter contract, execute_specialist         [C]
  datasets/           manifest contract, audit, grouped splits, btxrd.py      [A, audit w/ F]
  learning/           frozen-encoder features, heads, distillation            [E]
  evaluation/         metrics, calibration, thresholds, leakage               [F]
  experiments/        plan + reproducibility record schema                    [B]
  coordinator/        providers (any OpenAI-compatible server), tools, loop   [D]
  retrieval/          evidence search (PubMed, MedCPT)                        [D]
  curriculum/         reviewed tool-use example export                        [D]
tests/                stdlib unittest; synthetic fixtures only
docs/                 big-machine.md, reports/ (workstream deliverables)
data/  models/        downloaded artifacts (gitignored), each with PROVENANCE.json
```

## Storage tiers

| Tier | What | Size |
|---|---|---|
| `default` | BTXRD, BreastMNIST, PathMNIST, NoduleMNIST3D, 3 LIDC series; ResNet-50, DINOv2-B, RAD-DINO, BiomedCLIP, MedCPT ×2, MONAI lung + BraTS bundles | ~5.3 GB |
| `optional` | DermaMNIST (CC BY-NC), Phikon (non-commercial), MSD BrainTumour (7.6 GB) | ~9.1 GB |
| `gated` | MedSigLIP, MedGemma-4B, UNI2-h, Virchow2, H-optimus-1. Accept terms on HF yourself, then `set -x HF_TOKEN ...` | ~22 GB |
| `big_machine` | Qwen3.8-27B BF16 / FP8 (needs `--allow-big`) | 55.6 / 30.9 GB |
| `manual` | MURA, full LIDC, BraTS 2021, PANDA, CAMELYON16, ISIC, TCGA: registration or too large | instructions in record |

The default budget is 40 GB (`CW_STORAGE_BUDGET_GB`). Fetches refuse to exceed it. Move storage with `CW_DATA_DIR` / `CW_MODELS_DIR`.

**Safety:** Downloaded files are untrusted. Several weights are pickles (`.bin`/`.pt`). Load them with `torch.load(..., weights_only=True)` or prefer the `.safetensors` file. Read downloaded data with `python -I` from outside the data directory.
