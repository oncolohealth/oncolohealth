"""Background download jobs with live progress and cancellation (one fetch job at a time)."""
from __future__ import annotations

import threading
import time
import uuid

from ..acquisition import budget
from ..acquisition.fetch import fetch, plan
from ..registry.store import Catalog


class Cancelled(Exception):
    pass


class JobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.jobs: dict[str, dict] = {}

    def active(self) -> dict | None:
        return next((j for j in self.jobs.values() if j["state"] in ("planning", "running")), None)

    def list(self) -> list[dict]:
        with self._lock:
            return [{k: v for k, v in j.items() if not k.startswith("_")} for j in sorted(self.jobs.values(), key=lambda j: -j["started"])]

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job["state"] not in ("planning", "running"):
            return False
        job["_cancel"] = True
        return True

    def start(self, catalog: Catalog, ids: list[str], allow_big: bool = False, subsets: dict[str, dict] | None = None) -> dict:
        with self._lock:
            if self.active():
                raise RuntimeError("A download is already running. Wait for it or cancel it first.")
            records = [catalog.get(i) for i in ids]
            unknown = [i for i, r in zip(ids, records) if r is None]
            if unknown:
                raise KeyError(f"Unknown catalog ids: {unknown}")
            big = [r["id"] for r in records if r["acquisition"].get("tier") == "big_machine"]
            if big and not allow_big:
                raise PermissionError(f"{big} are big-machine models. Tick 'allow big-machine models' to fetch them here.")
            job = {
                "id": uuid.uuid4().hex[:10], "state": "planning", "started": time.time(), "finished": None,
                "items": [{"id": r["id"], "state": "queued", "file": None, "done": 0, "total": None, "error": None} for r in records],
                "log": [], "_cancel": False,
            }
            self.jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job, records, subsets), daemon=True).start()
        return {"id": job["id"]}

    def _run(self, job: dict, records: list[dict], subsets: dict[str, dict] | None = None) -> None:
        def log(msg: str):
            job["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")

        try:
            rows = plan(records, subsets)
            planned = sum(r["bytes"] for r in rows if not r["error"])
            fits, used, cap = budget.check(planned)
            if not fits:
                job["state"] = "failed"
                log(f"Over budget: {planned / 1e9:.2f} GB planned, {used / 1e9:.2f} GB used of {budget.describe(cap)}.")
                return
            job["state"] = "running"
            for item, rec, row in zip(job["items"], records, rows):
                if job["_cancel"]:
                    item["state"] = "cancelled"
                    continue
                if row["error"]:
                    item["state"], item["error"] = "blocked", row["error"]
                    log(f"{rec['id']}: blocked. {row['error']}")
                    continue
                item["state"] = "downloading"
                item["total"] = sum(p.size or p.approx_size or 0 for p in row["plans"]) or None
                finished_bytes = {"sum": 0, "rel": None, "last": 0}

                def on_progress(rel, done, total, item=item, acc=finished_bytes):
                    if job["_cancel"]:
                        raise Cancelled()
                    if acc["rel"] != rel:
                        acc["sum"] += acc["last"]
                        acc["rel"] = rel
                    acc["last"] = done
                    item["file"], item["done"] = rel, acc["sum"] + done

                try:
                    fetch(rec, row["plans"], quiet=True, on_progress=on_progress, selection=row["selection"])
                    item["state"], item["done"] = "done", item["total"] or item["done"]
                    log(f"{rec['id']}: fetched and verified")
                except Cancelled:
                    item["state"] = "cancelled"
                    log(f"{rec['id']}: cancelled. Partial files are kept so the next run resumes.")
                except Exception as e:
                    item["state"], item["error"] = "failed", f"{type(e).__name__}: {e}"
                    log(f"{rec['id']}: failed. {item['error']}")
            states = {i["state"] for i in job["items"]}
            job["state"] = "cancelled" if job["_cancel"] else ("failed" if "failed" in states else "done")
        except Exception as e:
            job["state"] = "failed"
            log(f"{type(e).__name__}: {e}")
        finally:
            job["finished"] = time.time()
