"""Measured tiny frozen-encoder extraction on a few local BTXRD images. Needs the `ml` extra.

Usage: .venv/bin/python scripts/extraction_smoke.py [--n 16] [--device mps]

Picks N exact-duplicate-free images spread over the three centers with a fixed
seed, strips labels and demographics, then for each encoder and preprocessing
variant runs the normal bound extraction, verifies the written cache against its
measured binding and times model load, cold and warm embedding. It also compares
`native_crop` with each publisher's own processor on these real JPEGs.

This is a runtime/resource measurement. It fits nothing, scores nothing and is
not a medical result. Outputs go to runs/extraction-smoke-<UTC time>/ (git-ignored).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cancer_workbench.adapters import encoder  # noqa: E402
from cancer_workbench.datasets.btxrd import RAW_DIR, build_manifest  # noqa: E402
from cancer_workbench.learning.features import extract_features, load_features, validate_feature_binding  # noqa: E402
from cancer_workbench.learning.provenance import feature_binding  # noqa: E402


def select(n: int, seed: int) -> list[dict]:
    rows = [r for r in build_manifest(RAW_DIR) if not r["duplicate_group"]]
    by_center: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["sample_id"]):
        by_center.setdefault(r["center"], []).append(r)
    rng, centers, picked = random.Random(seed), sorted(by_center), []
    for i, center in enumerate(centers):
        picked += rng.sample(by_center[center], n // len(centers) + (i < n % len(centers)))
    # labels, patient fields and demographics are not needed to time extraction
    return [{"sample_id": r["sample_id"], "file": r["file"], "sha256": r["sha256"], "center": r["center"],
             "patient_id": "", "partition": "unassigned", "label": ""} for r in sorted(picked, key=lambda r: r["sample_id"])]


def peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20 if sys.platform == "darwin" else 1 << 10), 1)


def publisher_agreement(encoder_id: str, paths: list[Path], adapter) -> dict:
    """Pixel and embedding agreement of `native_crop` with the publisher processor on real images."""
    import numpy as np
    import torch
    from PIL import Image

    spec, root = encoder.ENCODERS[encoder_id], encoder.MODELS_DIR / encoder_id
    if spec["arch"] == "dinov2":
        from transformers import AutoImageProcessor

        hf = AutoImageProcessor.from_pretrained(root, local_files_only=True)
        publisher = lambda im: hf(images=im, return_tensors="pt")["pixel_values"][0]
    else:
        import timm

        cfg = json.loads((root / "config.json").read_text())["pretrained_cfg"]
        publisher = timm.data.create_transform(**timm.data.resolve_data_config({}, pretrained_cfg=cfg, use_test_size=True))
    mean, std = torch.tensor(spec["mean"]).view(3, 1, 1), torch.tensor(spec["std"]).view(3, 1, 1)
    ours = torch.stack([(encoder.load_image(p, spec["size"], "native_crop", spec["crop_offset"]) - mean) / std
                       for p in paths])
    theirs = []
    for p in paths:
        with Image.open(p) as im:
            theirs.append(publisher(im.convert("RGB")))
    a, b = ours, torch.stack(theirs)
    diff = (a - b).abs()
    ea, eb = adapter._forward(a * std + mean).numpy(), adapter._forward(b * std + mean).numpy()  # _forward normalizes
    cos = (ea * eb).sum(1) / (np.linalg.norm(ea, axis=1) * np.linalg.norm(eb, axis=1))
    return {"pixel_max_abs_diff": round(float(diff.max()), 4), "pixel_mean_abs_diff": round(float(diff.mean()), 5),
            "embedding_cosine_min": round(float(cos.min()), 6), "embedding_cosine_mean": round(float(cos.mean()), 6),
            "note": "pixel differences are in normalized units; one 8-bit gray level is 1 / 255 / std"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default=None, help="default: mps, then cuda, then cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / f"extraction-smoke-{stamp}"
    (out / "features").mkdir(parents=True)
    rows = select(args.n, args.seed)
    with (out / "selection.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sample_id", "file", "center", "sha256"], extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    paths = [RAW_DIR / r["file"] for r in rows]
    report = {"started_utc": stamp, "n_images": len(rows), "seed": args.seed, "batch_size": args.batch_size,
              "centers": {c: sum(r["center"] == c for r in rows) for c in sorted({r["center"] for r in rows})},
              "image_bytes": sum(p.stat().st_size for p in paths), "timing": [], "runs": [], "publisher_agreement": {},
              "scope": "Runtime and resource measurement only. No labels, fitting, scoring or medical result."}
    for encoder_id in encoder.ENCODERS:
        size = encoder.ENCODERS[encoder_id]["size"]
        for variant in encoder.VARIANTS:
            t = time.monotonic()
            adapter = encoder.FrozenEncoderAdapter(encoder_id, device=args.device, variant=variant)
            adapter._ensure()
            load_s = time.monotonic() - t
            t = time.monotonic(); adapter.embed(paths, batch_size=args.batch_size); cold_s = time.monotonic() - t
            t = time.monotonic(); adapter.embed(paths, batch_size=args.batch_size); warm_s = time.monotonic() - t
            t = time.monotonic()
            for p in paths:  # decode and preprocessing alone, single-threaded
                encoder.load_image(p, size, variant, adapter.spec["crop_offset"])
            decode_s = time.monotonic() - t
            if variant == "native_crop":
                report["publisher_agreement"][encoder_id] = publisher_agreement(encoder_id, paths, adapter)
            report["timing"].append({"encoder": encoder_id, "variant": variant, "device": str(adapter.device),
                                     "model_load_seconds": round(load_s, 2), "cold_embed_seconds": round(cold_s, 2),
                                     "warm_embed_seconds": round(warm_s, 2),
                                     "warm_images_per_second": round(len(paths) / warm_s, 2),
                                     "decode_ms_per_image": round(1000 * decode_s / len(paths), 1),
                                     "projected_full_btxrd_minutes": round(3746 / (len(paths) / warm_s) / 60, 1)})
            del adapter
        for variant in encoder.VARIANTS:
            t = time.monotonic()
            expected = feature_binding(encoder_id, rows, RAW_DIR, variant)
            bind_s = time.monotonic() - t
            path = out / "features" / f"{encoder_id}-{variant}-{expected['sha256'][:12]}.npz"
            t = time.monotonic()
            extract_features(encoder_id, rows, RAW_DIR, path, batch_size=args.batch_size, device=args.device,
                             quiet=True, variant=variant, expected_binding=expected)
            extract_s = time.monotonic() - t
            features = load_features(path)
            validate_feature_binding(features, expected)
            report["runs"].append({"encoder": encoder_id, "variant": variant, "device": str(features["device"]),
                                   "feature_shape": list(features["features"].shape),
                                   "binding_sha256": expected["sha256"], "model_fingerprint": expected["model"]["sha256"],
                                   "binding_seconds": round(bind_s, 2), "extract_seconds_incl_load": round(extract_s, 2),
                                   "cache_bytes": path.stat().st_size, "cache": path.name, "binding_verified": True})
    report["peak_rss_mb"] = peak_rss_mb()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
