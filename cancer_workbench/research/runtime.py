"""One local inference path shared by the app and coordinator tools.

Reference labels are stored separately and read only AFTER prediction finishes.
No labels, file names or reference keys are passed to the model transform.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from ..common.paths import DATA_DIR, MODELS_DIR, PROJECT_ROOT

INPUTS = DATA_DIR / "research-inputs"
REFERENCES = DATA_DIR / "research-references"
RESULTS = PROJECT_ROOT / "runs" / "observations"
ARTIFACTS = MODELS_DIR / "research-specialists"
MAX_BYTES = 128_000_000
LOCK = threading.Lock()
NOTE = "Exploratory research output. Not a diagnosis or established medical performance."


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{16}|[0-9a-f]{64})", value):
        raise ValueError("Use a stable uploaded input ID, not a file path.")
    return value


def resolve_input(input_id: str) -> tuple[Path, dict]:
    input_id = _id(input_id)
    meta_path = INPUTS / (input_id + ".json")
    legacy = False
    if not meta_path.is_file():
        meta_path = DATA_DIR / "uploads" / (input_id + ".json")
        legacy = True
    meta = _json(meta_path)
    root = meta_path.parent.resolve()
    path = (root / meta["file"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("The registered input file is missing or leaves its input folder.")
    if sha_file(path) != meta["sha256"]:
        raise ValueError("Input bytes changed after upload; upload the reviewed file again.")
    # Never expose references through the input-listing/model-input interface.
    public = {k: meta[k] for k in ("id", "original_name", "bytes", "sha256", "format", "shape", "uploaded_at") if k in meta}
    if legacy:
        public["format"] = "image"
    return path, public


def list_inputs() -> list[dict]:
    rows = []
    for root in (INPUTS, DATA_DIR / "uploads"):
        for meta_path in root.glob("*.json") if root.exists() else []:
            try:
                _, meta = resolve_input(meta_path.stem)
                rows.append(meta)
            except (ValueError, KeyError, OSError):
                continue
    unique = {}
    for row in sorted(rows, key=lambda r: r.get("uploaded_at", ""), reverse=True):
        unique.setdefault(row["sha256"],row)
    return list(unique.values())


def preview(input_id: str) -> dict:
    path,meta = resolve_input(input_id)
    if meta["format"] == "image":
        root = "research" if path.parent.resolve() == INPUTS.resolve() else "uploads"
        return {"input":meta,"media":root+"/"+path.name,"note":"Original uploaded pixels; no prediction overlay."}
    if meta["format"] == "nifti":
        import nibabel as nib
        import numpy as np
        from PIL import Image
        image = nib.load(path)
        # One bounded middle slice for navigation only, never a model input.
        if len(image.shape) not in (3,4):
            return {"input":meta,"note":"No volume preview for this shape."}
        array = np.asarray(image.dataobj[:,:,image.shape[2]//2,0] if len(image.shape)==4 else image.dataobj[:,:,image.shape[2]//2],dtype=np.float32)
        finite = array[np.isfinite(array)]
        if finite.size:
            lo,hi=np.percentile(finite,[1,99]);array=np.nan_to_num(array,nan=float(lo),posinf=float(hi),neginf=float(lo))
            array=np.clip((array-lo)/max(float(hi-lo),1e-6)*255,0,255).astype(np.uint8)
        else:
            array=np.zeros(array.shape,dtype=np.uint8)
        root=DATA_DIR/"research-previews";root.mkdir(exist_ok=True,parents=True)
        Image.fromarray(array.T).save(root/(meta["sha256"]+".png"))
        return {"input":meta,"media":"research-preview/"+meta["sha256"]+".png","note":"Middle voxel-index slice, display window only; physical orientation is not inferred. The model receives the original volume."}
    return {"input":meta,"note":"Validated "+meta["format"]+" input. No eligible task is implied by accepting a file."}


def samples() -> list[dict]:
    path=DATA_DIR/"research-samples.json"
    if not path.is_file():
        return []
    return [{k:r[k] for k in ("model_id","input_id","title","source") if k in r} for r in _json(path)]


def inspect_file(path: Path, extension: str) -> dict:
    if extension in (".png", ".jpeg", ".jpg"):
        from PIL import Image
        with Image.open(path) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Images over 40 million pixels are not accepted.")
            image.verify()
            return {"format": "image", "shape": [image.height, image.width]}
    if extension in (".nii", ".nii.gz"):
        import nibabel as nib
        image = nib.load(path)
        import math
        if not 2 <= len(image.shape) <= 4 or any(n <= 0 for n in image.shape) or math.prod(image.shape) * image.header.get_data_dtype().itemsize > 512_000_000:
            raise ValueError("NIfTI must have 2–4 dimensions and at most 512 MB of decoded voxels.")
        return {"format": "nifti", "shape": list(image.shape)}
    if extension == ".dcm":
        import pydicom
        image = pydicom.dcmread(path, stop_before_pixels=True)
        if not hasattr(image, "Rows") or not hasattr(image, "Columns"):
            raise ValueError("DICOM must contain image rows/columns; this is not an image object.")
        return {"format": "dicom", "shape": [int(image.Rows), int(image.Columns)], "modality": str(image.get("Modality", "unknown"))}
    if extension == ".zip":
        import zipfile
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > 4096 or sum(m.file_size for m in members) > 512_000_000:
                raise ValueError("A DICOM series ZIP must contain 1–4096 files and decode to at most 512 MB.")
            if any(Path(m.filename).is_absolute() or ".." in Path(m.filename).parts or "\\" in m.filename for m in members):
                raise ValueError("Archive paths must be relative and stay inside the series.")
            import pydicom
            image_members = [m for m in members if not m.is_dir() and not m.filename.startswith("__MACOSX/")]
            for member in image_members:
                with archive.open(member) as stream:
                    ds = pydicom.dcmread(stream, stop_before_pixels=True)
                if not hasattr(ds, "Rows") or not hasattr(ds, "SeriesInstanceUID"):
                    raise ValueError("The series ZIP must contain only DICOM image files.")
            return {"format": "dicom-series", "files": len(image_members)}
    if extension in (".json", ".csv"):
        import csv
        raw = path.read_text(encoding="utf-8-sig")
        if len(raw) > 2_000_000:
            raise ValueError("Structured profiles are limited to 2 MB.")
        if extension == ".json":
            value = json.loads(raw)
            if not isinstance(value, (dict, list)):
                raise ValueError("A JSON profile must be an object or list of records.")
        else:
            reader = csv.DictReader(io.StringIO(raw))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV needs unique column names and a header.")
            value = list(reader)
            if not value or any(None in row or None in row.values() for row in value):
                raise ValueError("CSV rows must match the header and contain at least one record.")
        return {"format": "structured", "rows": len(value) if isinstance(value, list) else 1}
    raise ValueError("Use JPEG/PNG, NIfTI (.nii/.nii.gz), DICOM (.dcm or series ZIP), or structured CSV/JSON. Whole-slide SVS/TIFF needs a separate tile/slide model; it is unavailable here.")


def upload(body: dict) -> dict:
    from ..acquisition import budget
    raw = base64.b64decode(body.get("data", ""), validate=True)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Input must be nonempty and no larger than 128 MB.")
    if not budget.check(len(raw))[0]:
        raise ValueError("This upload exceeds the configured storage budget.")
    name = str(body.get("name") or "input")[:180]
    extension = ".nii.gz" if name.lower().endswith(".nii.gz") else Path(name).suffix.lower()
    if extension not in (".png", ".jpeg", ".jpg", ".nii", ".nii.gz", ".dcm", ".zip", ".csv", ".json"):
        raise ValueError("Unsupported file format. Choose a supported image, volume, DICOM series or profile.")
    sha = hashlib.sha256(raw).hexdigest()
    INPUTS.mkdir(parents=True, exist_ok=True)
    # JSON input bytes must not share the <id>.json metadata sidecar path.
    path = INPUTS / (sha + (".input.json" if extension == ".json" else extension))
    # Validate a temporary file before publishing the registered input.
    temp = INPUTS / (uuid.uuid4().hex + extension)
    try:
        temp.write_bytes(raw)
        inspection = inspect_file(temp, extension)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    meta = {"id": sha, "file": path.name, "original_name": name, "bytes": len(raw), "sha256": sha,
            "uploaded_at": datetime.now(timezone.utc).isoformat(), **inspection}
    _save(INPUTS / (sha + ".json"), meta)
    return meta


def profile(model_id: str) -> tuple[Path, dict]:
    if not isinstance(model_id, str) or not re.fullmatch(r"[a-z0-9-]{1,100}", model_id):
        raise ValueError("Unknown specialist model ID.")
    folder = ARTIFACTS / model_id
    if not (folder / "manifest.json").is_file():
        raise ValueError("No verified trained specialist is installed for " + model_id + ". Uploading data does not create a classifier.")
    data = _json(folder / "manifest.json")
    if data.get("id") != model_id or data.get("state") != "verified":
        raise ValueError("Specialist has not completed its saved-artifact verification.")
    for name, expected in data["files"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha_file(path) != expected:
            raise ValueError("Specialist artifact is missing or its checksum changed: " + name)
    for name, expected in data.get("external_files", {}).items():
        path = (MODELS_DIR / name).resolve()
        if not path.is_relative_to(MODELS_DIR.resolve()) or sha_file(path) != expected:
            raise ValueError("Pinned external specialist artifact is missing or changed: " + name)
    if data.get("backend") == "mri":
        if sha_file(Path(__file__).with_name("mri.py")) != data.get("implementation_sha256"):
            raise ValueError("MRI inference implementation differs from its verified manifest.")
    return folder, data


def list_models() -> list[dict]:
    out = []
    for path in ARTIFACTS.glob("*/manifest.json") if ARTIFACTS.exists() else []:
        try:
            _, data = profile(path.parent.name)
            out.append({k: data[k] for k in ("id", "name", "modality", "anatomy", "task", "formats", "classes", "preprocessing", "limitations", "license", "training", "output_kind", "backend", "input_guidance") if k in data} | {"available": True})
        except (OSError, KeyError, ValueError) as exc:
            out.append({"id": path.parent.name, "name": path.parent.name, "available": False, "blocker": str(exc)})
    return out


def _source_pixels(path: Path, spec: dict):
    """Decode source uint8 voxels/pixels before pooling/normalization."""
    import numpy as np
    if spec["kind"] == "volume-patch":
        import nibabel as nib
        array = np.asanyarray(nib.load(path).dataobj)
        if list(array.shape) != [28, 28, 28] or array.dtype != np.uint8:
            raise ValueError("This NoduleMNIST3D baseline accepts only a 28×28×28 uint8 CT patch on the dataset's intensity scale, not an entire CT scan or Hounsfield-unit DICOM volume.")
        return array
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert(spec["mode"])
        if image.size != (28,28):
            raise ValueError("This bounded MedMNIST baseline requires a 28×28 dataset-style image. Use the provided research samples; arbitrary full-size clinical images require a validated preprocessing/model pipeline.")
        return np.asarray(image,dtype=np.uint8)


def pixels(path: Path, spec: dict):
    """The SAME input-only transform is used for training verification and serving."""
    import numpy as np
    array = _source_pixels(path,spec).astype(np.float64)
    if spec["kind"] == "volume-patch":
        array = array.reshape(14,2,14,2,14,2).mean((1,3,5))
    return array.reshape(1,-1)/255.


def evaluation_eligibility(path: Path, model: dict, folder: Path) -> dict:
    """Match measured source identities, never file names or reference labels."""
    backend = model["backend"]
    partitions = set()
    basis = "No recorded training/validation/test source match"
    if backend == "btxrd":
        from ..datasets import read_manifest
        from ..experiments.explore import run_dir, _result
        directory = run_dir(model["run"])
        result = _result(directory,model["result"])
        protocol = result["protocol"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",protocol):
            raise ValueError("Invalid bound split protocol.")
        source_sha = sha_file(path)
        rows = read_manifest(directory/"splits"/(protocol+".csv"))
        partitions = {r["partition"] for r in rows if r.get("sha256")==source_sha}
        basis = "Exact measured source-file SHA-256 against the run's bound split"
    elif backend == "pixels":
        source_sha = hashlib.sha256(_source_pixels(path,model["preprocessing"]).tobytes()).hexdigest()
        receipt_path = folder/"training-receipt.json"
        if receipt_path.is_file():
            receipt = _json(receipt_path)
            selected = receipt.get("selected_pixel_sha256",{})
            partitions = {part for part in ("train","val","test") if source_sha in selected.get(part,[])}
        basis = "Decoded source uint8 pixel/voxel SHA-256 before normalization/pooling; no filename lookup"
    elif backend == "mri":
        return {"known_partition":"unknown", "may_be_used_for_held_out_sample_comparison":False,
                "independent_patient_evaluation":False, "basis":"Restored BraTS model; source-case overlap cannot be excluded",
                "note":"Demonstration only. A separate mask comparison is not independent evaluation."}
    partition = next((p for p in ("train","val","test") if p in partitions),"unknown")
    notes = {"train":"This input is a known training source and is refused for live scoring.",
             "val":"Known validation input: used to choose the head/regularization; its agreement is optimistic, not an unseen-case evaluation.",
             "test":"Source belongs to the saved sample-level test partition. Missing patient/lesion IDs still prevent a claim of patient-independent evaluation.",
             "unknown":"Source provenance is unmatched. A reference agreement is not proof this is an unseen case; re-encoding and unidentified related cases cannot be ruled out."}
    return {"known_partition":partition, "may_be_used_for_held_out_sample_comparison":partition=="test",
            "independent_patient_evaluation":False,"basis":basis,"note":notes[partition]}


def set_reference(body: dict) -> dict:
    input_path, meta = resolve_input(body.get("input_id"))
    _, model = profile(body.get("model_id"))
    source = str(body.get("source") or "user-provided reference; not independently verified")[:1000]
    if model["backend"] == "mri":
        from . import mri
        import nibabel as nib
        import numpy as np
        if body.get("reference_convention") != "MSD_Task01":
            raise ValueError("MRI references require explicit reference_convention='MSD_Task01' (0 background, 1 edema, 2 non-enhancing, 3 enhancing).")
        reference_path, reference_meta = resolve_input(body.get("reference_input_id"))
        if reference_meta["format"] != "nifti":
            raise ValueError("MRI reference must be a separately uploaded NIfTI mask.")
        mri.validate(input_path)
        reference, image = nib.load(reference_path), nib.load(input_path)
        if reference.shape != image.shape[:3] or not np.allclose(reference.affine,image.affine):
            raise ValueError("MRI reference mask must match the uploaded MRI voxel geometry.")
        if set(np.unique(np.asanyarray(reference.dataobj)).tolist()) - {0,1,2,3}:
            raise ValueError("Reference label codes do not match declared MSD Task01 convention.")
        ref = {"input_sha256":meta["sha256"], "model_id":model["id"], "type":"segmentation-mask",
               "reference_input_id":reference_meta["id"], "reference_sha256":reference_meta["sha256"],
               "reference_convention":"MSD_Task01", "source":source,
               "created_utc":datetime.now(timezone.utc).isoformat(), "separate_from_inference_inputs":True}
        _save(REFERENCES / meta["sha256"] / (model["id"] + ".json"),ref)
        return ref
    label = body.get("label")
    if label not in model["classes"]:
        raise ValueError("Reference must match one declared model class: " + ", ".join(model["classes"]))
    ref = {"input_sha256":meta["sha256"], "model_id":model["id"], "label":label, "source":source,
           "created_utc":datetime.now(timezone.utc).isoformat(), "separate_from_inference_inputs":True}
    _save(REFERENCES / meta["sha256"] / (model["id"] + ".json"),ref)
    return ref


def predict(model_id: str, input_id: str) -> dict:
    started = time.monotonic()
    receipt = {"id":uuid.uuid4().hex, "model_id":model_id, "input_id":input_id,
               "started_utc":datetime.now(timezone.utc).isoformat(), "status":"failed", "note":NOTE}
    try:
        path, meta = resolve_input(input_id)
        folder, model = profile(model_id)
        receipt.update(input=meta, model_manifest_sha256=sha_file(folder/"manifest.json"),
                       training=model["training"], preprocessing=model["preprocessing"])
        if meta["format"] not in model["formats"]:
            raise ValueError("Incompatible input format; this model requires: " + ", ".join(model["formats"]))
        receipt["evaluation_eligibility"] = evaluation_eligibility(path,model,folder)
        if receipt["evaluation_eligibility"]["known_partition"] == "train":
            raise ValueError(receipt["evaluation_eligibility"]["note"])
        with LOCK:
            if model["backend"] == "btxrd":
                from ..experiments.explore import score, head_for
                from ..learning.heads import head_fingerprint
                if head_fingerprint(head_for(model["run"], model["result"])) != model["head_fingerprint"]:
                    raise ValueError("The active bone head differs from this registered trained artifact.")
                observed = score(model["run"],model["result"],[{"key":"input:"+input_id,"path":str(path)}])
                item = observed["items"][0]
                if "probs" not in item:
                    raise ValueError(item.get("error") or item.get("refused") or "Scoring returned no prediction.")
                probs, pred = item["probs"], item["pred"]
                receipt["native_result"] = observed
                receipt["artifact_identity"] = {"model_fingerprint":observed["model_fingerprint"], "feature_binding_sha256":observed["feature_binding_sha256"], "run":model["run"],"result":model["result"]}
            elif model["backend"] == "mri":
                from . import mri
                observed = mri.run(path,RESULTS/receipt["id"])
                segmentation = dict(observed["segmentation"])
                for name in ("mask", "overlay"):
                    output = Path(segmentation[name+"_path"]).resolve()
                    if not output.is_relative_to((RESULTS/receipt["id"]).resolve()) or sha_file(output) != segmentation[name+"_sha256"]:
                        raise ValueError("MRI output identity/path mismatch.")
                    segmentation[name+"_media"] = "research-output/"+receipt["id"]+"/"+output.name
                receipt.update(kind="segmentation", segmentation=segmentation, native_result=observed,
                               artifact_identity={"weights_sha256":observed["weights_sha256"],
                                  "model_revision":observed["model_revision"],"implementation_sha256":observed["implementation_sha256"]})
            else:
                from ..learning.heads import load_head, head_fingerprint
                head = load_head(folder/"head.npz")
                if head_fingerprint(head) != model["head_fingerprint"] or head.classes != model["classes"]:
                    raise ValueError("Fitted head identity/class order does not match its manifest.")
                features = pixels(path,model["preprocessing"])
                probs = head.clf.predict_proba((features-head.mean)/head.scale)[0].tolist()
                pred = head.classes[max(range(len(probs)),key=probs.__getitem__)]
                receipt["artifact_identity"] = {"head_sha256":model["files"]["head.npz"],"head_fingerprint":model["head_fingerprint"]}
        if sha_file(path) != meta["sha256"]:
            raise ValueError("Input changed while inference was running.")
        receipt.update(status="ok",limitations=model["limitations"])
        if model["backend"] != "mri":
            receipt.update(kind="classification", prediction={"class":pred,"scores":dict(zip(model["classes"],probs)),
                            "meaning":model["output_meaning"]})
        # Only now, after model execution, consult the independent answer key.
        ref_path = REFERENCES/meta["sha256"]/(model_id+".json")
        if ref_path.is_file():
            ref = _json(ref_path)
            if ref["input_sha256"] != meta["sha256"] or ref["model_id"] != model_id:
                raise ValueError("Reference identity mismatch.")
            if model["backend"] == "mri":
                from . import mri
                reference_path, reference_meta = resolve_input(ref["reference_input_id"])
                if reference_meta["sha256"] != ref["reference_sha256"] or ref.get("reference_convention") != "MSD_Task01":
                    raise ValueError("Stored MRI reference identity/convention changed.")
                agreement = mri.compare_reference(Path(receipt["segmentation"]["mask_path"]),reference_path)
                receipt["comparison"] = {"reference":ref, "regions":agreement["regions"],
                                         "meaning":agreement["limitation"]}
            else:
                receipt["comparison"] = {"reference":ref,"matches":ref["label"]==pred,
                                         "meaning":"Agreement with this supplied/release label only; not medical validation."}
    except Exception as exc:
        receipt.update(status="failed",error=f"{type(exc).__name__}: {exc}")
    receipt["seconds"] = round(time.monotonic()-started,3)
    _save(RESULTS/(receipt["id"]+".json"),receipt)
    return receipt


class ResearchAdapter:
    synthetic = False

    def __init__(self, model_id):
        self.id = "local-research:"+model_id
        self.model_id = model_id

    def validate(self, inputs):
        if not isinstance(inputs,dict) or set(inputs) != {"input_id"}:
            return ["inputs must contain only input_id. References/labels are never model inputs."]
        try:
            resolve_input(inputs["input_id"])
        except (OSError,ValueError,KeyError) as exc:
            return [str(exc)]
        return []

    def run(self, inputs):
        result = predict(self.model_id,inputs["input_id"])
        if result["status"] != "ok":
            raise RuntimeError(result["error"] + "; saved observation " + result["id"])
        # Keep native receipts on disk; give the model the actual material output
        # without flooding its finite context with training tables or duplicate scores.
        return {k:result[k] for k in ("id","model_id","input_id","input","kind","prediction","segmentation","comparison",
                                     "artifact_identity","evaluation_eligibility","seconds","note","limitations") if k in result}


def tool_registration():
    records, adapters = [], {}
    for model in list_models():
        if not model["available"]:
            continue
        adapter = ResearchAdapter(model["id"])
        adapters[adapter.id] = adapter
        records.append({"id":model["id"],"name":model["name"],"kind":"local-research-specialist",
                        "summary":"Verified local exploratory "+model["task"]+" specialist. Supply inputs {input_id: stable uploaded ID}; output is not a diagnosis. " + " ".join(model["limitations"]),
                        "tasks":[model["task"]],"modality":[model["modality"]],"anatomy":[model["anatomy"]],
                        "input":{"formats":model["formats"],"stable_id_required":True},"outputs":({"regions":model["classes"],"kind":"segmentation"} if model.get("output_kind")=="segmentation" else {"classes":model["classes"]}),
                        "evidence_state":"locally_reproduced","inference_permission":"allowed","adapter":adapter.id,
                        "license":model["license"],"access":"local","citation":"Local training/provenance manifest: models/research-specialists/"+model["id"]+"/manifest.json"})
    return records, adapters
