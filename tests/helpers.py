"""Test helpers: a throwaway local HTTP server. All fixtures here are SYNTHETIC."""
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
