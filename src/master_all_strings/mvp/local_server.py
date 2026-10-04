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
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_PREVIEW_PATH,
    LESSON_PRACTICE_CHOICE_PATH,
    LESSON_PRACTICE_PREPARATION_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.received_lesson_attempt_api import (
    ATTEMPT_PATHS,
    LocalReceivedLessonAttemptApi,
)

__all__ = ["find_available_local_port", "serve_mvp_directory"]


def find_available_local_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


_LESSON_DELIVERY_PREFIX = "/api/education/lesson-deliveries"


def _is_lesson_delivery(path: str) -> bool:
    """The route owns its own path, not every path beginning with its name.

    ``startswith`` would claim ``/api/education/lesson-deliveries-summary`` for
    the delivery API and read "-summary" as a delivery identity, so a sibling
    route added later would return 404 from the wrong handler.
    """

    return path == _LESSON_DELIVERY_PREFIX or path.startswith(_LESSON_DELIVERY_PREFIX + "/")


def _is_lesson_delivery_preview(path: str) -> bool:
    """Exact sibling of the delivery collection.

    ``lesson-delivery-preview`` shares a prefix with nothing we already route
    only when the comparison is equality. A delivery id that ends in
    ``/preview`` still belongs to the collection route.
    """

    return path == LESSON_DELIVERY_PREVIEW_PATH


def _is_lesson_practice_choice(path: str) -> bool:
    """Exact collection, not a delivery id and not the preview sibling."""

    return path == LESSON_PRACTICE_CHOICE_PATH


def _is_lesson_practice_preparation(path: str) -> bool:
    """Exact collection. A trailing slash is a different path."""

    return path == LESSON_PRACTICE_PREPARATION_PATH


def _is_received_lesson_attempt(path: str) -> bool:
    """Exact attempt routes. A trailing slash is a different path."""

    return path in ATTEMPT_PATHS


