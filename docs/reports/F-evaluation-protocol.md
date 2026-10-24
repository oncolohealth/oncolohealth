# F: Evaluation protocol and executable checks

Owner: Codex, taking over unclaimed F utilities and protocol drafting. This is
a **review draft**, aligned with source commit
`7d4bf64c47946439691bcaa02883aebb2ec296d2`; it does not resolve the lead's open
endpoint decision (Hub Q02) or approve a medical model. New tests use synthetic
scores and identifiers only. Existing collaborator baseline results have not
been reproduced in this checkout.

## Cohort and endpoint lock

Before a confirmatory run, record the dataset/release, manifest SHA256, eligible
population, exclusions, reference standard and one primary endpoint. Existing
code supports normal/benign/malignant, tumor versus normal (tumor positive),
and benign versus malignant (malignant positive). Its three-class default is
not an endpoint decision. Keep the four images in the two conflicting exact
duplicate pairs quarantined. Retain an exclusion log and class counts for each
partition and source; do not infer patient or lesion IDs from adjacent rows,
age, sex or center.

BTXRD's public metadata lacks patient IDs according to the repository's source
inventory. Patient independence is unverified. The new patient utilities
cannot be used on it until genuine grouping and a patient reference endpoint
are available. Byte-identical groups reduce one leakage mechanism; they do not
identify all repeated views or patients. Near-duplicate review and reference
standard adjudication remain outstanding.

## Existing exploratory recipe, preserved

| Element | Implementation in this repository |
|---|---|
| Arms | Frozen RAD-DINO and `resnet50-a1-in1k`; pin actual weight revision, processor settings and preprocessing hash |
| Image policy | Grayscale, full image padded to square with black, resized, replicated to three channels, encoder mean/std; RAD-DINO 518 px, ResNet-50 288 px |
| Head | Train-only feature mean/std; balanced L2 logistic regression, lbfgs, max_iter 5000 |
| Selection | C grid `0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1`; val ROC-AUC (macro OvR for multiclass), smaller C wins ties |
| Image split | 70/15/15 train/val/test; declared patient/duplicate groups retained where present, then sample fallback |
| Source holdout | Center 1 split 85/15 for train/val; centers 2 and 3 test; source-shift exploration, not proof of independent patients |
| Threshold | Binary Youden rule on val only; multiclass argmax |
| Randomness | Split seed recorded (default string `0`), bootstrap seed 0; keep identical split and endpoint membership across arms |

Preprocessing, C grid, calibration and thresholds must be frozen before the
next untouched evaluation. Because previous test/source-holdout results are
already visible, subsequent choices informed by those results are exploratory;
a new untouched evaluation cohort is required for confirmation. Do not select
a favorable endpoint, center, preprocessing or seed after viewing its results.

## Binary patient aggregation

`evaluation.aggregate.patient_level(rows, how="max"|"mean")` requires unique
`sample_id`, nonempty declared `patient_id`, binary `label` (0/1), and finite
`score` in [0,1]. An optional `partition` must agree within a patient. It emits
patient ID, label, aggregate score, partition, image count and contributing
sample IDs. Empty input, missing IDs, duplicate samples, conflicting labels and
patients spanning partitions raise `ValueError`.

Choose max or mean on clinical/protocol grounds before evaluation; neither is
established as appropriate for BTXRD by this work. A patient with discordant
image labels needs an adjudicated patient target first. The helper refuses to
invent that target. This API currently supports binary scores only, not
multiclass aggregation or lesion-level evaluation.

## Overlap assessment

Run `evaluation.leakage.check(train_rows, val_rows, refs)` and separately against
test, plus val versus test. Exact shared sample IDs, declared patients,
duplicate groups and SHA256 values are errors; empty partitions and repeated
sample IDs within a partition are errors. Missing patients remain visible.
Shared dataset or documented source IDs are warnings about provenance, not
automatic proof of case leakage. `source` is a globally meaningful source
identifier, not BTXRD's local numeric `center` column.

Pretraining refs have this explicit shape:

