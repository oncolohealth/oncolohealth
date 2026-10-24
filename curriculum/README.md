# Coordinator curriculum candidates

This folder holds candidate tool-use conversations for the coordinator. It is
empty on purpose: the first batch (37 conversations, October 24) was removed
because its researcher prompts and every final answer were written by Claude.
Training the Gemma coordinator on Claude-written answers would make Claude a
teacher model, and Anthropic's terms may restrict using Claude's output to
train other models. Whether that covers this research use has not been checked.

## Format

| File | Who writes it |
|---|---|
| `scenarios.json` | A person: `{"scenarios": [{id, family, lineage_group, split, user, turns: [[{name, arguments}, ...], ...]}]}`. `split` is `train_candidate`, `development` or `evaluation_reserved`, assigned per lineage group |
| `responses.json` | A person, after reading the observed results: `{"responses": {id: {response, response_author, response_for}}}`. `response_for` is the candidate's `observed_digest`. A response without `response_author` counts as missing |
| `candidates.jsonl`, `manifest.json` | `.venv/bin/python -m cancer_workbench curriculum capture` |

Capture replays the scripted calls through the coordinator's real loop, so tool
results are observed, not invented. Every candidate starts `review.status:
pending` and `rights_status: pending`, and its rights note names the response
author. `curriculum.export_curriculum` returns only reviewed, rights-cleared
`train_candidate` records with a named response author and fresh results.

Reconcile with Jordi's 44 training and 12 development candidates and keep the
original 83/21 pilot intact before admitting anything.
