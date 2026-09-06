#!/usr/bin/env python3
"""
Minimal HTTP serve for SHARED_BODY_SET + digest (Reverie / browser consumers).

  GET /shared_bodies.json   → /tmp/metafield/shared_bodies.json
  GET /obs_digest.json      → /tmp/metafield/obs_digest.json
  GET /head_state.json      → /tmp/metafield/head_state.json
  GET /health               → {"ok": true, …}

CORS * so Vite dev (localhost:5173) can poll.
Fail-soft: missing files return empty SHARED_BODY_SET, not 500.

  python -m observer.shared_body_server
  python -m observer.shared_body_server --port 8765
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SHARED = Path("/tmp/metafield/shared_bodies.json")
DEFAULT_DIGEST = Path("/tmp/metafield/obs_digest.json")
DEFAULT_HEAD = Path("/tmp/metafield/head_state.json")

EMPTY_SET = {
    "schema_version": 1,
    "type": "SHARED_BODY_SET",
    "timestamp": None,
    "source": "throne-room.shared_body_server",
    "pressure": None,
    "n_bodies": 0,
    "bodies": [],
    "note": "no shared_bodies.json yet — start conductor digest loop",
}


def _read_json(path: Path, fallback: dict) -> tuple[dict, int]:
    if not path.exists():
        return fallback, 404
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return fallback, 500
        return data, 200
    except Exception:
        return fallback, 500


class Handler(BaseHTTPRequestHandler):
    shared_path = DEFAULT_SHARED
    digest_path = DEFAULT_DIGEST
    head_path = DEFAULT_HEAD

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[shared-body-server] " + (fmt % args) + "\n")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/shared_bodies", "/shared_bodies.json"):
            data, code = _read_json(self.shared_path, EMPTY_SET)
            # still 200 with empty set so Reverie can poll before first digest
            if code == 404:
                code = 200
            self._json(code, data)
            return
        if path in ("/obs_digest", "/obs_digest.json", "/digest"):
            data, code = _read_json(self.digest_path, {"type": "OBS_PATH_DIGEST", "health": "missing"})
            self._json(200 if code == 404 else code, data)
            return
        if path in ("/head_state", "/head_state.json"):
            data, code = _read_json(self.head_path, {"type": "HEAD_STATE", "ready": False})
            self._json(200 if code == 404 else code, data)
            return
        if path in ("/health", "/"):
            shared_ok = self.shared_path.exists()
            self._json(
                200,
                {
                    "ok": True,
                    "service": "throne-room.shared_body_server",
                    "shared_bodies": str(self.shared_path),
                    "shared_present": shared_ok,
                },
            )
            return
        self._json(404, {"error": "not found", "paths": ["/shared_bodies.json", "/obs_digest.json", "/head_state.json", "/health"]})

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    p = argparse.ArgumentParser(description="Serve SHARED_BODY_SET for Reverie")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--shared", type=Path, default=DEFAULT_SHARED)
    p.add_argument("--digest", type=Path, default=DEFAULT_DIGEST)
    p.add_argument("--head", type=Path, default=DEFAULT_HEAD)
    args = p.parse_args()

    Handler.shared_path = args.shared
    Handler.digest_path = args.digest
    Handler.head_path = args.head

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"[shared-body-server] http://{args.host}:{args.port}/shared_bodies.json",
        flush=True,
    )
    print(f"[shared-body-server] file={args.shared}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[shared-body-server] stop", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
