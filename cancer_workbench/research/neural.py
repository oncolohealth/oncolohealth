"""Frozen local ResNet-50 features plus separately fitted research task heads.

RGB histology/dermoscopy are preserved; ultrasound grayscale is replicated.
No reference labels, filenames or network downloads enter feature extraction.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import time

from ..common.paths import MODELS_DIR

REVISION="767268603ca0cb0bfe326fa87277f19c419566ef"
WEIGHT_SHA256="773525d5821de224f8f30c33377b7a795d7863e08522698200d3217d3f2a41bb"
CONFIG_SHA256="ff00d936f02c3b5f9f80a169d651ed28f9b6dc9cb1fd0464f92da4761caaac50"
MODEL_ROOT=MODELS_DIR/"resnet50-a1-in1k"
MODEL_LOCK=threading.Lock()
_MODEL=None
_LOADED_IDENTITY=None


def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""):digest.update(chunk)
    return digest.hexdigest()


def preprocessing(mode):
    if mode not in ("RGB","L"):raise ValueError("Neural research input mode must be RGB or L.")
    return {"mode":mode,"source_shape":[28,28,3] if mode=="RGB" else [28,28],
            "policy":"PIL bicubic square resize 28 to 288; preserve RGB, replicate L; float32/255; ImageNet mean/std once",
            "size":288,"interpolation":"PIL bicubic","mean":[0.485,0.456,0.406],"std":[0.229,0.224,0.225]}


def implementation_sha256():return sha_file(Path(__file__))


def identity(mode):
    import importlib.metadata as metadata
    weight=MODEL_ROOT/"model.safetensors";config=MODEL_ROOT/"config.json"
    if sha_file(weight)!=WEIGHT_SHA256 or sha_file(config)!=CONFIG_SHA256:
        raise ValueError("Frozen ResNet weight/config identity changed; no inference performed.")
    cfg=json.loads(config.read_text(encoding="utf-8"))["pretrained_cfg"]
    spec=preprocessing(mode)
    if cfg["test_input_size"]!=[3,288,288] or cfg["mean"]!=spec["mean"] or cfg["std"]!=spec["std"] or cfg["interpolation"]!="bicubic":
        raise ValueError("ResNet processor metadata no longer matches this pipeline.")
    body={"encoder_id":"resnet50-a1-in1k-rgb-research","revision":REVISION,"weights_sha256":WEIGHT_SHA256,
          "config_sha256":CONFIG_SHA256,"implementation_sha256":implementation_sha256(),"preprocessing":spec,
          "versions":{p:metadata.version(p) for p in ("torch","torchvision","timm","numpy","Pillow","safetensors")},
          "feature_dim":2048,"device":"cpu"}
    body["sha256"]=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    return body


def source_array(path,mode):
    import numpy as np
    from PIL import Image,ImageOps
    with Image.open(path) as image:
        image=ImageOps.exif_transpose(image)
        if image.size!=(28,28):raise ValueError("This bounded neural baseline requires a 28×28 dataset-style image; full clinical images need a different evaluated pipeline.")
        return np.asarray(image.convert(mode),dtype=np.uint8)


def tensor_for(array,mode):
    import numpy as np
    import torch
    from PIL import Image
    required=(28,28,3) if mode=="RGB" else (28,28)
    if array.shape!=required or array.dtype!=np.uint8:
        raise ValueError("Neural input must be source uint8 pixels with the declared 28-pixel shape.")
    image=Image.fromarray(array).convert("RGB").resize((288,288),Image.Resampling.BICUBIC)
    rgb=np.asarray(image,dtype=np.float32).copy()/255.
    tensor=torch.from_numpy(rgb).permute(2,0,1)
    spec=preprocessing(mode)
    return (tensor-torch.tensor(spec["mean"])[:,None,None])/torch.tensor(spec["std"])[:,None,None]


def _network():
    global _MODEL,_LOADED_IDENTITY
    current=identity("RGB")
    if _MODEL is not None:
        if _LOADED_IDENTITY!=current:raise ValueError("Loaded neural encoder identity changed; restart after review.")
        return _MODEL
    import timm
    import safetensors.torch
    model=timm.create_model("resnet50",pretrained=False,num_classes=0)
    state={k:v for k,v in safetensors.torch.load_file(MODEL_ROOT/"model.safetensors").items() if not k.startswith("fc.")}
    model.load_state_dict(state,strict=True)
    _MODEL=model.eval().to("cpu");_LOADED_IDENTITY=current
    return _MODEL


def embed_arrays(arrays,mode,*,batch_size=8,progress=None,deadline=None):
    import numpy as np
    import torch
    torch.set_num_threads(4)
    with MODEL_LOCK:
        model=_network();chunks=[]
        with torch.inference_mode():
            for start in range(0,len(arrays),batch_size):
                if deadline is not None and time.monotonic()>deadline:raise TimeoutError("Aggregate neural-candidate CPU budget reached; no additional batches started.")
                batch=torch.stack([tensor_for(a,mode) for a in arrays[start:start+batch_size]])
                chunks.append(model(batch).float().cpu().numpy())
                if progress:progress(min(start+batch_size,len(arrays)),len(arrays))
        return np.concatenate(chunks) if chunks else np.zeros((0,2048),dtype=np.float32)


def run(input_path,folder,*,allow_candidate=False):
    """Actual input→frozen encoder→trained head. Never accepts a reference label."""
    import numpy as np
    from ..learning.heads import load_head,head_fingerprint
    started=time.monotonic();folder=Path(folder)
    manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("state")!="verified" and not allow_candidate:raise ValueError("Neural candidate is not approved for active inference.")
    current=identity(manifest["preprocessing"]["mode"])
    if current!=manifest["encoder_identity"]:raise ValueError("Neural candidate encoder/implementation/preprocessing identity changed.")
    for name,expected in manifest["files"].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha_file(path)!=expected:raise ValueError("Neural candidate artifact changed: "+name)
    head=load_head(folder/"head.npz")
    if head_fingerprint(head)!=manifest["head_fingerprint"] or head.classes!=manifest["classes"]:raise ValueError("Neural fitted-head identity or class order differs.")
    array=source_array(Path(input_path),manifest["preprocessing"]["mode"])
    features=embed_arrays([array],manifest["preprocessing"]["mode"])
    probs=head.clf.predict_proba((features.astype(np.float64)-head.mean)/head.scale)[0].tolist()
    return {"prediction":{"class":head.classes[int(np.argmax(probs))],"scores":dict(zip(head.classes,probs)),"meaning":manifest["output_meaning"]},
            "device":"cpu","seconds":round(time.monotonic()-started,3),"source_pixel_sha256":hashlib.sha256(array.tobytes()).hexdigest(),
            "encoder_identity_sha256":current["sha256"],"weights_sha256":WEIGHT_SHA256,"head_fingerprint":head_fingerprint(head),
            "limitations":manifest["limitations"]}
