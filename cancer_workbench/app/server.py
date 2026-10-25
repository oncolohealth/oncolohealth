"""Local web app server (standard library only). Binds to 127.0.0.1.

Every request must carry the right Host header (blocks DNS rebinding) and
every /api call must carry the per-launch token injected into the page
(blocks other websites from driving this server through your browser).
/media/ image requests carry the same token as a `t` query parameter,
because <img> tags can't send headers.
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
MAX_BODY = 32_000_000  # a base64 upload of api.MAX_UPLOAD plus JSON
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(token: str, port_ref: dict):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "CancerWorkbench"

        def log_message(self, fmt, *args):
            line = str(args[0]) if args else ""
            if "/api/jobs" not in line and "/media/" not in line:
                sys.stderr.write("  %s\n" % (fmt % args))

        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
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
                    if path in api.POST_ROUTES or path in api.STREAM_ROUTES:
                        n = int(self.headers.get("Content-Length") or 0)
                        if n > MAX_BODY:
                            return self._json(413, {"error": "Request too large."})
                        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                        if path in api.STREAM_ROUTES:
                            return self._stream(api.STREAM_ROUTES[path], body)
                        return self._json(200, api.POST_ROUTES[path](body))
                return self._json(404, {"error": f"No such endpoint: {path}"})
            except api.ApiError as e:
                return self._json(e.status, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def _stream(self, fn, body: dict) -> None:
            """Newline-delimited JSON, one event per line, flushed as it happens. The response has no
            length, so the connection closes when the handler returns. Once streaming has started,
            failures are sent as {"type": "error"} events instead of an HTTP status."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def emit(event: dict) -> None:
                # A closed browser tab raises here (BrokenPipe/ConnectionReset), which ends the turn.
                self.wfile.write(json.dumps(event).encode() + b"\n")
                self.wfile.flush()

            gone = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
            try:
                fn(body, emit)
            except gone:
                return
            except Exception as e:
                if not isinstance(e, api.ApiError):
                    traceback.print_exc()
                try:
                    emit({"type": "error", "error": str(e) if isinstance(e, api.ApiError) else f"{type(e).__name__}: {e}"})
                except gone:
                    pass

        def _media(self, url):
            if urllib.parse.parse_qs(url.query).get("t") != [token]:
                return self._send(403, b"missing or wrong app token", "text/plain")
            try:
                p, ctype = api.media_file(urllib.parse.unquote(url.path[len("/media/"):]))
            except api.ApiError:
                return self._send(404, b"not found", "text/plain")
            self._send(200, p.read_bytes(), ctype, cache="private, max-age=3600")

        def do_GET(self):
            if not self._host_ok():
                return self._send(421, b"wrong host", "text/plain")
            url = urllib.parse.urlsplit(self.path)
            path = url.path
            if path.startswith("/api/"):
                return self._api("GET")
            if path.startswith("/media/"):
                return self._media(url)
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
