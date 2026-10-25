"""Exploratory image review and scoring with a BTXRD baseline run. Owner: Workstream B with E.

Replay (standard library): a run's stored val/test probabilities joined with
its split, so single images can be looked at and errors sorted. Live scoring
(`ml` extra): embed chosen images with the run's frozen encoder and apply the
run's head, preprocessing images with the variant the head was trained on
(`pad` unless the result names another). A head comes from `runs/<run>/heads/`.
Only measured-input-bound runs can load or rebuild a head for live scoring.
Rebuilding checks the input binding, stored val probabilities and fitted-array
fingerprint. Legacy runs retain stored-prediction replay.

This path deliberately does not go through `execute_specialist`: no catalog
model is cleared to run, and these heads are image-level exploratory results.
Every response carries LABEL, and the coordinator's tool box never calls it.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..common.paths import PROJECT_ROOT, RUNS_DIR
from ..datasets import read_manifest
from .btxrd_baseline import CLASSES, LABEL, endpoint_rows, head_inputs

MAX_SCORE = 24
NOTE = ("Exploratory software output from an image-level baseline. Not a diagnosis and not a validated model. "
        "Hand-picked images are not a random sample: use the run's test-set report for performance.")

_LOCK = threading.Lock()
_ENCODERS: dict = {}
_HEADS: dict = {}


def run_dir(run: str) -> Path:
    if not run or any(c in run for c in "/\\") or run.startswith("."):
        raise ValueError("Unknown run.")
    d = RUNS_DIR / run
    if not (d / "results.json").is_file():
        raise ValueError(f"No run named {run!r} with a results.json.")
    return d


def _result(d: Path, result_id: str) -> dict:
    for r in json.loads((d / "results.json").read_text())["results"]:
        if r["id"] == result_id:
            return r
    raise ValueError(f"Run {d.name} has no result {result_id!r}.")


def decide(probs: list[float], classes: list[str], threshold: float | None) -> str:
    """Binary: positive (index 1) when its probability >= the val threshold, as in `binary_report`. Else argmax."""
    if len(classes) == 2 and threshold is not None:
        return classes[1] if probs[1] >= threshold else classes[0]
    return classes[max(range(len(probs)), key=probs.__getitem__)]


def list_runs() -> list[dict]:
    from ..learning.provenance import valid_sha
    out = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True) if RUNS_DIR.exists() else []:
        if not (d / "results.json").is_file():
            continue
        res = json.loads((d / "results.json").read_text())
        out.append({"id": d.name, "label": res.get("label", ""), "results": [
            {"id": r["id"], "protocol": r["protocol"], "endpoint": r["endpoint"], "encoder": r["encoder"], "counts": r["counts"],
             "variant": r.get("variant"), "selected": r.get("selected"),
             "roc_auc": r["test"].get("roc_auc", r["test"].get("macro_roc_auc")), "macro": "macro_roc_auc" in r["test"],
             "threshold": r["test"].get("threshold"), "has_head": (d / "heads" / f"{r['id']}.npz").exists(),
             "has_binding": valid_sha(r.get("feature_binding_sha256")) and valid_sha(r.get("head_fingerprint"))}
            for r in res["results"]]})
    return out


def review(run: str, result_id: str) -> dict:
    """Every split row with its partition and endpoint label; val/test rows also get stored probs, prediction, correctness."""
    d = run_dir(run)
    r = _result(d, result_id)
    classes, threshold = CLASSES[r["endpoint"]], r["test"].get("threshold")
    split = read_manifest(d / "splits" / f"{r['protocol']}.csv")
    cohort = {x["sample_id"]: x for x in endpoint_rows(split, r["endpoint"])}
    rows = {}
    for x in split:
        if x["sample_id"] in cohort:
            rows[x["sample_id"]] = {"partition": x["partition"], "label": cohort[x["sample_id"]]["label"], "sha256": x.get("sha256", "")}
        else:
            why = "unlabeled (quarantined in the manifest)" if not x["label"] else f"outside the {r['endpoint']} cohort"
            rows[x["sample_id"]] = {"partition": "excluded", "label": "", "why": why, "sha256": x.get("sha256", "")}
    preds = json.loads((d / "predictions" / f"{result_id}.json").read_text())
    for part in ("val", "test"):
        p = preds[part]
        for sid, probs in zip(p["sample_ids"], p["probs"]):
            pred = decide(probs, classes, threshold)
            rows[sid].update(probs=probs, pred=pred, correct=pred == rows[sid]["label"])
    return {"run": run, "result": result_id, "label": LABEL, "protocol": r["protocol"], "endpoint": r["endpoint"],
            "encoder": r["encoder"], "variant": r.get("variant", "pad"), "classes": classes, "threshold": threshold,
            "positive_class": classes[1] if len(classes) == 2 else None, "rows": rows}


def _refit(d: Path, r: dict):
    """Rebuild a run's head from its saved split and the feature cache; refuse unless it reproduces the stored val probs."""
    import numpy as np

    from ..datasets.btxrd import RAW_DIR
    from ..learning.features import load_features, validate_feature_binding
    from ..learning.provenance import feature_binding, valid_sha
    from ..learning.heads import evaluate_head, train_feature_head

    name = r.get("feature_cache")
    if (not isinstance(name, str) or not name or name.startswith(".") or "/" in name or "\\" in name
            or not name.endswith(".npz") or not valid_sha(r.get("feature_binding_sha256"))):
        raise ValueError("Legacy run has no measured feature-cache reference. Replay stored results or regenerate the exploratory run.")
    fpath = (RUNS_DIR / "features" / name).resolve()
    if not fpath.is_relative_to((RUNS_DIR / "features").resolve()):
        raise ValueError("Feature-cache reference leaves the run cache folder.")
    if not fpath.exists():
        raise FileNotFoundError(f"{fpath.name} is missing, so the head can't be rebuilt. Re-run the baseline.")
    rows = read_manifest(d / "splits" / f"{r['protocol']}.csv")
    expected = feature_binding(r["encoder"], rows, RAW_DIR, r.get("variant", "pad"))
    if expected["sha256"] != r["feature_binding_sha256"]:
        raise ValueError("Run source/model identity no longer matches its recorded feature binding.")
    f = load_features(fpath)
    validate_feature_binding(f, expected)
    er = endpoint_rows(rows, r["endpoint"])
    data = head_inputs(er, f, {sid: i for i, sid in enumerate(f["sample_ids"].tolist())}, r["endpoint"])
    head = train_feature_head(data)
    stored = json.loads((d / "predictions" / f"{r['id']}.json").read_text())["val"]
    val = evaluate_head(head, data, "val")
    if val["sample_ids"] != stored["sample_ids"] or not np.allclose(val["probs"], stored["probs"], atol=1e-6):
        raise RuntimeError("The rebuilt head does not reproduce this run's stored val predictions. Re-run the baseline to get a saved head.")
    return head, data


