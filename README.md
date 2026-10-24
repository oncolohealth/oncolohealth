# Cancer AI research workbench

A researcher-focused workspace: **question → evidence → eligible data → compatible model → reproducible experiment → measured result**. Background and scientific ground rules: [Cancer-AI-Research-Context.md](Cancer-AI-Research-Context.md). Status and task checklist: [PROGRESS.md](PROGRESS.md).

> No trained cancer model, clinical validation or medical-performance claim exists here. Synthetic fixtures test software only.

## Quick start (no installs needed for the core)

```fish
python3 -m cancer_workbench app                  # opens the researcher app at http://127.0.0.1:8765
```

The app has five screens. **Catalog** finds compatible models. **Downloads** fetches data and weights within the budget. **Datasets** inspects files and audits or splits manifests. **Assistant** chats with or compares any OpenAI-compatible model. **Progress** shows the team checklist. It runs on localhost only and needs nothing installed. It can't run a model on an image yet: see PROGRESS.md (C/E/G).

Command-line equivalents:

```fish
python3 -m unittest discover -s tests            # synthetic software tests
python3 -m cancer_workbench catalog validate
python3 -m cancer_workbench fetch list           # catalog, tiers, sizes, local status
python3 -m cancer_workbench fetch plan --tier default
python3 -m cancer_workbench fetch get --tier default
python3 -m cancer_workbench route --task feature_extraction --modality xray --anatomy bone
python3 -m cancer_workbench coordinator profiles
```

ML work needs the pinned extras: `uv venv; uv pip install -e ".[ml]"` (add `imaging`, `clip` as needed).

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
