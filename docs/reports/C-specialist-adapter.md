# Frozen encoders through the real specialist path

Sebastian · October 24, 2026 · branch `sebastian/encoder-specialist`, written with Claude Code (Claude Opus 5.5).

RAD-DINO and ResNet-50 now run through `execute_specialist`, the coordinator's
`run_specialist` tool, a CLI command and a panel on the Catalog screen. All four
share one code path. Each returns a feature vector with its measured
provenance. **An embedding is not a probability, label or diagnosis**, and the
result says so. Nothing here is a medical result.

## What changed

- `cancer_workbench/adapters/installed.py`: `installed_adapters(models)` maps each
  catalog `adapter` id to a real adapter. An adapter is installed only when the
  catalog names it, the `ml` extra imports and the weights are on disk. It wraps
  the existing `FrozenEncoderAdapter`, so the processor binding and JPEG decoding
  fixes from `66562ea`/`7abd79a` are reused, not copied. Inputs are image
  references inside the data folder, not paths: `btxrd:<sample_id>` (checked
  against the manifest's declared SHA-256) or `uploads:<id>`.
- `catalog/models.json`: `rad-dino` and `resnet50-a1-in1k` move to
  `locally_reproduced` with `inference_permission: allowed` and an adapter id.
  A new `terms_review` block records inference scope and evidence separately from
  adaptation, redistribution and distillation, which all stay `unreviewed`.
  `reuse_permissions` stays unreviewed, so the experiment planner still blocks
  transfer and distillation. ResNet-50's input size is corrected from 224 to 288
  (timm `test_input_size`).
- Router: `route_models(..., installed=...)` adds a blocker for an adapter the
  catalog names but this process cannot load. The app, the coordinator toolbox
  and `specialist status` use it, so plain Python shows both encoders as blocked,
  with the reason.
- App: `POST /api/specialist/run` calls the coordinator's own `run_specialist`
  tool (same argument validation) and logs every envelope, including rejections,
  to `runs/specialist-calls/`. The Assistant now gets the installed adapters too.
  The Catalog inspector has a "Run specialist" panel for models with an adapter.
- CLI: `python -m cancer_workbench specialist status|run`.

## Terms read (local files at the pinned revisions)

| Model | License file / card | Inference scope recorded | Not yet reviewed |
|---|---|---|---|
| rad-dino | LICENSE: MIT (Microsoft). README Uses: "shared for research purposes only", "not meant to be used for clinical practice" | Research-use frozen feature extraction on local images; not clinical | adaptation, redistribution of weights or heads, distillation |
| resnet50-a1-in1k | README: `license: apache-2.0`; trained on ImageNet-1k | Research-use frozen feature extraction | the same, plus whether ImageNet's non-commercial research terms reach derived weights |

## The example: one real call

```
.venv/bin/python -m cancer_workbench specialist run --model rad-dino --image btxrd:IMG000001
```

Observed envelope (`status: ok`, adapter `frozen-encoder:rad-dino`), abridged:

| Field | Value |
|---|---|
| output | `embedding`, 768 × float32, L2 norm 15.175356 |
| vector SHA-256 | `ab17a80052481d42f3b838c1e25e8f8c41f0c65c1f5b6bd65f1dba820a4f1902` |
| input | `btxrd/BTXRD/BTXRD/images/IMG000001.jpeg`, 446,439 bytes, 3213×2397 L, SHA-256 `2ddae86a…37ad` (matches the manifest) |
| revision | `110cbc18d5133582e320b43d53bf5c44e410c936` |
| weights | `model.safetensors` SHA-256 `dbfb9f54459c38773505de64a6ab7807bdcb392610fe1e697166342e43fb91ae`, 346,345,912 bytes |
| processor | `preprocessor_config.json` SHA-256 `c537fc99…3b56`, parsed size 518, mean 0.5307, std 0.2583, bicubic |
| preprocessing | `pad` (hash `713d6faa44ab`), whole radiograph padded to square |
| model fingerprint | `85349f5989afb8e694c77fb02d6ec0c071d21452238971ffb0940c523a19529e` |
| runtime | MPS; torch 2.14.1, transformers 5.19.0, timm 1.0.30, Pillow 12.3.0, numpy 2.5.3 |

The same call for `resnet50-a1-in1k` returns 2,048 dimensions, weights
`773525d5…41bb`, processor `config.json` `ff00d936…ac50`.

**Check against stored features:** with `--return-vector`, both embeddings for
IMG000001 equal the rows in the existing pad-variant feature caches bit for bit
(cosine 1.0, max difference 0), so the specialist path computes exactly what
the baseline runs used.

**Observed rejections through the same path:** an unknown id
(`btxrd:IMG999999`), a filesystem path (`../../etc/passwd`), the wrong
modality (`mri` for RAD-DINO) and a catalog-only model (`medsiglip-448`) each
return `status: rejected` with the specific reason. Under plain `python3` both
encoders report "adapter … is not installed in this process".

## Checks

- `tests/test_specialist_adapters.py` covers image-reference resolution and
  refusals, a declared-hash mismatch, missing weights, the router's installed
  blocker, an observed rejection through `run_specialist`, the app endpoint's
  logging and the catalog promotion invariants. It includes one opt-in
  real-weight test (`CW_MODEL_TESTS=1`) that runs both encoders on a SYNTHETIC
  upload through `run_specialist` and compares the result with direct
  `FrozenEncoderAdapter.embed`.
- `tests/test_registry_routing.py`: "nothing is runnable" became "only the two
  reviewed encoders are runnable, and nothing is when no adapter is installed".
- `tests/test_hosted_profile.py` (Inam's): its RAD-DINO round trip now compares
  against the catalog's own `evidence_state` instead of the literal `cataloged`.

## Decisions still open

- Team reading of RAD-DINO's "research purposes only" for anything derived
  (fitted heads, fine-tunes) and for sharing outside the team.
- Whether ImageNet-1k's terms reach ResNet-50's derived weights.
- Exploratory fitted heads remain a separate path (Images screen,
  `experiments/explore.py`). Exposing one as a specialist needs its endpoint,
  ordered labels, encoder/head/split provenance and exploratory limits recorded
  first. It is not done here.
- Patient/lesion grouping and per-row reference standard for BTXRD stay open;
  embeddings change nothing about them.
