"""Near-duplicate candidates in BTXRD from frozen-encoder feature similarity. Owner: Workstream A with E. Needs numpy.

Writes a ranked list of image pairs for a person to review. It changes no
duplicate group or split: a similar pair may be the same radiograph re-saved
or cropped, two views of one lesion, or just two similar radiographs.

A pair's score is the lower of its two cosine similarities (RAD-DINO and
ResNet-50 features, each centered on the dataset mean), so both encoders must
agree that the images look alike.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from ..common.paths import PROJECT_ROOT
from ..datasets.btxrd import MANIFEST_PATH, RAW_DIR
from .btxrd_baseline import ENCODERS, PROTOCOLS, make_split

CUTOFFS = (0.99, 0.98, 0.95, 0.90)
FIELDS = ("rank", "score", "a", "b", "cos_rad_dino", "cos_resnet50", "known_duplicate", "center_a", "center_b",
          "label_a", "label_b", "view_a", "view_b", "region_a", "region_b", "cross_center", "label_conflict",
          "cross_split_image_stratified", "cross_split_source_holdout")


def _unit(features):
    import numpy as np

    z = features.astype(np.float64) - features.mean(0)
    return z / np.linalg.norm(z, axis=1, keepdims=True).clip(1e-12)


def pair_scores(feature_sets: list, top: int):
    """The `top` highest-scoring pairs (i < j) as (i, j, score, per-encoder cosines), best first."""
    import numpy as np

    n = len(feature_sets[0]) if feature_sets else 0
    if type(top) is not int or not 1 <= top <= n * (n - 1) // 2:
        raise ValueError("top must be an integer between one and the number of distinct image pairs")
    sims = [(u @ u.T).astype(np.float32) for u in map(_unit, feature_sets)]
    score = np.minimum.reduce(sims)
    score[np.tril_indices(len(score))] = -np.inf
    flat = np.argpartition(score, -top, axis=None)[-top:]
    flat = flat[np.argsort(-score.ravel()[flat], kind="stable")]
    i, j = np.unravel_index(flat, score.shape)
    return [(int(a), int(b), float(score[a, b]), [float(s[a, b]) for s in sims]) for a, b in zip(i, j)], score


def run(*, top: int = 300, out_dir: Path | None = None, seed: str = "0",
        features_dir: Path = PROJECT_ROOT / "runs" / "features") -> Path:
    import numpy as np

    from ..learning.features import bound_source_rows, existing_features
    from ..learning.provenance import manifest_snapshot

    rows, manifest_sha256 = manifest_snapshot(MANIFEST_PATH)
    by_id = {r["sample_id"]: r for r in rows}
    feats = []
    references = []
    for enc in ENCODERS:
        f, path = existing_features(enc, rows, RAW_DIR, features_dir)
        rows = bound_source_rows(rows, f)
        feats.append(f)
        references.append({"encoder": enc, "feature_cache": path.name, "feature_binding_sha256": f["feature_binding_sha256"]})
    ids = feats[0]["sample_ids"].tolist()
    if any(f["sample_ids"].tolist() != ids for f in feats) or set(ids) != set(by_id):
        raise ValueError("feature files and manifest do not list the same images in the same order")
    pairs, score = pair_scores([f["features"] for f in feats], top)
    parts = {p: {r["sample_id"]: r["partition"] for r in make_split(rows, p, seed)} for p in PROTOCOLS}

    out = []
    for rank, (a, b, s, cos) in enumerate(pairs, 1):
        ra, rb = by_id[ids[a]], by_id[ids[b]]
        out.append({"rank": rank, "score": round(s, 4), "a": ids[a], "b": ids[b], "cos_rad_dino": round(cos[0], 4),
                    "cos_resnet50": round(cos[1], 4),
                    "known_duplicate": bool(ra["duplicate_group"]) and ra["duplicate_group"] == rb["duplicate_group"],
                    **{f"{k}_{x}": r[k] for k in ("center", "label", "view", "region") for x, r in (("a", ra), ("b", rb))},
                    "cross_center": ra["center"] != rb["center"],
                    "label_conflict": bool(ra["label"] and rb["label"]) and ra["label"] != rb["label"],
                    **{f"cross_split_{p}": parts[p][ids[a]] != parts[p][ids[b]] for p in PROTOCOLS}})

    upper = score[np.triu_indices(len(score), 1)]
    known = [o for o in out if o["known_duplicate"]]
    counts = {str(c): int((upper >= c).sum()) for c in CUTOFFS}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(out_dir or PROJECT_ROOT / "runs" / f"btxrd-near-duplicates-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "candidates.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    new = [o for o in out if not o["known_duplicate"]]
    stats = {"label": "Candidates for review, not confirmed duplicates. Splits and duplicate groups are unchanged.",
             "manifest_sha256": manifest_sha256, "feature_inputs": references,
             "encoders": list(ENCODERS), "n_images": len(ids), "top": top, "pairs_at_or_above": counts,
             "known_duplicate_pairs_in_top": len(known),
             "new_in_top": {"total": len(new), "cross_center": sum(o["cross_center"] for o in new),
                            "label_conflict": sum(o["label_conflict"] for o in new),
                            **{f"cross_split_{p}": sum(o[f"cross_split_{p}"] for o in new) for p in PROTOCOLS}}}
    (out_dir / "summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    return out_dir