def _is_closed_education_method(path: str) -> bool:
    """Routes whose unsupported verbs are 405 rather than a static 501."""

    return (
        _is_lesson_delivery_preview(path)
        or _is_lesson_practice_choice(path)
        or _is_lesson_practice_preparation(path)
        or _is_received_lesson_attempt(path)
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    performance_api: Any = None
    education_api: Any = None
    guided_session_api: Any = None
    lesson_delivery_api: Any = None
    attempt_api: Any = None
    media_root: Path | None = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if _is_received_lesson_attempt(path):
            self._attempt_http("GET", parsed.geturl(), {})
            return
        if _is_closed_education_method(path):
            # Query stays encoded. The API decodes delivery_id once.
            self._lesson_delivery_http("GET", parsed.geturl(), {})
            return
        if path.startswith("/api/education/guided-sessions"):
            self._guided_session_http("GET", path, {})
            return
        if _is_lesson_delivery(path):
            self._lesson_delivery_http("GET", parsed.geturl(), {})
            return
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

    def do_HEAD(self) -> None:  # noqa: N802
        # The static handler's inherited HEAD serves a file and would answer
        # this path with 404. The preview route's only success method is GET.
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if _is_received_lesson_attempt(path):
            self._discard_body()
            self._attempt_http("HEAD", parsed.geturl(), {})
            return
        if _is_closed_education_method(path):
            self._discard_body()
            self._lesson_delivery_http("HEAD", parsed.geturl(), {})
            return
        super().do_HEAD()

    def do_PUT(self) -> None:  # noqa: N802
        self._preview_or_unsupported("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._preview_or_unsupported("DELETE")

    def __getattr__(self, name: str) -> Any:
        """Verbs this class does not declare still meet the preview refusal.

        ``BaseHTTPRequestHandler`` answers an unimplemented verb with 501
        before any route code runs. On the preview path that would break the
        promise that every method other than GET is 405. Elsewhere the 501
        stands.
        """

        if not name.startswith("do_"):
            raise AttributeError(name)
        method = name.removeprefix("do_")

        def respond() -> None:
            self._preview_or_unsupported(method)

        return respond

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if _is_lesson_delivery_preview(path):
            self._discard_body()
            self._lesson_delivery_http("POST", parsed.geturl(), {})
            return
        if _is_received_lesson_attempt(path):
            if parsed.query:
                self._discard_body()
                self._attempt_http("POST", parsed.geturl(), {})
                return
            payload_or_error = self._json_body()
            if payload_or_error is None:
                return
            self._attempt_http("POST", parsed.geturl(), payload_or_error)
            return
        if _is_lesson_practice_choice(path) or _is_lesson_practice_preparation(path):
            if parsed.query:
                self._discard_body()
                self._lesson_delivery_http("POST", parsed.geturl(), {})
                return
            payload_or_error = self._json_body()
            if payload_or_error is None:
                return
            self._lesson_delivery_http("POST", parsed.geturl(), payload_or_error)
            return
        if path.startswith("/api/education/guided-sessions"):
            try:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                body = json.dumps({"error": "malformed JSON"}).encode()
                self.send_response(400)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if not isinstance(payload, dict):
                body = json.dumps({"error": "payload must be an object"}).encode()
                self.send_response(400)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._guided_session_http("POST", path, payload)
            return
        if _is_lesson_delivery(path):
            payload_or_error = self._json_body()
            if payload_or_error is None:
                return
            self._lesson_delivery_http("POST", parsed.geturl(), payload_or_error)
            return
        api = None
        if path.startswith("/api/performance/") and self.performance_api is not None:
            api = self.performance_api
        elif path.startswith("/api/education/") and self.education_api is not None:
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

    def _preview_or_unsupported(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if _is_received_lesson_attempt(path):
            self._discard_body()
            self._attempt_http(method, parsed.geturl(), {})
            return
        if _is_closed_education_method(path):
            self._discard_body()
            self._lesson_delivery_http(method, parsed.geturl(), {})
            return
        self.send_error(501, f"Unsupported method ({method!r})")

    def _discard_body(self) -> None:
        raw = self.headers.get("content-length", "0")
        try:
            length = int(raw)
        except ValueError:
            return
        if length > 0:
            self.rfile.read(length)

    def _json_body(self) -> dict[str, Any] | None:
        """Read a JSON object body, answering 400 itself when it is not one."""

        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json_response(400, {"error": "malformed JSON"})
            return None
        if not isinstance(payload, dict):
            self._json_response(400, {"error": "payload must be an object"})
            return None
        return payload

    def _json_response(self, status: int, result: dict[str, Any]) -> None:
        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _attempt_http(self, method: str, path: str, payload: dict[str, Any]) -> None:
        api = self.attempt_api
        if api is None:
            self.send_error(404, "lesson attempt API is not enabled")
            return
        status, result = api.handle_http(method, path, payload)
        self._json_response(status, result)

    def _lesson_delivery_http(self, method: str, path: str, payload: dict[str, Any]) -> None:
        api = self.lesson_delivery_api
        if api is None:
            self.send_error(404, "lesson delivery API is not enabled")
            return
        status, result = api.handle_http(method, path, payload)
        self._json_response(status, result)

    def _guided_session_http(self, method: str, path: str, payload: dict[str, Any]) -> None:
        api = self.guided_session_api
        if api is None:
            self.send_error(404, "guided session API is not enabled")
            return
        status, result = api.handle_http(method, path, payload)
        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
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
    guided_session_api: object | None = None,
    lesson_delivery_api: LocalLessonDeliveryApi | None = None,
    media_root: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve ``directory`` on localhost. Returns server, thread, and URL."""

    chosen = port or find_available_local_port(host)

    class Handler(_QuietHandler):
        pass

    Handler.performance_api = performance_api
    Handler.education_api = education_api
    Handler.guided_session_api = guided_session_api
    delivery = lesson_delivery_api or LocalLessonDeliveryApi()
    Handler.lesson_delivery_api = delivery
    # Same inbox and choice store as Stage 5. A second pair would prepare a
    # lesson the delivery routes cannot see.
    Handler.attempt_api = LocalReceivedLessonAttemptApi(delivery.service, delivery.choices)
    Handler.media_root = media_root or default_media_root()
    handler = functools.partial(Handler, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{chosen}{path}"
    if open_browser:
        webbrowser.open(url)
    return server, thread, url
