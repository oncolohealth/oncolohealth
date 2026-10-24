# Coordinator development evaluation

Inam Qasimi · October 24, 2026

Run the offline smoke suite from the repository root:

```bash
python3 scripts/evaluate_coordinator.py --out runs/coordinator-smoke-01.json
```

It executes eight public, deterministic development scenarios against the actual
catalog and toolbox: evidence lookup, catalog execution refusal, synthetic
success/failure, unknown record, invalid argument type, unknown tool and multiple
tool-result feedback. Only synthetic adapters are installed in this harness,
even if medical artifacts exist elsewhere on the machine. No ML package,
credential, network request or medical execution is needed in smoke mode.

To evaluate a configured endpoint when API use is authorized:

```bash
python3 scripts/evaluate_coordinator.py --mode live --profile claude-research --limit 1 --out runs/coordinator-live-01.json
```

Live mode selects six applicable public development scenarios. The two
intentionally malformed contract cases are smoke-only. Live requests may incur
provider charges. Use `--limit` and `--max-steps` (1–8) to bound the run, and the
profile's timeout/token settings to bound individual requests. A new profile is
constructed for each independent case. No live run was performed here.

## What a pass means

A trace pass requires the specified actual tool result, matching declared
argument constraints, feedback in a subsequent provider request, an answered
turn and a nonempty final answer. An answer claiming success without using a
tool fails. Provider errors and step exhaustion cannot pass. Errors retain
partial observed tool traces so a failed second request does not erase the
first tool's result. Output files use exclusive creation and are not overwritten.

This is not a semantic judge. It does not establish that the final answer is
correct, properly cited, clinically appropriate or free of unsupported claims.
`answer_review` is `unscored`, and `reasoning_quality_score` is null. Smoke mode
also leaves `trace_pass_rate` null to avoid presenting scripted completions as
model performance. A live trace rate includes failed/error cases in its
denominator. These public fixtures are not held-out evaluation data.

## Comparing profiles

Each schema-version-1 report records suite ID/hash, catalog hash, system-prompt
hash, UTC time, mode, step bound, actual returned model/profile, provider latency,
usage and observed calls. It excludes auth headers, credentials, raw responses
and private reasoning. Retain the exact configuration and source commit with
each experiment separately. Compare only like suite/catalog/prompt versions,
and disclose sampling parameters, provider revisions, errors and repetitions.

Review each final answer against its observed trace. Record reviewer, date,
unsupported claims, preserved refusals/failures, synthetic labeling and scope
errors. Keep this human assessment separate from the automated trace score.
Before claiming generalization, freeze a separate unseen workflow suite and
review rubric before testing. The earlier 14-case review proposal remains a
broader specification; unsupported retrieval, coding and patient-reasoning
scenarios were not silently marked executed by this smaller harness.
