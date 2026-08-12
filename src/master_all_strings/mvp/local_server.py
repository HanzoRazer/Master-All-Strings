"""Localhost-only static delivery for the MVP web UI."""

from __future__ import annotations

import functools
import json
import socket
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

__all__ = ["find_available_local_port", "serve_mvp_directory"]


def find_available_local_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class _QuietHandler(SimpleHTTPRequestHandler):
    performance_api: Any = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/performance/") or self.performance_api is None:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = self.performance_api.handle(self.path.rsplit("/", 1)[-1], payload)
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = str(exc).encode()
            self.send_response(400)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def serve_mvp_directory(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
    path: str = "/index.html",
    performance_api: object | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve ``directory`` on localhost. Returns server, thread, and URL."""

    chosen = port or find_available_local_port(host)

    class Handler(_QuietHandler):
        pass

    Handler.performance_api = performance_api
    handler = functools.partial(Handler, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{chosen}{path}"
    if open_browser:
        webbrowser.open(url)
    return server, thread, url
