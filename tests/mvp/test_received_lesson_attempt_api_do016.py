"""Direct facade and threaded-server contract for received-lesson attempts."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.education_api import LocalPracticeEvaluationApi
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LESSON_DELIVERY_PREVIEW_PATH,
    LESSON_PRACTICE_CHOICE_PATH,
    LESSON_PRACTICE_PREPARATION_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory
from master_all_strings.mvp.performance_api import LocalPerformanceCaptureApi
from master_all_strings.mvp.received_lesson_attempt_api import (
    LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
    LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
    LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
    LESSON_PRACTICE_ATTEMPT_PATH,
    LocalReceivedLessonAttemptApi,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment(
        (REPO_ROOT / "resources" / "lesson" / "examples" / "local_midi_basic.json").read_text(
            "utf-8"
        )
    )


def _request(
    base: str, method: str, path: str, body: dict[str, Any] | list[Any] | None = None
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path, data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read() or b"{}"
            loaded = json.loads(raw)
            return response.status, loaded if isinstance(loaded, dict) else {"error": raw.decode()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            loaded = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}
        if isinstance(loaded, dict):
            return exc.code, loaded
        return exc.code, {"error": raw.decode("utf-8", "replace")}


def _wire(
    base: str, method: str, path: str, raw: bytes | None = None
) -> tuple[int, dict[str, Any]]:
    host_port = base.removeprefix("http://")
    host, port_text = host_port.rsplit(":", 1)
    payload = raw or b""
    header = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: {host}:{port_text}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    with socket.create_connection((host, int(port_text)), timeout=10) as sock:
        sock.sendall(header + payload)
        chunks = bytearray()
        while True:
            piece = sock.recv(65536)
            if not piece:
                break
            chunks.extend(piece)
    head, _, body = bytes(chunks).partition(b"\r\n\r\n")
    status = int(head.split()[1])
    try:
        loaded = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return status, {"error": body.decode("utf-8", "replace")}
    if isinstance(loaded, dict):
        return status, loaded
    return status, {"error": body.decode("utf-8", "replace")}


def _pins(document: dict[str, Any]) -> dict[str, str]:
    return {
        "delivery_id": document["delivery_id"],
        "expected_assignment_artifact_digest": document["assignment_artifact_digest"],
        "expected_assignment_behavior_digest": document["assignment_behavior_digest"],
    }


@pytest.fixture
def api(assignment: LessonAssignmentV1) -> LocalLessonDeliveryApi:
    facade = LocalLessonDeliveryApi()
    sent = delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id="deliv/ery 1",
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )
    assert facade.handle_http("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    pins = _pins(sent)
    assert facade.handle_http("POST", LESSON_PRACTICE_CHOICE_PATH, pins)[0] == 201
    return facade


@pytest.fixture
def attempts(api: LocalLessonDeliveryApi) -> LocalReceivedLessonAttemptApi:
    return LocalReceivedLessonAttemptApi(api.service, api.choices)


def test_the_facade_begins_appends_and_finishes(
    attempts: LocalReceivedLessonAttemptApi, api: LocalLessonDeliveryApi
) -> None:
    sent = api.service.get("deliv/ery 1")
    body = {
        "delivery_id": "deliv/ery 1",
        "expected_assignment_artifact_digest": sent.assignment_artifact_digest,
        "expected_assignment_behavior_digest": sent.assignment_behavior_digest,
        "device_id": "keyboard-a",
        "capture_time_ns": 1000,
    }
    status, begun = attempts.handle_http("POST", LESSON_PRACTICE_ATTEMPT_PATH, body)
    assert status == 201
    assert begun["delivery_id"] == "deliv/ery 1"
    assert set(begun) == {
        "schema_id",
        "schema_version",
        "attempt_status",
        "attempt_id",
        "capture_id",
        "performance_session_id",
        "delivery_id",
        "assignment_id",
        "content_id",
        "assignment_artifact_digest",
        "assignment_behavior_digest",
        "capture_clock",
        "preparation",
        "attempt_policy",
    }
    event = begun["preparation"]["playback"]["events"][0]
    message = {
        "attempt_id": begun["attempt_id"],
        "sequence_number": 0,
        "capture_time_ns": 2000,
        "practice_position_seconds": event["onset_seconds"],
        "raw_payload": [144, event["midi_note"], 90],
    }
    status, accepted = attempts.handle_http("POST", LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH, message)
    assert status == 200
    assert accepted["accepted_event_count"] == 1
    status, finished = attempts.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        {"attempt_id": begun["attempt_id"], "capture_time_ns": 3000},
    )
    assert status == 200
    assert finished["attempt_status"] == "EVALUATED"
    assert set(finished) == {
        "schema_id",
        "schema_version",
        "attempt_status",
        "attempt_id",
        "capture_id",
        "performance_session_id",
        "delivery_id",
        "assignment_id",
        "content_id",
        "assignment_artifact_digest",
        "assignment_behavior_digest",
        "capture_clock",
        "raw_capture",
        "observed_events",
        "unmatched_note_offs",
        "evaluation",
        "messages",
        "guidance",
        "hardware_status",
    }


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (LESSON_PRACTICE_ATTEMPT_PATH, {"delivery_id": "x", "extra": 1}),
        (
            LESSON_PRACTICE_ATTEMPT_PATH,
            {
                "delivery_id": "deliv/ery 1",
                "expected_assignment_artifact_digest": "sha256:" + "ab" * 32,
                "expected_assignment_behavior_digest": "sha256:" + "cd" * 32,
                "device_id": "keyboard-a",
                "capture_time_ns": True,
            },
        ),
        (LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH, {"attempt_id": "missing", "sequence_number": 0}),
        (LESSON_PRACTICE_ATTEMPT_FINISH_PATH, []),
    ],
)
def test_malformed_bodies_are_only_an_error(
    attempts: LocalReceivedLessonAttemptApi, path: str, body: Any
) -> None:
    status, response = attempts.handle_http("POST", path, body)
    assert status == 400
    assert set(response) == {"error"}
    assert "Traceback" not in response["error"]


def test_unknown_attempt_and_stage5_codes_stay_public(
    attempts: LocalReceivedLessonAttemptApi,
) -> None:
    status, response = attempts.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        {"attempt_id": "missing", "capture_time_ns": 1},
    )
    assert status == 404
    assert response == {"error": "unknown_attempt"}
    status, response = attempts.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_PATH,
        {
            "delivery_id": "nobody-received-this",
            "expected_assignment_artifact_digest": "sha256:" + "ab" * 32,
            "expected_assignment_behavior_digest": "sha256:" + "cd" * 32,
            "device_id": "keyboard-a",
            "capture_time_ns": 1,
        },
    )
    assert status == 404
    assert response == {"error": "unknown_practice_choice"}
    status, response = attempts.handle_http(
        "POST", f"{LESSON_PRACTICE_ATTEMPT_PATH}?delivery_id=x", {}
    )
    assert status == 400
    assert response == {"error": "query string is not allowed"}


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
def test_other_verbs_are_405_on_the_exact_paths(
    attempts: LocalReceivedLessonAttemptApi, method: str
) -> None:
    for path in (
        LESSON_PRACTICE_ATTEMPT_PATH,
        LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
    ):
        status, response = attempts.handle_http(method, path, {})
        assert status == 405
        assert response == {"error": "method not allowed"}


def test_a_serializer_failure_is_sanitized(api: LocalLessonDeliveryApi) -> None:
    def bad_encode(_record: Any) -> dict[str, Any]:
        raise RuntimeError("secret serializer text")

    service_api = LocalReceivedLessonAttemptApi(api.service, api.choices)
    service_api.service._encode_performance = bad_encode  # noqa: SLF001
    sent = api.service.get("deliv/ery 1")
    status, begun = service_api.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_PATH,
        {
            "delivery_id": "deliv/ery 1",
            "expected_assignment_artifact_digest": sent.assignment_artifact_digest,
            "expected_assignment_behavior_digest": sent.assignment_behavior_digest,
            "device_id": "keyboard-a",
            "capture_time_ns": 1,
        },
    )
    assert status == 201
    status, response = service_api.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        {"attempt_id": begun["attempt_id"], "capture_time_ns": 2},
    )
    assert status == 500
    assert response == {"error": "internal server error"}


@pytest.fixture
def server(tmp_path: Path, assignment: LessonAssignmentV1) -> Any:
    facade = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(
        tmp_path,
        open_browser=False,
        lesson_delivery_api=facade,
        performance_api=LocalPerformanceCaptureApi(),
        education_api=LocalPracticeEvaluationApi(),
    )
    base = url.removesuffix("/index.html")

    def call(
        method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        return _request(base, method, path, body)

    call.base = base  # type: ignore[attr-defined]
    call.api = facade  # type: ignore[attr-defined]
    yield call
    httpd.shutdown()
    httpd.server_close()


def test_the_threaded_server_runs_one_attempt(server: Any, assignment: LessonAssignmentV1) -> None:
    sent = delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id="delivery-001",
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    pins = _pins(sent)
    assert server("POST", LESSON_PRACTICE_CHOICE_PATH, pins)[0] == 201
    status, preview = server("GET", f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id=delivery-001")
    assert status == 200
    assert preview["preview_status"] == "READY"
    status, prepared = server("POST", LESSON_PRACTICE_PREPARATION_PATH, pins)
    assert status == 200
    assert prepared["preparation_status"] == "PREPARED"
    status, begun = server(
        "POST",
        LESSON_PRACTICE_ATTEMPT_PATH,
        {**pins, "device_id": "keyboard-a", "capture_time_ns": 10},
    )
    assert status == 201
    status, cancelled = server(
        "POST",
        LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
        {"attempt_id": begun["attempt_id"], "capture_time_ns": 11},
    )
    assert status == 200
    assert cancelled["attempt_status"] == "INTERRUPTED"
    assert "evaluation" not in cancelled
    status, armed = server("POST", "/api/performance/arm", {"device_id": "legacy"})
    assert status == 200
    assert armed["status"] == "armed"
    status, lesson = server(
        "POST",
        "/api/education/begin_lesson",
        {"assignment_id": "a", "content_id": "c"},
    )
    assert status == 200
    assert lesson["status"] == "lesson_ready"
    status, _guided = server("POST", "/api/education/guided-sessions", {"session_id": "s"})
    assert status == 404


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_the_server_refuses_other_methods_only_on_the_exact_route(server: Any, method: str) -> None:
    status, response = _wire(server.base, method, LESSON_PRACTICE_ATTEMPT_PATH, b"{}")
    assert status == 405
    assert response == {"error": "method not allowed"}
    status, off = _wire(server.base, method, LESSON_PRACTICE_ATTEMPT_PATH + "/", b"{}")
    assert status != 405 or off.get("error") != "method not allowed"


@pytest.mark.parametrize(
    "raw",
    [b'{"delivery_id": "\xff"}', b"{", b"[]", b"null"],
)
def test_the_server_rejects_a_bad_body(server: Any, raw: bytes) -> None:
    status, response = _wire(server.base, "POST", LESSON_PRACTICE_ATTEMPT_PATH, raw)
    assert status == 400
    assert set(response) == {"error"}
    assert "Traceback" not in response["error"]


def test_a_post_query_string_is_rejected(server: Any) -> None:
    status, response = server("POST", f"{LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH}?x=1", {})
    assert status == 400
    assert response == {"error": "query string is not allowed"}
