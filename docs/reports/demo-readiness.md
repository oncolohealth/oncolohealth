# Execution checks and demo readiness

Inam Qasimi · October 24, 2026

This follow-up builds on `df45e788b3eebb55e722bdc795f8ce633df1cb2f` and integrates
latest pushed main `acb8e298e196cb86187d879b00a25bc1c50a2cd9` on a separate
`codex/demo-readiness` branch. It addresses remaining source findings
without downloading data or weights, choosing a scientific endpoint, or
changing the exploratory Images scoring route.

## Implemented

- E: Validate feature geometry, numeric/finite values, aligned columns, unique
  nonempty sample identities, class declarations, encoder identity, split names,
  train/validation class coverage and positive finite regularization options
  before constructing or fitting a learner. Reject declared patient, duplicate
  group or image-hash overlap across partitions. The BTXRD input builder now
  carries duplicate groups and SHA-256 identities from the manifest into this
  check. Existing source-holdout data with cross-center duplicates will refuse
  fitting until the split is corrected and re-audited.
  New experiment records describe the actual declared-duplicate/source grouping
  instead of incorrectly saying every image is its own group. Historical records
  and reported results are unchanged.
- C: Convert an exception in adapter input validation into a failed observed
  result envelope, preserving model/input identity and synthetic provenance.
  Ordinary validation findings remain rejected results. Do not call `run`
  after validation throws.
- D: Validate tool argument types and enums, nested objects/array items,
  required/unknown properties, finite JSON values, declared lengths and numeric
  bounds before invoking a handler. No type coercion. Keep the top-level closed
  argument contract and nested open-object behavior unless explicitly closed.
  This is a documented subset for the schemas used here, not full JSON Schema.
- Offline fallback: `python3 scripts/demo_observed_results.py` executes a real
  catalog lookup, catalog-only refusal, argument rejection, synthetic success,
  synthetic failure and a scripted coordinator feedback cycle. It asserts those
  states before emitting JSON. It does not demonstrate live model reasoning.

## Verification

Eighteen new synthetic regression tests pass. They assert that learners and
handlers are not invoked after invalid input, and that failures preserve their
observed-result metadata. Existing binary/multiclass saved-head round trips and
learning tests continue to pass in the available ML environment.

Full integrated suite in the temporary NumPy/scikit-learn environment: **146 tests,
144 passed, 2 skipped** (Torch preprocessing unavailable). Plain Python:
**146 tests, 106 passed, 40 optional-ML skips**. The initial full run
could not bind localhost sockets inside the sandbox. After the network grant,
the full suite passed. These are software checks, not medical findings.

## Concurrent team-work integration

While this branch was being prepared, Sebastian pushed overlapping pre-fit
checks, preprocessing variants, source-shift evaluation, near-duplicate search
and CI to main. Those changes are retained. The public `validate_head_inputs`
API, canonical `group_ids` metadata, and acceptance of unassigned rows remain
compatible. Unassigned rows never enter fitting or contribute cross-partition
overlap. The stricter shared checks add encoder/string/hash and regularization
validation without introducing a second fitting route.

The shared `evaluate`, `record`, `rel` and `test_cells` helpers remain in place.
Null-safe formatting now applies through `test_cells` to both baseline and
source-shift reports, with a new plain-Python integration regression. Both
workstreams' documentation and tests are retained. Earlier 139-test counts
describe the pre-integration checkpoint.

The Hub additionally reports unpushed `c13a74a` Images/preprocessing changes.
Those unavailable changes are not claimed as integrated or tested here. The
branch must still be reviewed against that checkout before its eventual merge.

## Remaining limitations

Missing patient identities remain unknown and are still allowed only in the
existing explicitly exploratory path. Declared duplicate checks do not detect
near duplicates or unrecorded patient overlap. This change does not create an
independent cohort, approve a protocol, establish an endpoint or reference
standard, or promote a catalog model. Existing saved heads are not retrained or
rewritten, and no existing reported scores were reproduced here.

The local app still needs HTTPS/access controls, persistent shared job state and
storage, and a reviewed server configuration for public cloud use. Tiger Data,
Vultr, Claude and the Droid SDK are proposed integrations, not implemented ones.
Live coordinator evaluation, reviewed specialist promotion and an experiment
runs screen remain open. No cloud resource was provisioned.

## Review and integration

The branch is separate from the user's source checkout. Review the source diff
and run the full Torch/ML environment before merging. Its history includes the
earlier evaluation follow-up; fetch the bundle into a new branch and merge by
Git ancestry rather than applying both versions of the same patch.
