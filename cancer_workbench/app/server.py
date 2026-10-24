"""Local web app server (standard library only). Binds to 127.0.0.1.

Every request must carry the right Host header (blocks DNS rebinding) and
every /api call must carry the per-launch token injected into the page
(blocks other websites from driving this server through your browser).
"""
from __future__ import annotations

import http.server
import json
import secrets
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from pathlib import Path

from . import api

STATIC = Path(__file__).with_name("static")
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(token: str, port_ref: dict):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "CancerWorkbench"

        def log_message(self, fmt, *args):
            if "/api/jobs" not in (args[0] if args else ""):
                sys.stderr.write("  %s\n" % (fmt % args))

        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _host_ok(self) -> bool:
            port = port_ref["port"]
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _api(self, method: str):
            if self.headers.get("X-CW-Token") != token:
                return self._json(403, {"error": "Missing or wrong app token. Reload the page."})
            path = urllib.parse.urlsplit(self.path).path
            try:
                if method == "GET":
                    if path in api.GET_ROUTES:
                        return self._json(200, api.GET_ROUTES[path]())
                    for prefix, fn in api.GET_PARAM_ROUTES.items():
                        if path.startswith(prefix):
                            return self._json(200, fn(urllib.parse.unquote(path[len(prefix):])))
                else:
                    if path in api.POST_ROUTES:
                        n = int(self.headers.get("Content-Length") or 0)
                        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                        return self._json(200, api.POST_ROUTES[path](body))
                return self._json(404, {"error": f"No such endpoint: {path}"})
            except api.ApiError as e:
                return self._json(e.status, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self):
            if not self._host_ok():
                return self._send(421, b"wrong host", "text/plain")
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith("/api/"):
                return self._api("GET")
            if path in STATIC_FILES:
                name, ctype = STATIC_FILES[path]
                body = (STATIC / name).read_bytes()
                if name == "index.html":
                    body = body.replace(b"__CW_TOKEN__", token.encode())
                return self._send(200, body, ctype)
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._host_ok():
                return self._send(421, b"wrong host", "text/plain")
            if not urllib.parse.urlsplit(self.path).path.startswith("/api/"):
                return self._send(404, b"not found", "text/plain")
            self._api("POST")

    return Handler


def serve(port: int = 8765, open_browser: bool = True) -> None:
    token = secrets.token_urlsafe(24)
    port_ref = {"port": port}
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, port_ref))
    port_ref["port"] = httpd.server_address[1]
    url = f"http://127.0.0.1:{port_ref['port']}/"
    print(f"Cancer workbench running at {url}  (Ctrl+C to stop)", file=sys.stderr)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
