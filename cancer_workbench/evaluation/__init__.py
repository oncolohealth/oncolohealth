"""Evaluation protocol and metrics. Owner: Workstream F. STUBS: contracts only.

metrics.binary_report(y_true, scores, threshold, group_ids=None) -> dict
    sensitivity, specificity, precision, ROC-AUC, PR-AUC, confusion matrix,
    with bootstrap CIs resampled BY GROUP (patient) when group_ids are given.
metrics.calibration(y_true, probs, n_bins=10) -> dict          ECE + reliability bins
thresholds.choose_threshold(y_true, scores, rule) -> float      development data only
aggregate.patient_level(rows, how="max"|"mean") -> rows         explicit image->patient rule
leakage.check(train_rows, eval_rows, pretraining_refs) -> list  sample/patient/source overlap

Rules: never select models, thresholds, preprocessing or augmentation on test data.
"""
