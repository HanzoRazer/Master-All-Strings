"""Localhost-only static delivery for the MVP web UI."""

from __future__ import annotations

import functools
import json
import mimetypes
import socket
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from master_all_strings.media.catalog import default_media_root
from master_all_strings.media.presentation import lesson_media_payload
from master_all_strings.media.resolver import MediaResolver

__all__ = ["find_available_local_port", "serve_mvp_directory"]


def find_available_local_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class _QuietHandler(SimpleHTTPRequestHandler):
    performance_api: Any = None
    education_api: Any = None
    media_root: Path | None = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/v1/lessons/") and path.endswith("/media"):
            lesson_key = path[len("/api/v1/lessons/") : -len("/media")].strip("/")
            if not lesson_key or "/" in lesson_key:
                self.send_error(400, "invalid lesson key")
                return
            root = self.media_root or default_media_root()
            try:
                payload = lesson_media_payload(lesson_key, root=root)
            except FileNotFoundError:
                payload = {
                    "schema_version": "1.0.0",
                    "lesson_key": lesson_key,
                    "items": [],
                    "available_count": 0,
                    "unavailable_count": 0,
                    "status": "ready",
                    "message": None,
                }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/media/assets/"):
            relative = path[len("/media/assets/") :]
            root = self.media_root or default_media_root()
            resolver = MediaResolver(asset_root=root / "examples")
            try:
                asset = resolver.resolve_path(relative)
            except Exception:
                self.send_error(404, "media not found")
                return
            if not asset.is_file():
                self.send_error(404, "media not found")
                return
            data = asset.read_bytes()
            mime, _ = mimetypes.guess_type(str(asset))
            self.send_response(200)
            self.send_header("content-type", mime or "application/octet-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        api = None
        if self.path.startswith("/api/performance/") and self.performance_api is not None:
            api = self.performance_api
        elif self.path.startswith("/api/education/") and self.education_api is not None:
            api = self.education_api
        else:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = api.handle(self.path.rsplit("/", 1)[-1], payload)
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
    education_api: object | None = None,
    media_root: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve ``directory`` on localhost. Returns server, thread, and URL."""

    chosen = port or find_available_local_port(host)

    class Handler(_QuietHandler):
        pass

    Handler.performance_api = performance_api
    Handler.education_api = education_api
    Handler.media_root = media_root or default_media_root()
    handler = functools.partial(Handler, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{chosen}{path}"
    if open_browser:
        webbrowser.open(url)
    return server, thread, url
