"""Localhost-only static delivery for the MVP web UI."""

from __future__ import annotations

import functools
import socket
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

__all__ = ["find_available_local_port", "serve_mvp_directory"]


def find_available_local_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def serve_mvp_directory(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
    path: str = "/index.html",
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve ``directory`` on localhost. Returns server, thread, and URL."""

    chosen = port or find_available_local_port(host)
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{chosen}{path}"
    if open_browser:
        webbrowser.open(url)
    return server, thread, url
