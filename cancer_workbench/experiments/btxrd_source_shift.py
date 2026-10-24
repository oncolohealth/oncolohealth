"""Source-shift preprocessing check on BTXRD. Owner: Workstream B with E. Needs the `ml` extra.

Only the `source_holdout` protocol: center 1 develops (train / val), centers 2
and 3 are TEST. For each encoder x endpoint, one head is fit per preprocessing
variant on the same split, and one variant is picked by its center-1 VAL macro
ROC-AUC (ties go to the `pad` baseline). TEST is evaluated only for the pick
and for `pad`; the other variants never see TEST.

Centers 2 and 3 are not an untouched test set. The first baseline run reported
on them, and the drop it showed there is why these variants exist. A gain on
them is a hint, not evidence that a variant handles new sources better; that
needs a source nobody has looked at.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from ..acquisition.download import hash_file
from ..common.paths import PROJECT_ROOT
from ..datasets import audit_dataset, read_manifest, write_manifest
from ..datasets.btxrd import MANIFEST_PATH, RAW_DIR
from .btxrd_baseline import (CLASSES, ENCODERS, GROUPING, _git_revision, endpoint_rows, evaluate, head_inputs, make_split,
                             record, rel, test_cells)

VARIANTS = ("pad", "pad_pstretch", "native_crop")  # "pad" first: it is the baseline and wins ties
LABEL = ("EXPLORATORY: image-level, no patient grouping, single source dataset. Not medical performance. "
         "Centers 2 and 3 were already seen as test data in the first baseline run, so they are not an untouched test.")
SCOPE = "local laptop; exploratory source-shift check requested 2026-10-24"


def select(val_scores: dict[str, float]) -> str:
    """The variant with the highest VAL score; ties go to the one listed first in VARIANTS."""
    return max(val_scores, key=lambda v: (val_scores[v], -VARIANTS.index(v)))


def run(encoders=ENCODERS, endpoints=tuple(CLASSES), variants=VARIANTS, *, out_dir: Path | None = None,
        seed: str = "0", n_boot: int = 1000, features_dir: Path = PROJECT_ROOT / "runs" / "features") -> Path:
    from ..adapters.encoder import preprocessing, preprocessing_hash, revision
    from ..learning.features import cache_path, extract_features, load_features
    from ..learning.heads import save_head, train_feature_head

    if "pad" not in variants or set(variants) - set(VARIANTS):
        raise ValueError(f"variants must include 'pad' and come from {VARIANTS}")
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"{MANIFEST_PATH} missing; run `python -m cancer_workbench btxrd manifest` first")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(out_dir or PROJECT_ROOT / "runs" / f"btxrd-source-shift-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_manifest(MANIFEST_PATH)
    manifest_sha = hash_file(MANIFEST_PATH)["sha256"]
    source_rev = _git_revision()

    feats = {}
    for enc in encoders:
        for v in variants:
            path = cache_path(enc, "btxrd", features_dir, v)
            if not path.exists():
                extract_features(enc, rows, RAW_DIR, path, variant=v)
            f = load_features(path)
            if f["preprocessing_hash"] != preprocessing_hash(enc, v) or f["revision"] != str(revision(enc)):
                raise ValueError(f"{path} was made with different preprocessing or weights")
            feats[enc, v] = (f, {sid: i for i, sid in enumerate(f["sample_ids"].tolist())}, path)

    split = make_split(rows, "source_holdout", seed)
    split_path = out_dir / "splits" / "source_holdout.csv"
    write_manifest(split_path, split)
    selections, results, records = [], [], []
    for endpoint in endpoints:
        er = endpoint_rows(split, endpoint)
        audit = audit_dataset({"id": "btxrd", "classes": CLASSES[endpoint]}, er)
        for enc in encoders:
            fitted = {}
            for v in variants:
                f, index, _ = feats[enc, v]
                data = head_inputs(er, f, index, endpoint)
                t0 = time.monotonic()
                fitted[v] = (train_feature_head(data), data, time.monotonic() - t0)
            val_scores = {v: fitted[v][0].val_score for v in variants}
            chosen = select(val_scores)
            selections.append({"endpoint": endpoint, "encoder": enc, "val_macro_roc_auc": val_scores,
                               "C": {v: fitted[v][0].C for v in variants}, "selected": chosen})
            for v in dict.fromkeys(("pad", chosen)):  # TEST only for the baseline and the pick
                head, data, fit_seconds = fitted[v]
                t0 = time.monotonic()
                val, test, report = evaluate(head, data, endpoint, n_boot)
                run_id = f"source_holdout.{endpoint}.{enc}.{v}"
                results.append({"id": run_id, "protocol": "source_holdout", "endpoint": endpoint, "encoder": enc,
                                "variant": v, "selected": v == chosen, "label": LABEL, "C": head.C,
                                "val_macro_roc_auc": head.val_score,
                                "counts": {p: sum(1 for r in er if r["partition"] == p) for p in ("train", "val", "test")},
                                "test": report})
                (out_dir / "predictions").mkdir(exist_ok=True)
                (out_dir / "predictions" / f"{run_id}.json").write_text(json.dumps({"val": val, "test": test}) + "\n")
                (out_dir / "heads").mkdir(exist_ok=True)
                save_head(head, out_dir / "heads" / f"{run_id}.npz")
                f, _, fpath = feats[enc, v]
                records.append(record(
                    f"{out_dir.name}/{run_id}", endpoint, enc, f, f"{split_path.name} (source_holdout, seed {seed}); {GROUPING}",
                    seed, preprocessing(enc, v), source_rev, manifest_sha, fit_seconds + time.monotonic() - t0,
                    [rel(fpath), f"predictions/{run_id}.json", f"heads/{run_id}.npz"],
                    [x["detail"] for x in audit["findings"] if x["severity"] == "error"], scope=SCOPE))

    (out_dir / "results.json").write_text(json.dumps({"label": LABEL, "variants": list(variants), "selections": selections,
                                                      "results": results}, indent=2) + "\n")
    (out_dir / "records.json").write_text(json.dumps(records, indent=2) + "\n")
    (out_dir / "summary.md").write_text(summary(selections, results, variants))
    return out_dir


def summary(selections: list[dict], results: list[dict], variants=VARIANTS) -> str:
    lines = [f"**{LABEL}**", "", "Center-1 VAL macro ROC-AUC per variant (the selection step; TEST not used):", "",
             "| Endpoint | Encoder | " + " | ".join(variants) + " | Selected |", "|---|---|" + "---|" * len(variants) + "---|"]
    for s in selections:
        lines.append(f"| {s['endpoint']} | {s['encoder']} | " + " | ".join(f"{s['val_macro_roc_auc'][v]:.3f}" for v in variants)
                     + f" | {s['selected']} |")
    lines += ["", "TEST (centers 2 + 3) for the baseline and the selected variant only:", "",
              "| Endpoint | Encoder | Variant | Test n | ROC-AUC (95% CI) | At val threshold / argmax |", "|---|---|---|---|---|---|"]
    for r in results:
        auc, dec = test_cells(r["test"])
        tag = r["variant"] + (" (selected)" if r["selected"] and r["variant"] != "pad" else "")
        lines.append(f"| {r['endpoint']} | {r['encoder']} | {tag} | {r['test']['n']} | {auc} | {dec} |")
    lines += ["", "CIs resample images, so they are too narrow if images share patients."]
    return "\n".join(lines) + "\n"