def head_for(run: str, result_id: str):
    import numpy as np

    from ..learning.heads import evaluate_head, head_fingerprint, load_head, save_head
    from ..learning.provenance import measured_file, valid_sha

    d = run_dir(run)
    result = _result(d, result_id)
    if not valid_sha(result.get("feature_binding_sha256")) or not valid_sha(result.get("head_fingerprint")):
        raise ValueError("Legacy run/head has no measured-input binding. Stored result replay remains available; regenerate before live scoring.")
    if (not isinstance(result_id, str) or not result_id or "/" in result_id or "\\" in result_id or result_id.startswith(".")):
        raise ValueError("Invalid head identity.")
    path = d / "heads" / f"{result_id}.npz"
    if not path.resolve().is_relative_to(d.resolve()):
        raise ValueError("Head path leaves its run folder.")
    if not path.exists():
        head, data = _refit(d, result)
        if head_fingerprint(head) != result["head_fingerprint"]:
            raise ValueError("Rebuilt head does not reproduce this run's fitted-array identity. No head was written.")
        path.parent.mkdir(exist_ok=True)
        save_head(head, path)
        if not np.allclose(evaluate_head(load_head(path), data, "val")["probs"], evaluate_head(head, data, "val")["probs"], atol=1e-9):
            path.unlink()
            raise RuntimeError("A saved head did not reload to the same predictions.")
    key = (run, result_id, measured_file(path)["sha256"])
    if key not in _HEADS:
        for old in list(_HEADS):
            if old[:2] == key[:2]:
                del _HEADS[old]
        _HEADS[key] = load_head(path)
    head = _HEADS[key]
    if (head.encoder.get("feature_binding_sha256") != result["feature_binding_sha256"]
            or head_fingerprint(head) != result["head_fingerprint"]):
        raise ValueError("Saved head does not belong to this run's feature binding.")
    return head


