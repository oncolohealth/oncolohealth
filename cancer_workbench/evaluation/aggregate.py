"""Explicit binary image-to-patient aggregation; no patient identifiers are inferred."""
from __future__ import annotations

from ._binary import binary_rows


def patient_level(rows: list[dict], how: str = "max") -> list[dict]:
    """Aggregate binary scores with max or mean; refuse mixed labels/partitions.

    Required: sample_id, patient_id, label (0/1), score (0..1). Optional
    partition must agree within each patient, including whether it is supplied.
    A patient with discordant image labels needs an adjudicated patient target,
    not an implicit conversion of a normal view into a positive patient label.
    """
    if how not in {"max", "mean"}:
        raise ValueError("how must be 'max' or 'mean'")
    binary_rows(rows)
    groups = {}
    for row in rows:
        groups.setdefault(row["patient_id"], []).append(row)
    result = []
    for patient, images in sorted(groups.items()):
        if len({r["label"] for r in images}) != 1:
            raise ValueError(f"conflicting labels for patient {patient!r}; adjudicate the patient endpoint")
        if len({r.get("partition") for r in images}) != 1:
            raise ValueError(f"patient {patient!r} spans partitions")
        scores = [r["score"] for r in images]
        result.append({"patient_id": patient, "label": images[0]["label"],
                       "score": max(scores) if how == "max" else sum(scores) / len(scores),
                       "partition": images[0].get("partition"), "n_images": len(images),
                       "sample_ids": sorted(r["sample_id"] for r in images), "aggregation": how})
    return result
