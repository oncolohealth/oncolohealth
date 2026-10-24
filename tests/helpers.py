"""Test helpers: a throwaway local HTTP server and synthetic model files. All fixtures here are SYNTHETIC."""
from __future__ import annotations

import http.server
import json
import threading


class LocalServer:
    """Serves `routes` {path: bytes | callable(handler, body)->(status, bytes)} on 127.0.0.1."""

    def __init__(self, routes: dict):
        routes_ = routes

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self, body: bytes | None):
                route = routes_.get(self.path.split("?")[0])
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if callable(route):
                    status, payload = route(self, body)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                data, start = route, 0
                rng = self.headers.get("Range")
                if rng:
                    start = int(rng.split("=")[1].split("-")[0])
                    self.send_response(206)
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(data) - start))
                self.end_headers()
                self.wfile.write(data[start:])

            def do_GET(self):
                self._serve(None)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                self._serve(json.loads(self.rfile.read(n)) if n else None)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def write_processor_config(folder, encoder_id: str) -> None:
    """Write a SYNTHETIC publisher processor file matching the encoder constants (no real model)."""
    from pathlib import Path

    from cancer_workbench.adapters.encoder import ENCODERS

    spec = ENCODERS[encoder_id]
    if spec["arch"] == "dinov2":
        value = {"size": {"shortest_edge": spec["size"]}, "crop_size": {"height": spec["size"], "width": spec["size"]},
                 "do_resize": True, "do_center_crop": True, "do_rescale": True, "do_normalize": True,
                 "rescale_factor": 1 / 255, "resample": 3, "image_mean": spec["mean"], "image_std": spec["std"]}
    else:
        value = {"architecture": spec["arch"], "pretrained_cfg": {
            "test_input_size": [3, spec["size"], spec["size"]], "test_crop_pct": 1.0, "crop_mode": "center",
            "interpolation": "bicubic", "mean": spec["mean"], "std": spec["std"]}}
    Path(folder, spec["processor_config"]).write_text(json.dumps(value))
