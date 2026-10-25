# Live Claude coordinator run

Inam Qasimi · October 24, 2026, 8:48 PM PDT (`20261025T034822Z`) · branch
`inam/coordinator-ipv6-fallback` on main `15d79e2`. Software and workflow
evidence only; nothing here is a medical result.

## Setup

- Profile `claude-research` (`configs/coordinator.example.json`), model
  `claude-opus-5-5` through Anthropic's OpenAI-compatible endpoint
  (`https://api.anthropic.com/v1`), key from `ANTHROPIC_API_KEY` in the shell,
  paid from Cal Hacks hackathon API credits.
- Local `configs/coordinator.json` (gitignored) raised `max_tokens` to 8000
  (Claude 5 thinking is always on and counts toward it) and `timeout_s` to 180.
- The provider now uses the download code's IPv6-to-IPv4 connection fallback.
  On the network used, `api.anthropic.com` resolves an IPv6 address but IPv6
  traffic is dropped; without the fallback every request waited out its full
  timeout before trying IPv4. Regression:
  `test_requests_use_the_ipv6_to_ipv4_connection_fallback`.
- The CLI tool box has no installed specialist adapters, so `run_specialist`
  is expected to refuse.

## Researcher workflow (one question)

Question: could RAD-DINO features support a BTXRD baseline; check whether it
can run here via `run_specialist` on `btxrd:IMG000001`; say what is missing.

4 requests, 30.3 s, 10,069 input / 2,234 output tokens. Tool calls, in order:
`search_catalog` ×2, `get_record("rad-dino")`, `search_catalog`,
`get_record("btxrd")`, `route_models(feature_extraction, xray, bone)` (5
compatible encoders, none runnable), `run_specialist("rad-dino", …)` →
`rejected` with `evidence_state is 'cataloged'`, `inference_permission is
'unreviewed'`, `no adapter installed`.

The answer reported the rejection exactly ("No embeddings were produced, so I
have no results to give you") and listed the blockers: adapter, permission
review, local reproduction, chest-only pretraining, missing patient grouping,
duplicate/label conflicts, mixed reference standard and class imbalance. Every
specific identifier and count in the answer appears in the observed tool
results. Answer quality was read by a person, not scored.

## Live evaluation suite

`scripts/evaluate_coordinator.py --mode live --profile claude-research`, suite
`coordinator-development-v1`: **6 of 6 cases pass** (12 requests, 61.6 s,
15,389 input / 4,543 output tokens). Cases: catalog-evidence,
catalog-refusal, synthetic-success, synthetic-failure, unknown-record,
multiple-tool-feedback. The suite checks expected tool-call results and that
each observed result is fed back to the model; it does not score reasoning
or answer quality.

## Limits

One question and six scripted development cases, one run each. No medical
inference, no patient data, no specialist execution. The OpenAI-compatible
layer does not return Claude's thinking and is documented by Anthropic as a
testing path; a production deployment would use the native Claude API.
Run files (`run-info.txt`, `demo-transcript.json`, `live-eval.json`) are in the
gitignored `runs/claude-live/20261025T034822Z/` on Inam's machine.