def score(run: str, result_id: str, items: list[dict], progress=None) -> dict:
    """Score images, reporting observed stages and completed items through an optional callback."""
    t0 = time.monotonic()
    out, metadata = [], {}

    def report(stage, current=None):
        if progress:
            progress({"stage": stage, "current": current, "done": len(out), "items": out,
                      "metadata": metadata, "seconds": round(time.monotonic() - t0, 2)})

    report("preparing")
    import numpy as np

    from ..adapters.encoder import FrozenEncoderAdapter
    from ..learning.provenance import measured_file, model_identity, valid_sha

    if not items:
        raise ValueError("Select at least one image.")
    if len(items) > MAX_SCORE:
        raise ValueError(f"Score at most {MAX_SCORE} images at a time.")
    view = review(run, result_id)
    metadata = {k: view[k] for k in ("run", "result", "encoder", "variant", "classes", "threshold", "positive_class", "label")}
    metadata.update(note=NOTE, device="pending")
    report("head")
    head, enc, variant, classes = head_for(run, result_id), view["encoder"], view["variant"], view["classes"]
    if not valid_sha(head.encoder.get("model_fingerprint")) or not valid_sha(head.encoder.get("feature_binding_sha256")):
        raise ValueError("Legacy head has no measured model/input binding. Replay stored results or regenerate before scoring.")
    model = model_identity(enc, variant)
    expected = {"encoder_id": enc, "revision": str(model["revision"]), "preprocessing_hash": model["preprocessing_hash"],
                "model_fingerprint": model["sha256"], "feature_binding_sha256": head.encoder["feature_binding_sha256"]}
    if head.encoder != expected or list(head.classes) != classes:
        raise ValueError(f"The head was trained on features from other weights or preprocessing than {enc} "
                         f"with {variant} preprocessing as installed now.")
    metadata.update(model_fingerprint=model["sha256"], feature_binding_sha256=head.encoder["feature_binding_sha256"])
    adapter_key = (enc, variant, model["sha256"])
    with _LOCK:
        for old in list(_ENCODERS):
            if old[:2] == adapter_key[:2] and old != adapter_key:
                del _ENCODERS[old]
        adapter = _ENCODERS.get(adapter_key) or _ENCODERS.setdefault(adapter_key, FrozenEncoderAdapter(enc, variant=variant))
    for it in items:
        report("scoring", it["key"])
        sid = it.get("sample_id") or None
        row = view["rows"].get(sid) if sid else None
        e = {"key": it["key"], "sample_id": sid, "partition": row["partition"] if row else "outside run",
             "label": row["label"] if row else "", "stored_probs": row.get("probs") if row else None, "notes": []}
        out.append(e)
        if sid and sid in head.train_ids:
            e["refused"] = "This sample ID was used to train the head, so it is refused for live scoring."
            report("scoring")
            continue
        if row and row["partition"] == "val":
            e["notes"].append("Validation image: it was used to choose this head's regularization and threshold, so its score is optimistic.")
        if row and row["partition"] == "excluded":
            e["notes"].append(f"{row['why'].capitalize()}: the head was not trained or evaluated on images like it.")
        if not row:
            e["notes"].append("Not part of this run: no reference label, and the head has only seen BTXRD radiographs.")
        try:
            source = measured_file(Path(it["path"]))
            e["source_sha256"] = source["sha256"]
            if row and (not valid_sha(row.get("sha256")) or row["sha256"] != source["sha256"]):
                e["refused"] = "Image bytes do not match a measured source in this run. Stored labels/predictions may not apply."
                report("scoring")
                continue
            with _LOCK:
                feat = adapter.embed([Path(it["path"])], batch_size=1)
            if measured_file(Path(it["path"])) != source:
                raise ValueError("Image bytes changed during scoring.")
        except Exception as ex:  # an upload that will not decode, a missing file...
            e["error"] = f"{type(ex).__name__}: {ex}"
            report("scoring")
            continue
        probs = head.clf.predict_proba((feat.astype(np.float64) - head.mean) / head.scale)[0].tolist()
        e.update(probs=probs, pred=decide(probs, classes, view["threshold"]))
        if e["label"]:
            e["correct"] = e["pred"] == e["label"]
        metadata["device"] = str(adapter.device)
        report("scoring")
    if model_identity(enc, variant) != model:
        raise ValueError("Model inputs changed during scoring. No completed batch was published.")
    return {"label": LABEL, "note": NOTE, "run": run, "result": result_id, "encoder": enc, "variant": variant, "device": str(adapter.device),
            "model_fingerprint": model["sha256"], "feature_binding_sha256": head.encoder["feature_binding_sha256"],
            "classes": classes, "threshold": view["threshold"], "positive_class": view["positive_class"],
            "seconds": round(time.monotonic() - t0, 2), "items": out}
