"""Evaluation protocol and utilities. Owner: Workstream F.

metrics.binary_report(y_true, scores, threshold, group_ids=None) -> dict
    sensitivity, specificity, precision, ROC-AUC, PR-AUC, confusion matrix,
    with bootstrap CIs resampled BY GROUP (patient) when group_ids are given.
metrics.calibration(y_true, probs, n_bins=10) -> dict          ECE + reliability bins
thresholds.choose_threshold(y_true, scores, rule) -> float      development data only
aggregate.patient_level(rows, how="max"|"mean") -> rows         explicit image->patient rule
leakage.check(train_rows, eval_rows, pretraining_refs) -> list  sample/patient/source overlap
comparison.paired_binary(arm_a, arm_b, ...) -> dict             paired patient-cluster ranking deltas

Rules: never select models, thresholds, preprocessing or augmentation on test data.
Aggregation, overlap checks and paired comparisons require only the standard
library. Metrics/thresholds use the optional ML extra. See the F protocol for
row schemas, limitations and the distinction between image and patient estimands.
"""
