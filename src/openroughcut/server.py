"""Minimal local HTTP API for editor integrations (the Premiere Pro panel).

Binds to 127.0.0.1 only. Endpoints:

* ``GET  /health``   -> {"ok": true, "version": ...}
* ``POST /cut``      -> body {"video": "<abs path>", "out_dir": "...", "options": {...CutOptions}}
                        returns {"stats", "outputs", "ai_notes"}
"""

from __future__ import annotations

import json
import threading
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .pipeline import CutOptions, rough_cut

_lock = threading.Lock()  # one job at a time: transcription is CPU-heavy


def options_from_json(data: dict) -> CutOptions:
    known = {f.name for f in fields(CutOptions)}
    kwargs = {k: v for k, v in data.items() if k in known}
    if "formats" in kwargs:
        kwargs["formats"] = tuple(kwargs["formats"])
    return CutOptions(**kwargs)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "version": __version__})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/cut":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            video = Path(req["video"])
            if not video.is_file():
                return self._send(400, {"error": f"file not found: {video}"})
            out_dir = Path(req.get("out_dir") or video.parent / "openroughcut")
            opts = options_from_json(req.get("options", {}))
        except (KeyError, ValueError, TypeError) as e:
            return self._send(400, {"error": f"bad request: {e}"})
        if not _lock.acquire(blocking=False):
            return self._send(409, {"error": "another job is running"})
        try:
            result = rough_cut(video, out_dir, opts, log=lambda *a, **k: print(*a, **k))
            self._send(200, result)
        except Exception as e:  # report any pipeline failure to the panel
            self._send(500, {"error": str(e)})
        finally:
            _lock.release()


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"OpenRoughCut {__version__} listening on http://{host}:{port} (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
