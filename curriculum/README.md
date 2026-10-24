# Coordinator curriculum candidates

Candidate tool-use conversations for the next coordinator round. **None is
admitted to training.** Every candidate is `review.status: pending`,
`rights_status: pending` and `admitted_to_training: false`.
`curriculum.export_curriculum` returns only reviewed, rights-cleared
`train_candidate` records with fresh responses, so today it returns nothing.

| File | What it is |
|---|---|
| `scenarios.json` | 37 researcher requests and the tool calls made for them, with family, lineage group and split |
| `responses.json` | Drafted final responses, each tied to the digest of the observed results it was written against |
| `candidates.jsonl` | Captured candidates: messages exactly as `run_turn` produced them, plus per call the id, typed arguments, exact tool schema, result id and observed result |
| `manifest.json` | Counts, git commit, catalog/card/workflow file hashes, installed adapters, candidates-file hash |

Regenerate with `.venv/bin/python -m cancer_workbench curriculum capture`.
Tool results are real: catalog lookups, routing, workflows, and two real
encoder runs on BTXRD images. If a recapture observes different results, the
candidate becomes `stale_response`, and its response must be reread and
restamped by a person.

## Splits

| Split | Count | Use |
|---|---|---|
| `train_candidate` | 26 | May be trained on after review |
| `development` | 5 | For iterating on prompts and tools; not training |
| `evaluation_reserved` | 6 | Held back for the next round's evaluation; never train on these |

Splits are assigned per lineage group, and capture refuses a group that spans
splits.

Families: specialist kinds (7), dataset audit (8), training recipe (6),
failure handling (9), research reading (4), reuse path (3).

## Provenance and limits

- Thinking mode: off. Calls are scripted and responses drafted by Claude Code
  (Claude Opus 5.5) after reading the observed results. No reasoning trace is
  recorded.
- No patient identifiers. Images are referenced by BTXRD sample id (CC BY 4.0).
  Embedding outputs carry an 8-value preview and a hash, not the vector.
- No accuracy claims. Responses quote only what the call results in the same
  conversation show.
- Not yet reconciled with Jordi's 44 training and 12 development candidates or
  the original 83/21 pilot, which are not on this machine. De-duplicate by
  lineage before admitting anything, and keep the 83/21 pilot intact.
