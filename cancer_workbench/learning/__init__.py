"""Transfer learning and distillation. Owner: Workstream E. STUBS: contracts only.

features.extract_features(encoder_id, manifest_rows, data_root, out_path) -> FeatureFile
    Run a frozen encoder from models/<encoder_id>/ over manifest rows and write
    an .npz with: sample_ids, patient_ids, partitions, labels, features (N x D),
    plus encoder id + revision + preprocessing hash. Requires the `ml` extra.

heads.train_feature_head(data, *, epochs=100, learning_rate=0.05, teacher_weight=0.0) -> HeadModel
    Train a small classifier on TRAIN rows only. data must declare encoder ref,
    ordered classes, reference labels; with teacher_weight > 0 also teacher id,
    aligned per-sample probabilities in the same class order, and permission.

heads.evaluate_head(model, data) -> dict
    Refuse if eval rows share sample/patient ids with training rows or the
    encoder/class order differs. Return predictions for evaluation.metrics;
    do not compute headline metrics here.
"""
