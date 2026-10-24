"""In-memory progress for one live scoring batch at a time (stdlib only)."""
from __future__ import annotations

import copy
import threading
import time
import uuid


class ScoringJobs:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def get(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError("Scoring session expired. Select images and score again.")
            return copy.deepcopy(self._jobs[job_id])

    def current(self) -> dict | None:
        """Recover the latest batch after a reload, even before its start response arrived."""
        with self._lock:
            return copy.deepcopy(next(reversed(self._jobs.values()))) if self._jobs else None

    def start(self, run: str, result: str, total: int, work, keys=None) -> dict:
        with self._lock:
            if any(j["state"] == "running" for j in self._jobs.values()):
                raise ValueError("A live scoring batch is already running. Wait for it to finish.")
            # Keep a bounded history for clients still reading a finished job.
            while len(self._jobs) >= 8:
                del self._jobs[next(iter(self._jobs))]
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "run": run, "result": result, "total": total, "done": 0,
                   "state": "running", "stage": "preparing", "current": None, "items": [],
                   "started": time.time(), "seconds": 0, "error": None, "response": None,
                   "keys": list(keys or [])}
            self._jobs[job_id] = job
            snapshot = copy.deepcopy(job)

        def update(progress):
            with self._lock:
                job.update(copy.deepcopy(progress))

        def execute():
            started = time.monotonic()
            try:
                response = work(update)
                update({"state": "done", "stage": "done", "current": None, "done": total,
                        "items": response["items"], "response": response,
                        "seconds": round(time.monotonic() - started, 2)})
            except Exception as exc:
                update({"state": "failed", "stage": "failed", "current": None,
                        "error": str(exc) or type(exc).__name__,
                        "seconds": round(time.monotonic() - started, 2)})

        threading.Thread(target=execute, daemon=True).start()
        return snapshot
