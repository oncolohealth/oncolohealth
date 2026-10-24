"""Load the model and dataset catalogs (catalog/models.json, catalog/datasets.json)."""
from __future__ import annotations

import json
from pathlib import Path

from ..common.paths import CATALOG_DIR
from .schema import validate_dataset, validate_model


class Catalog:
    def __init__(self, models: list[dict], datasets: list[dict]):
        self.models = [dict(m, _kind="model") for m in models]
        self.datasets = [dict(d, _kind="dataset") for d in datasets]
        ids = [r["id"] for r in self.all()]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate catalog ids: {sorted(dupes)}")
        self._by_id = {r["id"]: r for r in self.all()}

    def all(self) -> list[dict]:
        return self.models + self.datasets

    def get(self, record_id: str) -> dict | None:
        return self._by_id.get(record_id)

    def validate(self) -> list[str]:
        return [e for m in self.models for e in validate_model(m)] + [
            e for d in self.datasets for e in validate_dataset(d)
        ]

    def search(self, text: str = "", kind: str | None = None) -> list[dict]:
        """Naive substring search over id/name/tasks/modality/anatomy. Workstream D may replace this."""
        text = text.lower()
        out = []
        for r in self.all():
            if kind and r["_kind"] != kind:
                continue
            hay = " ".join(
                str(r.get(k, "")) for k in ("id", "name", "tasks", "modality", "anatomy", "kind", "summary")
            ).lower()
            if text in hay:
                out.append(r)
        return out


def load_catalog(root: Path = CATALOG_DIR) -> Catalog:
    models = json.loads((root / "models.json").read_text())["records"]
    datasets = json.loads((root / "datasets.json").read_text())["records"]
    return Catalog(models, datasets)
