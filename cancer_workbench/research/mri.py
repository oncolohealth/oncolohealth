"""Pinned MONAI BraTS MRI segmentation, local CPU, no reference-label input.

Only already aligned, 1 mm, BraTS-style four-channel NIfTI inputs in the
explicit order T1ce,T1,T2,FLAIR are accepted. The public MSD demonstration
is reordered by prepare_msd_input; unrelated scans are never guessed into
this format. This module does not execute bundle configuration expressions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from ..common.paths import MODELS_DIR

BUNDLE = MODELS_DIR / "monai-brats-mri-segmentation"
REVISION = "370f7f9d062745fbac445e7fe6d6616d35df04ec"
WEIGHT_SHA256 = "860ccb3f1c21c99d0410ad8a1ac4ef6b8fab60cec0a503b0ba42675741a750ae"
CHANNEL_ORDER = ["T1ce", "T1", "T2", "FLAIR"]
MARKER = b"ONCO:BraTS-preprocessed;T1ce,T1,T2,FLAIR"
MODEL_LOCK = threading.Lock()
_MODEL = None
_LOADED_SHA = None


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare_msd_input(source: Path, destination: Path, provenance: Path) -> dict:
    """Reorder the documented MSD Task01 channels; never receives a mask/label.

    Source order comes from the source archive's dataset.json:
    FLAIR,T1w,t1gd,T2w. The pinned bundle prepare_datalist.py uses
    T1ce,T1,T2,FLAIR. Preserve voxel geometry and source values exactly.
    """
    import nibabel as nib
    import numpy as np

    source, destination, provenance = Path(source), Path(destination), Path(provenance)
    if destination.exists() or provenance.exists():
        raise FileExistsError("Preserve the existing prepared MRI and provenance.")
    image = nib.load(source)
    if len(image.shape) != 4 or image.shape[3] != 4:
        raise ValueError("MSD Task01 preparation requires a four-channel NIfTI.")
    array = np.asanyarray(image.dataobj)
    reordered = array[..., [2, 1, 3, 0]]
    header = image.header.copy()
    header["descrip"] = MARKER
    header.set_data_dtype(array.dtype)
    prepared = nib.Nifti1Image(reordered, image.affine, header)
    nib.save(prepared, destination)
    loaded = nib.load(destination)
    if not np.array_equal(np.asanyarray(loaded.dataobj), reordered) or not np.allclose(loaded.affine, image.affine):
        raise RuntimeError("Prepared MRI did not preserve source values/geometry.")
    receipt = {
        "source": str(source), "source_sha256": _sha(source),
        "prepared": str(destination), "prepared_sha256": _sha(destination),
        "source_channel_order": ["FLAIR", "T1w", "t1gd", "T2w"],
        "model_channel_order": CHANNEL_ORDER, "channel_reorder_indices": [2, 1, 3, 0],
        "shape": list(loaded.shape), "spacing_mm": list(map(float, loaded.header.get_zooms()[:3])),
        "affine": loaded.affine.tolist(), "reference_mask_used": False,
        "source_reference": "MSD Task01 dataset.json; bundle scripts/prepare_datalist.py at " + REVISION,
        "overlap_limit": "MSD BraTS2017 case may overlap this BraTS2018-trained model. Demonstration only; independent performance is not established.",
    }
    _save_json(provenance, receipt)
    return receipt


def validate(input_path: Path) -> dict:
    import nibabel as nib
    import numpy as np

    image = nib.load(input_path)
    if len(image.shape) != 4 or image.shape[3] != 4:
        raise ValueError("Requires four aligned MRI channels, not a single MRI slice or sequence.")
    if any(d < 8 or d > 256 for d in image.shape[:3]):
        raise ValueError("This bounded runtime supports 8–256 voxels per spatial axis.")
    spacing = np.asarray(image.header.get_zooms()[:3], dtype=float)
    if not np.allclose(spacing, [1., 1., 1.], atol=0.01, rtol=0):
        raise ValueError("Requires the bundle's pre-aligned 1 mm MRI grid; automatic clinical resampling is not implemented.")
    if bytes(image.header["descrip"]).rstrip(b"\0") != MARKER:
        raise ValueError("Channel order/preprocessing is undeclared. Use a prepared BraTS-style NIfTI declaring T1ce,T1,T2,FLAIR; do not assume arbitrary four-channel files use that order.")
    if image.header.get_xyzt_units()[0] not in ("mm", "unknown"):
        raise ValueError("MRI voxel spacing must use millimetres.")
    return {"shape": list(image.shape), "spacing_mm": spacing.tolist(),
            "channel_order": CHANNEL_ORDER, "orientation": list(nib.aff2axcodes(image.affine))}


def _network():
    global _MODEL, _LOADED_SHA
    import torch
    from monai.networks.nets import SegResNet

    weight = BUNDLE / "models" / "model.pt"
    measured = _sha(weight)
    if measured != WEIGHT_SHA256:
        raise ValueError("Pinned MRI model checksum differs from publisher-verified weight.")
    if _MODEL is None:
        # Exact architecture from the pinned inference.json, without eval/import
        # execution of the downloaded bundle config.
        network = SegResNet(blocks_down=[1, 2, 2, 4], blocks_up=[1, 1, 1],
                            init_filters=16, in_channels=4, out_channels=3, dropout_prob=0.2)
        state = torch.load(weight, map_location="cpu", weights_only=True)
        network.load_state_dict(state, strict=True)
        if _sha(weight) != measured:
            raise ValueError("MRI weight changed while loading.")
        _MODEL, _LOADED_SHA = network.eval().to("cpu"), measured
    if _LOADED_SHA != measured:
        raise ValueError("Loaded MRI model identity no longer matches disk.")
    return _MODEL


def run(input_path: Path, output_dir: Path, *, threads: int = 6) -> dict:
    """Run real segmentation and save mask/overlay/receipt. No answer key accepted.

    Returns native segmentation output identities and model-region voxel counts.
    The matching reference mask, if any, is a separate caller-owned comparison.
    A single inference uses the pinned whole-volume sliding-window ROI
    (240,240,160), batch 1, overlap 0.5, sigmoid and threshold 0.5.
    """
    import nibabel as nib
    import numpy as np
    from PIL import Image
    import torch
    from monai.inferers import sliding_window_inference
    from monai.transforms import NormalizeIntensity

    started = time.monotonic()
    input_path, output_dir = Path(input_path), Path(output_dir)
    inspected = validate(input_path)
    source_sha = _sha(input_path)
    image = nib.load(input_path)
    array = np.asarray(image.dataobj, dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError("MRI contains non-finite voxel values.")
    for channel in range(4):
        nonzero = array[..., channel][array[..., channel] != 0]
        if nonzero.size < 32 or float(nonzero.std()) == 0:
            raise ValueError("Every aligned MRI sequence must contain nonconstant nonzero voxels.")
    tensor = torch.from_numpy(np.ascontiguousarray(np.moveaxis(array, -1, 0)))
    tensor = NormalizeIntensity(nonzero=True, channel_wise=True)(tensor).unsqueeze(0)
    with MODEL_LOCK:
        torch.set_num_threads(max(1, min(int(threads), 8)))
        network = _network()
        with torch.inference_mode():
            logits = sliding_window_inference(tensor, roi_size=(240, 240, 160),
                        sw_batch_size=1, predictor=network, overlap=0.5, mode="constant",
                        device="cpu", sw_device="cpu")
            regions = torch.sigmoid(logits)[0] >= 0.5
            masks = regions.cpu().numpy()
    if _sha(input_path) != source_sha:
        raise ValueError("MRI input changed during inference.")
    # Exact priority mapping from pinned bundle postprocessing.
    combined = np.where(masks[2], 4, np.where(masks[0], 1, np.where(masks[1], 2, 0))).astype(np.uint8)
    output_dir.mkdir(parents=True, exist_ok=True)
    observation = uuid.uuid4().hex
    mask_path = output_dir / ("mri-" + observation + "-segmentation.nii.gz")
    overlay_path = output_dir / ("mri-" + observation + "-overlay.png")
    header = image.header.copy(); header.set_data_shape(combined.shape); header.set_data_dtype(np.uint8)
    header["descrip"] = b"MONAI BraTS predicted segmentation; 0,1,2,4"
    nib.save(nib.Nifti1Image(combined, image.affine, header), mask_path)
    # Pick a slice using predictions only. Ground-truth is never consulted.
    z = int(np.argmax(masks[1].sum(axis=(0, 1)))) if masks[1].any() else array.shape[2] // 2
    plane = array[:, :, z, 0].T
    values = plane[plane != 0]
    lo, hi = np.percentile(values, [1, 99]) if values.size else (0., 1.)
    grey = np.clip((plane - lo) / max(float(hi - lo), 1e-6), 0, 1)
    rgb = np.repeat(grey[..., None], 3, axis=2)
    colors = {1: [1., 0.7, 0.1], 2: [0.15, 0.9, 0.7], 4: [1., 0.2, 0.3]}
    for code, color in colors.items():
        selected = combined[:, :, z].T == code
        rgb[selected] = 0.55 * rgb[selected] + 0.45 * np.asarray(color)
    Image.fromarray(np.uint8(np.clip(rgb * 255, 0, 255))).save(overlay_path)
    native_counts = {name: int(masks[i].sum()) for i, name in enumerate(["tumor_core", "whole_tumor", "enhancing_tumor"])}
    counts = {"tumor_core": int(np.isin(combined, [1, 4]).sum()),
              "whole_tumor": int((combined > 0).sum()),
              "enhancing_tumor": int((combined == 4).sum())}
    receipt = {
        "id": observation, "status": "ok", "kind": "segmentation", "device": "cpu",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": "monai-brats-segresnet-local", "model_revision": REVISION,
        "weights_sha256": WEIGHT_SHA256, "inference_config_sha256": _sha(BUNDLE / "configs" / "inference.json"),
        "implementation_sha256": _sha(Path(__file__)),
        "input_sha256": source_sha, "input": inspected,
        "preprocessing": {"normalization": "nonzero, channel-wise MONAI NormalizeIntensity", "channel_order": CHANNEL_ORDER,
                          "geometry": "input geometry preserved; no resampling or orientation change", "roi_size": [240, 240, 160], "overlap": 0.5},
        "segmentation": {"region_voxels": counts, "native_threshold_region_voxels": native_counts,
                         "class_codes": {"0": "background", "1": "predicted tumor core outside enhancing region", "2": "predicted whole tumor outside core", "4": "predicted enhancing tumor"},
                         "mask_path": str(mask_path), "mask_sha256": _sha(mask_path),
                         "overlay_path": str(overlay_path), "overlay_sha256": _sha(overlay_path),
                         "overlay_slice_voxel_index": z, "overlay_sequence": "T1ce", "threshold": 0.5},
        "seconds": round(time.monotonic() - started, 3),
        "reference_used_for_inference": False,
        "limitations": ["Exploratory model output, not a diagnosis or medical performance claim.",
                        "Only aligned 1 mm BraTS-style four-sequence MRI is supported. Arbitrary MRI/DICOM needs a separate validated preprocessing path.",
                        "The demonstration MSD case may overlap BraTS2018 training. No independent generalization/accuracy estimate is established."],
    }
    _save_json(output_dir / ("mri-" + observation + "-receipt.json"), receipt)
    return receipt


def compare_reference(predicted_mask: Path, reference_mask: Path) -> dict:
    """Post-inference agreement with a separate MSD Task01 answer key.

    MSD uses 1=edema, 2=non-enhancing tumor, 3=enhancing tumor. The bundle's
    derived mask uses 1=core outside ET, 2=whole-tumor outside core, 4=ET.
    This is a demonstration agreement check, not an independent medical test.
    """
    import nibabel as nib
    import numpy as np

    predicted_mask, reference_mask = Path(predicted_mask), Path(reference_mask)
    prediction, reference = nib.load(predicted_mask), nib.load(reference_mask)
    if prediction.shape != reference.shape or not np.allclose(prediction.affine, reference.affine):
        raise ValueError("Reference and predicted masks must have matching voxel geometry.")
    predicted, truth = np.asanyarray(prediction.dataobj), np.asanyarray(reference.dataobj)
    if set(np.unique(predicted).tolist()) - {0, 1, 2, 4} or set(np.unique(truth).tolist()) - {0, 1, 2, 3}:
        raise ValueError("Mask labels do not match the declared MONAI/MSD conventions.")
    pairs = {"tumor_core": (np.isin(predicted, [1, 4]), np.isin(truth, [2, 3])),
             "whole_tumor": (predicted > 0, truth > 0),
             "enhancing_tumor": (predicted == 4, truth == 3)}
    comparison = {}
    for name, (a, b) in pairs.items():
        denominator = int(a.sum()) + int(b.sum())
        comparison[name] = {"predicted_voxels": int(a.sum()), "reference_voxels": int(b.sum()),
                            "intersection_voxels": int((a & b).sum()),
                            "dice_agreement": 2 * int((a & b).sum()) / denominator if denominator else None}
    return {"predicted_mask_sha256": _sha(predicted_mask), "reference_mask_sha256": _sha(reference_mask),
            "reference_convention": "MSD Task01: 1 edema, 2 non-enhancing, 3 enhancing",
            "regions": comparison,
            "limitation": "Potential BraTS2017/2018 train-case overlap: this is post-inference demonstration agreement, not an independently held-out estimate or medical validation."}
