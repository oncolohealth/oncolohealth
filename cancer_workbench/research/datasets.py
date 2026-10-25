"""Read-only installed-dataset inventory. No catalog entry is treated as downloaded."""
from __future__ import annotations
import csv
import json
import zipfile
from pathlib import Path
from ..common.paths import DATA_DIR
from ..registry import load_catalog


def installed() -> dict:
    rows=[]
    for record in load_catalog().datasets:
        root=DATA_DIR/record["id"]
        provenance=root/"PROVENANCE.json"
        if not root.is_dir():
            continue
        files=[p for p in root.rglob("*") if p.is_file() and not p.name.endswith((".part",".tmp"))]
        if not files:
            continue
        row={"id":record["id"],"name":record["name"],"modality":record.get("modality"),
             "license":record.get("license"),"citation":record.get("citation"),
             "actual_file_count":len(files),"actual_bytes":sum(p.stat().st_size for p in files),
             "has_provenance":provenance.is_file(),"local_root":str(root),"arrays":[],"manifests":[],
             "evidence_limit":"Presence is not a runnable model or independent clinical validation.",
             "unresolved":record.get("unresolved",[])}
        for path in files:
            if path.suffix.lower()==".npz":
                import numpy.lib.format as fmt
                with zipfile.ZipFile(path) as archive:
                    for member in archive.namelist():
                        if not member.endswith(".npy"):
                            continue
                        with archive.open(member) as stream:
                            version=fmt.read_magic(stream)
                            shape,fortran,dtype=(fmt.read_array_header_1_0(stream) if version==(1,0) else fmt.read_array_header_2_0(stream))
                        row["arrays"].append({"file":str(path.relative_to(root)),"array":member[:-4],"shape":list(shape),"dtype":str(dtype),"contains_object":bool(dtype.hasobject)})
            elif path.name=="manifest.csv":
                with path.open(encoding="utf-8-sig",newline="") as stream:
                    reader=csv.DictReader(stream);fields=reader.fieldnames;count=sum(1 for _ in reader)
                row["manifests"].append({"file":str(path.relative_to(root)),"rows":count,"fields":fields})
        rows.append(row)
    return {"datasets":rows,"count":len(rows),"note":"Measured files on this PC. A downloaded dataset is distinct from a trained runnable model. NPZ array headers expose real split sizes without loading patient labels into the assistant."}
