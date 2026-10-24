# F: Merged-checkout metric follow-up

Owner: Inam Qasimi. Based on merged main `bff6ea4`, preserving Sebastian's
Images workspace, saved heads and scoring recovery. No changes to the UI,
learning, coordinator, adapters, catalogs or shared manifest/types.

## Problem and resulting behavior

Legacy metric calls accepted misaligned arrays and missing group identifiers,
allowed non-finite scores, and could emit NaN or raise on an absent class.
Bootstrap results did not expose how many draws were unusable. Youden's
initial no-positive-prediction threshold was clipped from infinity to 1,
which changes predictions when a score is exactly 1.

The follow-up validates numeric class indices, aligned finite probabilities,
class column order, normalization, complete declared groups and option values.
Single-class binary ranking and multiclass aggregate metrics without all
classes are explicit nulls. Conditional confusion metrics with zero
denominators remain null. The compatibility key `pr_auc` is retained and
explicitly described as non-interpolated average precision.

Each metric's `bootstrap` report contains requested/valid draws, missing-class
and non-finite rejections, group count, seed and resampling unit. Intervals
require at least two groups, two valid draws and 80% valid draws. Unexpected
statistic errors propagate rather than becoming a successful empty interval.
These are operational safeguards, not coverage or power guarantees.

Threshold selection rejects undefined cohorts and invalid target/rule inputs.
It preserves the no-positive-prediction ROC point using the next finite float
above the maximum observed probability. This can be slightly greater than 1;
that sentinel correctly predicts no positives and remains strict-JSON safe.
The caller is still responsible for using development data only.

Baseline summaries render null metric/recall values as `undefined`. Existing
saved heads, stored thresholds and results are not recalculated. The new
patient aggregation/paired comparator still requires genuine grouping and a
reviewed protocol before integration into a scientific evaluation.

## Attribution

B/F ownership labels and the source-check note use Inam Qasimi. `.mailmap`
maps the earlier assistant author identity to the repository's configured
human email, and future branch commits use that identity. The mapping was
checked with `git check-mailmap`. Raw shared commit objects are not rewritten;
GitHub account-level attribution for a previously merged commit may require a
coordinated history correction, outside this local follow-up.

References: [Git author mapping](https://git-scm.com/docs/gitmailmap),
[GitHub contributor attribution](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-a-projects-contributors).

## Verification

24 new synthetic tests cover validation, missing classes/denominators,
bootstrap rejection accounting and cluster preservation, reproducibility,
calibration boundary bins, threshold targets/ties and no-positive decisions,
and binary/multiclass summary compatibility. Final environment-specific test
counts are recorded in PROGRESS.md. No medical workload, model training or
catalog promotion is part of this change.
