"""Exploratory BTXRD frozen-encoder baseline. Owner: Workstream B with E/F. Needs the `ml` extra.

For each split protocol x endpoint x encoder: fit a linear head on TRAIN, pick
its regularization (and, for binary endpoints, the decision threshold) on VAL,
report on TEST. BTXRD has no patient identifiers, so every result is
image-level and EXPLORATORY: views of one patient can sit on both sides of a
split. `source_holdout` keeps any such pair inside one source (center 1 trains,
centers 2 + 3 test) at the cost of measuring a source shift as well.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import platform
import subprocess
import time
from pathlib import Path

from ..acquisition.download import hash_file
from ..common.paths import PROJECT_ROOT
from ..datasets import audit_dataset, grouped_split, read_manifest, write_manifest
from ..datasets.btxrd import ENDPOINTS, MANIFEST_PATH, RAW_DIR, RELEASE
from .records import ExperimentRecord, JobState

ENCODERS = ("rad-dino", "resnet50-a1-in1k")
PROTOCOLS = ("image_stratified", "source_holdout")
CLASSES = {"three_class": ["normal", "benign", "malignant"], "tumor_vs_normal": ["normal", "tumor"],
           "benign_vs_malignant": ["benign", "malignant"]}  # binary: index 1 is the positive class
LABEL = "EXPLORATORY: image-level, no patient grouping, single source dataset. Not medical performance."
GROUPING = ("grouping: no patient ids; declared duplicate groups in image_stratified, centers held out in source_holdout; "
            "declared cross-partition overlap rejected before fitting")


def make_split(rows: list[dict], protocol: str, seed: str = "0") -> list[dict]:
    if protocol == "image_stratified":
        return grouped_split(rows, {"train": 0.70, "val": 0.15, "test": 0.15}, seed=seed)
    if protocol == "source_holdout":
        dev = grouped_split([r for r in rows if r["center"] == "1"], {"train": 0.85, "val": 0.15}, seed=seed)
        return dev + [dict(r, partition="test") for r in rows if r["center"] != "1"]
    raise ValueError(f"protocol must be one of {PROTOCOLS}")


def endpoint_rows(rows: list[dict], endpoint: str) -> list[dict]:
    """Relabel three-class rows for `endpoint`; drop unlabeled (quarantined) rows and rows outside the cohort."""
    mapping = ENDPOINTS[endpoint]
    return [dict(r, label=mapping[r["label_derived"]]) for r in rows if r["label"] and mapping[r["label_derived"]]]


def head_inputs(er: list[dict], f: dict, index: dict[str, int], endpoint: str) -> dict:
    """Training/evaluation arrays for `train_feature_head` from endpoint rows and a loaded feature cache."""
    import numpy as np

    idx = [index[r["sample_id"]] for r in er]
    col = lambda k: np.array([r[k] for r in er])
    return {"features": f["features"][idx], "labels": col("label"), "partitions": col("partition"), "sample_ids": col("sample_id"),
            "patient_ids": col("patient_id"), "group_ids": col("duplicate_group"), "classes": CLASSES[endpoint],
            "image_hashes": np.array([r.get("sha256", "") for r in er]),
            "encoder": {"encoder_id": str(f["encoder_id"]), "revision": f["revision"], "preprocessing_hash": f["preprocessing_hash"]}}


def rel(path: Path) -> str:
    """`path` relative to the project when it is inside it, else as given."""
    return str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path)


def _git_revision() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "cancer_workbench"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _environment(device: str) -> dict[str, str]:
    import numpy, sklearn, torch

    return {"python": platform.python_version(), "platform": platform.platform(), "torch": torch.__version__,
            "numpy": numpy.__version__, "scikit-learn": sklearn.__version__, "device": device}


def evaluate(head, data: dict, endpoint: str, n_boot: int) -> tuple[dict, dict, dict]:
    """VAL and TEST predictions, and the TEST report. A binary threshold is chosen on VAL and applied unchanged."""
    from ..evaluation.metrics import binary_report, calibration, multiclass_report
    from ..evaluation.thresholds import choose_threshold
    from ..learning.heads import evaluate_head

    val, test = evaluate_head(head, data, "val"), evaluate_head(head, data, "test")
    if len(CLASSES[endpoint]) == 2:
        pos = lambda pred: [p[1] for p in pred["probs"]]
        threshold = choose_threshold(val["y_true"], pos(val), "youden")
        report = binary_report(test["y_true"], pos(test), threshold, n_boot=n_boot)
        report["calibration"] = calibration(test["y_true"], pos(test))
        report["positive_class"] = CLASSES[endpoint][1]
    else:
        report = multiclass_report(test["y_true"], test["probs"], CLASSES[endpoint], n_boot=n_boot)
    return val, test, report


def record(record_id: str, endpoint: str, enc: str, f: dict, split: str, seed: str, preprocessing: dict, source_rev: str,
           manifest_sha: str, seconds: float, outputs: list[str], blockers: list[str],
           scope: str = "local laptop; exploratory image-level run authorized 2026-10-23") -> dict:
    """One completed `ExperimentRecord` (as a dict) for a fitted and evaluated head."""
    rec = ExperimentRecord(
        id=record_id, path="transfer_learning", task=f"btxrd_{endpoint}_image",
        cohort=f"btxrd {RELEASE}; manifest sha256 {manifest_sha}", split=split, model=f"{enc}@{f['revision']}",
        source_revision=source_rev, environment=_environment(str(f["device"])), preprocessing=preprocessing,
        objective="logistic regression on standardized frozen features, balanced class weights; C and threshold chosen on val",
        metrics=["roc_auc", "pr_auc", "sensitivity", "specificity", "calibration"] if len(CLASSES[endpoint]) == 2
        else ["macro_roc_auc", "balanced_accuracy", "per_class_recall"],
        seed_policy=f"split seed {seed}; bootstrap seed 0; lbfgs is deterministic",
        execution_scope=scope,
        state=JobState.COMPLETED,
        resource_profile={"feature_seconds": float(f["seconds"]), "feature_device": str(f["device"]),
                          "head_and_eval_seconds": round(seconds, 2)},
        outputs=outputs, blockers=blockers)
    return dict(dataclasses.asdict(rec), state=rec.state.value)


def run(encoders=ENCODERS, endpoints=tuple(CLASSES), protocols=PROTOCOLS, *, out_dir: Path | None = None,
        seed: str = "0", n_boot: int = 1000, features_dir: Path = PROJECT_ROOT / "runs" / "features") -> Path:
    from ..adapters.encoder import preprocessing, preprocessing_hash, revision
    from ..learning.features import cache_path, extract_features, load_features
    from ..learning.heads import save_head, train_feature_head

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"{MANIFEST_PATH} missing; run `python -m cancer_workbench btxrd manifest` first")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(out_dir or PROJECT_ROOT / "runs" / f"btxrd-baseline-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_manifest(MANIFEST_PATH)
    manifest_sha = hash_file(MANIFEST_PATH)["sha256"]
    source_rev = _git_revision()

    feats = {}
    for enc in encoders:
        path = cache_path(enc, "btxrd", features_dir)
        if not path.exists():
            extract_features(enc, rows, RAW_DIR, path)
        f = load_features(path)
        if f["preprocessing_hash"] != preprocessing_hash(enc) or f["revision"] != str(revision(enc)):
            raise ValueError(f"{path} was made with different preprocessing or weights")
        feats[enc] = (f, {sid: i for i, sid in enumerate(f["sample_ids"].tolist())}, path)

    results, records = [], []
    for protocol in protocols:
        split = make_split(rows, protocol, seed)
        split_path = out_dir / "splits" / f"{protocol}.csv"
        write_manifest(split_path, split)
        for endpoint in endpoints:
            er = endpoint_rows(split, endpoint)
            audit = audit_dataset({"id": "btxrd", "classes": CLASSES[endpoint]}, er)
            for enc in encoders:
                f, index, fpath = feats[enc]
                data = head_inputs(er, f, index, endpoint)
                t0 = time.monotonic()
                head = train_feature_head(data)
                val, test, report = evaluate(head, data, endpoint, n_boot)
                run_id = f"{protocol}.{endpoint}.{enc}"
                results.append({"id": run_id, "protocol": protocol, "endpoint": endpoint, "encoder": enc, "label": LABEL,
                                "C": head.C, "val_macro_roc_auc": head.val_score,
                                "counts": {p: sum(1 for r in er if r["partition"] == p) for p in ("train", "val", "test")},
                                "test": report})
                (out_dir / "predictions").mkdir(exist_ok=True)
                (out_dir / "predictions" / f"{run_id}.json").write_text(json.dumps({"val": val, "test": test}) + "\n")
                (out_dir / "heads").mkdir(exist_ok=True)
                save_head(head, out_dir / "heads" / f"{run_id}.npz")
                records.append(record(
                    f"{out_dir.name}/{run_id}", endpoint, enc, f, f"{split_path.name} ({protocol}, seed {seed}); {GROUPING}",
                    seed, preprocessing(enc), source_rev, manifest_sha, time.monotonic() - t0,
                    [rel(fpath), f"predictions/{run_id}.json", f"heads/{run_id}.npz"],
                    [x["detail"] for x in audit["findings"] if x["severity"] == "error"]))

    (out_dir / "results.json").write_text(json.dumps({"label": LABEL, "results": results}, indent=2) + "\n")
    (out_dir / "records.json").write_text(json.dumps(records, indent=2) + "\n")
    (out_dir / "summary.md").write_text(summary(results))
    return out_dir


def _fmt_ci(v, ci):
    if v is None:
        return "undefined"
    return f"{v:.3f} ({ci[0]:.3f}-{ci[1]:.3f})" if ci else f"{v:.3f}"


def _fmt_metric(v):
    return "undefined" if v is None else f"{v:.2f}"


def test_cells(t: dict) -> tuple[str, str]:
    """The ROC-AUC (95% CI) and decision-summary cells of a summary table for one TEST report."""
    if "roc_auc" in t:
        return (_fmt_ci(t["roc_auc"], t["roc_auc_ci95"]),
                f"sens {_fmt_metric(t['sensitivity'])}, spec {_fmt_metric(t['specificity'])} ({t['positive_class']} positive)")
    return (_fmt_ci(t["macro_roc_auc"], t["macro_roc_auc_ci95"]) + " macro",
            f"bal. acc {_fmt_metric(t['balanced_accuracy'])}; recall " + ", ".join(f"{c} {_fmt_metric(v)}" for c, v in t["recall"].items()))


def summary(results: list[dict]) -> str:
    lines = [f"**{LABEL}**", "", "| Protocol | Endpoint | Encoder | Test n | ROC-AUC (95% CI) | At val threshold / argmax |",
             "|---|---|---|---|---|---|"]
    for r in results:
        t = r["test"]
        auc, dec = test_cells(t)
        lines.append(f"| {r['protocol']} | {r['endpoint']} | {r['encoder']} | {t['n']} | {auc} | {dec} |")
    lines += ["", "CIs resample images, so they are too narrow if images share patients."]
    return "\n".join(lines) + "\n"
