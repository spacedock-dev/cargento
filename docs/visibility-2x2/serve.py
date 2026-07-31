#!/usr/bin/env python3
"""Tiny local server for the Cargento Visibility 2x2 working session.

Serves index.html and re-reads items.json on every request, so edits to the
data show up on a browser refresh without restarting anything.

    python3 serve.py --port 8899
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                body = (HERE / "index.html").read_bytes()
            except OSError as exc:
                self._send(500, str(exc).encode(), "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
        elif path == "/api/items":
            try:
                raw = (HERE / "items.json").read_text(encoding="utf-8")
                json.loads(raw)  # fail loudly on malformed edits
            except (OSError, json.JSONDecodeError) as exc:
                self._send(
                    500,
                    json.dumps({"error": str(exc)}).encode(),
                    "application/json; charset=utf-8",
                )
                return
            self._send(200, raw.encode("utf-8"), "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _read_items_body(self) -> dict[str, Any]:
        """Parse and sanity-check a POSTed items document, or raise ValueError."""
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4_000_000:
            msg = f"bad content length {n}"
            raise ValueError(msg)
        payload = json.loads(self.rfile.read(n).decode("utf-8"))
        if not isinstance(payload, dict) or not payload.get("items"):
            msg = "payload is not the items document"
            raise ValueError(msg)
        return payload

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/save":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            payload = self._read_items_body()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send(
                400, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8"
            )
            return

        target = HERE / "items.json"
        try:
            # keep the previous good copy, then swap the new one in atomically
            if target.exists():
                (HERE / "items.bak.json").write_text(
                    target.read_text(encoding="utf-8"), encoding="utf-8"
                )
            tmp = HERE / "items.json.tmp"
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            tmp.replace(target)
        except OSError as exc:
            self._send(
                500, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8"
            )
            return
        self._send(
            200,
            json.dumps({"ok": True, "items": len(payload["items"])}).encode(),
            "application/json; charset=utf-8",
        )

    def log_message(self, fmt: str, *args: object) -> None:
        """Stay quiet; the default handler logs every request to stderr."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"could not bind 127.0.0.1:{args.port} — {exc}", file=sys.stderr, flush=True)
        return 1
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Visibility 2x2 → {url}   (ctrl-c to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
