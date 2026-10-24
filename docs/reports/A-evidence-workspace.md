# Dataset evidence workspace follow-up

Inam Qasimi · October 24, 2026 · based on combined main `e22234c`.

The shared root now contains Jordi's offline release audit and evidence-return
checker alongside Inam's evaluation/planning/provenance implementation and
Sebastian's encoders, exploratory runs and desktop integration. The Hub's old
role entries still described Inam's source as unavailable or unmerged. Those
entries were corrected with concrete commit references, preserving teammate
credit and the distinction between software delivery and a medical study.

## Implemented in this follow-up

The existing Datasets screen now shows a read-only **BTXRD evidence review**.
Researchers can find source label counts, exact-copy conflicts, the recorded
missing grouping/reference evidence, next review actions and snapshot hashes.
The blank evidence template can be exported for the data-review handoff.

This surfaces the published audit/evidence reports already added by Jordi; it
does not rerun their real-archive audit. It adds no new medical findings. The
panel states that it is a published snapshot and does not check the user's
current archive, pixels, model weights or returned evidence file. Local manifest
audits and the existing explicit `btxrd-review` CLI remain available separately.

`datasets/readiness.py` checks the three snapshot files against their recorded
publication byte counts/SHA-256 values, checks archive/count consistency and
requires the reports' non-authorizing evidence state. Hash agreement is a local
consistency check, not a signature or independent authentication of the report.
The historical publication manifest is used only for these unchanged published
report/template bytes; it is not treated as a manifest of the current source tree.

The JSON summary is an allowlist of aggregate counts and evidence state; it does
not return patient IDs, diagnostic-reference values or arbitrary report fields.
Template export accepts only the fixed published CSV with blank patient/lesion/
reference fields and unreviewed rows. Changed, malformed, escaping, oversized or
inconsistent files fail without presenting them as current readiness. The panel
degrades gracefully while local manifest audits continue to work.

Both new routes use the existing local server/token boundary:

- `GET /api/datasets/btxrd/evidence`
- `GET /api/datasets/btxrd/evidence-template`

No new write endpoint, acquisition, extraction, split, cohort, model load, job
dispatch or training is added. Opening the panel needs only the standard library.
`ready_for_training`, `execution_authorized`, medical-validation and verified
patient/reference states remain false. Existing planner gates are unchanged.

## Verification

The receiving main checkpoint was independently rechecked here: 243 discovered,
241 pass and two Torch preprocessing skips in the available ML environment;
system Python passes 203 with 40 optional-ML skips. These are environment-specific
counts, distinct from Sebastian's earlier all-218 supported-environment result.

Fourteen additional SYNTHETIC snapshot/CSV tests exercise immutable published reads, file identity and
archive/count disagreements, read/path limits, malformed/promoted evidence
states, private-field suppression, blank-only CSV export, duplicate/changed
template rows, graceful API fallback and operation without importing an ML
runtime. Full integrated follow-up counts and browser verification are recorded
in `PROGRESS.md` after the final checks. No actual archive rerun or medical
inference was performed for this follow-up.

## Handoff

Review this branch on top of `e22234c`; the prior demo-readiness bundle is already
ancestral to current main and should not be reapplied. The panel does not change
the underlying evidence: genuine patient/lesion mapping, per-row diagnostic
references, contradictory-label adjudication, visual-overlap/privacy review and
an agreed prospective protocol remain open. Sebastian's full Torch/runtime work
and an approved live coordinator endpoint remain separate prerequisites.

Final follow-up verification: 257 discovered, 255 pass/two Torch skips in the
available ML environment; system Python 217 pass/40 skips. Eight scripted
coordinator cases pass, catalog/profile parsing and JavaScript/whitespace checks
pass. Desktop browser panel loading, expanded review/provenance and coexistence
with the synthetic manifest audit were verified with no console errors. Template
CSV content is verified by API/library tests; a completed browser download and
phone/light-theme QA are not claimed.

## Subsequent local integration check

Combined 7405810 with the published identity-formatting guard a7f8ff4, preserving
both histories. Only the appended progress records conflicted; both were kept.
The integrated review branch discovers 267 tests: 265 pass/two Torch skips in
the available ML environment, or 227 pass/40 optional-ML skips in system Python.
This is a local candidate, not a merge into shared main.

At 390x844, dark and light panel layouts have no page-width horizontal overflow.
Desktop light mode and the export control were checked; the UI confirmed a
3,746-row blank-template export with no console errors/warnings. API/library
tests verify CSV contents; a completed downloaded file was not independently
inspected. Temporary viewport/theme changes were restored. Full Torch/runtime
and scientific prerequisites remain open. Other teams' readiness/coordinator
branches remain separate from this bounded integration.