```json
[{"id": "review-id", "citation": "source URL or artifact reference",
  "coverage": "partial", "dataset_id": "namespace",
  "records": [{"sample_id": "source-id", "sha256": "declared-digest"}]}]
```

Pretraining sample/patient matches require the same dataset namespace; hashes
can match across namespaces. An exact match on eval is an error; training reuse
is a warning requiring protocol review. Shared provenance prompts case review.
Unstructured citations, absent/empty records, or partial coverage remain
unresolved. No match proves only that the supplied identifiers did not match;
it does not certify independent patients or absent pretraining exposure.
RAD-DINO's chest-domain description alone is not a completed overlap audit.
The public training inventory and BTXRD source identities still need review.

## Metrics, pairing and uncertainty

Report endpoint membership, positives/negatives, prevalence, exclusions,
ROC-AUC, **average precision**, and sensitivity/specificity/PPV/NPV at the locked
development threshold. Include confusion counts, reliability-bin counts and
ECE; fit any calibrator on development data only. Existing `metrics.py` uses
`pr_auc` to store scikit-learn average precision: label that quantity explicitly
in reports. AP uses recall increments rather than trapezoidal interpolation,
as documented in [scikit-learn's AP reference](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html).
Single-class subgroup ranking metrics must be marked undefined, not zero.

`evaluation.comparison.paired_binary(a, b, n_boot=1000, seed=0, min_valid=100)`
requires identical sample sets, labels, patients and one partition across
arms. It reports arm metrics, **B minus A**, and paired percentile 95% intervals.
Each draw samples patients with replacement, retains all their views and draw
multiplicity, and applies exactly the same draw to both arms. Blank groups are
rejected; image resampling is never substituted. Input order cannot change the
seeded result. Scores must be finite probabilities in [0,1]. ROC-AUC gives half
credit to ties; AP groups equal scores at the same threshold.

These are **image-weighted ranking estimates with patient-cluster uncertainty**.
They are not patient-level estimates. For a reviewed patient endpoint, aggregate
first, map each patient result to one prediction row (`sample_id=patient_id`),
and then compare. Do not mistake longer multi-view patient series for additional
independent patients.

The new comparison counts single-class draws and withholds intervals unless
there are at least two groups, at least `min_valid` valid draws, and at least
80% valid draws. Both ranking metrics are withheld for single-class cohorts.
These are operational safeguards, not a power analysis or validated coverage
guarantee. Report patient counts and invalid draws; small/sparse subgroups can
remain uninterpretable. No p-value, multiplicity correction or equivalence
claim is implemented.

The older `metrics.py` bootstrap still uses images when groups are absent and
does not report invalid-draw counts. It is unchanged in this patch and requires
further input/non-finite/bootstrap hardening. The existing baseline does not
automatically call the new utilities; patient/source enrichment and a reviewed
protocol must precede that integration.

## Error-review sheet

Use one row per reviewed case; reviewers should be blinded to arm identity
where feasible. An empty template is included in `F-error-review-template.csv`.

Record run/manifest/split/model revisions, sample/patient/source, age band,
anatomy and view, reference label and its provenance, both scores, locked
threshold, error type, quality/artefact flags, adjudication and reviewer.
Use `unknown` for unavailable metadata. Predefine source, age, anatomy and view
subgroups, report denominators and uncertainty, and suppress unsupported
comparisons. Record discordant arms and every false negative; do not silently
relabel or exclude errors. Changes from review create a new dataset version and
new development cycle, not a correction to a reported test score.

## Verification and remaining work

22 new stdlib synthetic evaluation tests cover aggregation, cross-split and
pretraining overlap, namespace handling, paired identity/direction, tied scores,
cluster resampling, undefined metrics and reproducibility. One test includes
1,134 exhaustive four-row cases against independent pair-count AUC and
threshold-integration AP oracles. Eight additional planner tests cover draft
gates. This is software evidence only.

Needed for scientific progression: primary endpoint decision; genuine patient
mapping or a defensible independent cohort; reference-standard adjudication;
near-duplicate/source/pretraining inventory review; a reviewed protocol and
untouched evaluation set; measured resource records. No catalog evidence state
or real model execution permission was changed.
