# Handoff: encoder specialists, knowledge cards and open work

Sebastian · October 24, 2026 · branch `sebastian/encoder-specialist` (from main
`15d79e2`), written with Claude Code (Claude Opus 5.5). Software progress only;
nothing here is a medical result.

## What works now

- **RAD-DINO and ResNet-50 run through the product's real call path**: the
  coordinator's `run_specialist` tool, `POST /api/specialist/run`, the Catalog
  screen's "Run specialist" panel and `python -m cancer_workbench specialist run`.
  Each returns a feature vector, not a prediction, with the weight, processor and
  input-image hashes it was computed from. Example and checks:
  [C-specialist-adapter.md](C-specialist-adapter.md). Both embeddings for
  IMG000001 equal the stored baseline features bit for bit.
- **Rejections are observed, not invented**: unknown image, path outside the data
  folder, wrong modality and catalog-only models all return `rejected` with the
  reason. Under plain `python3` the router shows both encoders as blocked
  ("adapter … is not installed in this process").
- **Bound feature caches**: the exploratory baseline was re-run with
  hash-bound features (`runs/btxrd-baseline-20261024T223701Z` reproduces the
  original table exactly; `…T230951Z` adds the reviewed duplicate pair). Images
  screen live scoring works again on these runs and refuses training images.
- **Knowledge for retrieval**: 10 cards in `catalog/cards.json` (returned by
  `get_record`) and 6 researcher workflows in `catalog/workflows.json` (new
  `get_workflow` tool). Both are Claude-written: retrieval only, not training text.
- **Near-duplicate review**: IMG002677/IMG002686 confirmed as one radiograph and
  grouped (`catalog/reviews/btxrd-same-image.json`).
- **Phone layout**: all seven screens fit 390 px in dark and light.
- Tests: 320 discovered; ML environment all pass with 5 opt-in skips, plain
  Python 49 skips. `CW_MODEL_TESTS=1` real-weight tests pass.

## Commits on the branch

| Commit | Change |
|---|---|
| `048b6fb` | Encoder adapters, catalog promotion with terms review, router installed-blocker, app endpoint and panel, CLI, cards, workflows, curriculum capture code |
| `b6f7ad8` | Captured 37 curriculum candidates (removed again in `2e1bb0f`) |
| `6ee3292` | Reviewed same-radiograph pair joins a duplicate group in the BTXRD manifest |
| `d7a43cc` | Phone-width fixes |
| `2e1bb0f` | Removed the Claude-written curriculum data; responses must name their author |

Two teammates' checks were adjusted to follow the catalog and tool-list changes:
Inam's `tests/test_hosted_profile.py` (RAD-DINO evidence state now read from the
catalog) and the `unknown-tool` expectation in `configs/coordinator-evaluation.json`
(adds `get_workflow`).

## What has to be done

| # | Task | Who | Notes |
|---|---|---|---|
| 1 | Review and merge `sebastian/encoder-specialist` | Inam or Jordi, opened by Sebastian | `gh` is not installed on this machine; open the PR on GitHub. The branch history still contains the removed curriculum files; it will be replaced, so no rewrite is planned |
| 2 | Decide where coordinator training conversations come from | Team (Jordi leads the Gemma round) | Either people write requests and answers (format in `curriculum/README.md`), or someone checks Anthropic's terms on training other models with Claude output against this research use. Apply the same check to any model-written answers in Jordi's 44 + 12 candidates |
| 3 | Rights reading for the two runnable encoders beyond inference | Team | RAD-DINO "research purposes only" for fitted heads, fine-tunes and sharing; whether ImageNet-1k terms reach ResNet-50's derived weights. Adaptation, redistribution and distillation stay `unreviewed` until then |
| 4 | Look at IMG000155/IMG000157 | Sebastian or a data reviewer | Same hip and pose; pixel match 0.97, not conclusive. If one radiograph, add it to `catalog/reviews/btxrd-same-image.json` and rebuild the manifest |
| 5 | Review the remaining near-duplicate candidates (ranks 38 onward) | Data reviewer | Ranks 22–37 and 42 are done; group only same-radiograph pairs, never same-patient views (Hub D04) |
| 6 | Subset label reviews | Sebastian | GDC open-access terms for TCGA-SARC; RTSTRUCT ROI names and outcome columns in `INFOclinical_STS.xlsx`; per-row pathology reference standard in CBIS-DDSM's case-description CSVs. Nothing fetched yet |
| 7 | Re-extract the source-shift variants | Sebastian, when needed | Only `pad` caches are bound; `pad_pstretch` and `native_crop` runs stay replay-only (about 25 min per RAD-DINO variant) |
| 8 | Remaining visual QA | Sebastian | Model profile editing and a running download were not exercised |
| 9 | Fix the Hub model register | Its owner, on Sebastian's proposal | Lists ResNet-18 and "not acquired"; the runnable pair is RAD-DINO and ResNet-50 |
| 10 | Unchanged blockers | Team | Patient/lesion mapping and per-row reference standard for BTXRD (custodian request drafted, unsent); endpoint decision (Q02); MedSigLIP HAI-DEF terms; independent review of `66562ea`/`7abd79a` |

## For the next Gemma round

Give the coordinator the installed adapters (the app does this) and use
`get_record`, `route_models`, `get_workflow` and `run_specialist` as its tools.
The cards and workflows are for retrieval. There are no training candidates from
this branch until item 2 is settled.

## One sentence for Inam

RAD-DINO and ResNet-50 now run through the real `run_specialist` path (Catalog
panel, assistant and CLI) and return hash-bound embeddings that match the stored
baseline features exactly; they are research-use feature extractors, not
diagnostic models.
