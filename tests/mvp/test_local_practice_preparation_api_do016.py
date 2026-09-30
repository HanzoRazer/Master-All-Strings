"""Preparation over the localhost API and a real threaded server.

The body is the only place a preparation learns its delivery id. A method
other than POST on the exact path is refused, and a failure is a code with
no bundle fields attached.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.models import LessonAssignmentV1, LessonRoutingV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LESSON_DELIVERY_PREVIEW_PATH,
    LESSON_PRACTICE_CHOICE_PATH,
    LESSON_PRACTICE_PREPARATION_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_practice_preparation import preparation_to_dict
from master_all_strings.mvp.local_server import serve_mvp_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
OTHER = "sha256:" + "cd" * 32


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment(
        (EXAMPLES / "local_midi_basic.json").read_text(encoding="utf-8")
    )


def payload_for(
    assignment: LessonAssignmentV1, delivery_id: str = "delivery-001"
) -> dict[str, Any]:
    return delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id=delivery_id,
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )


def body_for(delivery_id: str, artifact: str, behavior: str) -> dict[str, str]:
    return {
        "delivery_id": delivery_id,
        "expected_assignment_artifact_digest": artifact,
        "expected_assignment_behavior_digest": behavior,
    }


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
    headers = [
        f"{method} {path} HTTP/1.1",
        f"Host: {host}:{port_text}",
        "Connection: close",
    ]
    if raw is not None:
        headers.append("content-type: application/json")
        headers.append(f"content-length: {len(payload)}")
    request = ("\r\n".join(headers) + "\r\n\r\n").encode() + payload
    with socket.create_connection((host, int(port_text)), timeout=5) as sock:
        sock.sendall(request)
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    try:
        loaded = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return status, {"error": body.decode("utf-8", "replace")}
    if isinstance(loaded, dict):
        return status, loaded
    return status, {"error": body.decode("utf-8", "replace")}


@pytest.fixture
def api() -> LocalLessonDeliveryApi:
    return LocalLessonDeliveryApi()


@pytest.fixture
def server(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    lesson_api = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(
        tmp_path, open_browser=False, lesson_delivery_api=lesson_api
    )
    base = url.rsplit("/", 1)[0]

    def request(
        method: str, path: str, body: dict[str, Any] | list[Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        return _request(base, method, path, body)

    request.api = lesson_api  # type: ignore[attr-defined]
    request.base = base  # type: ignore[attr-defined]
    try:
        yield request
    finally:
        httpd.shutdown()
        httpd.server_close()


def _choose(api: LocalLessonDeliveryApi, sent: dict[str, Any]) -> dict[str, str]:
    assert api.handle_http("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = body_for(
        sent["delivery_id"],
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    assert api.handle_http("POST", LESSON_PRACTICE_CHOICE_PATH, body)[0] == 201
    return body


def test_the_api_prepares_a_chosen_delivery(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    body = _choose(api, sent)
    status, document = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 200
    assert document["preparation_status"] == "PREPARED"
    assert document["delivery_id"] == "delivery-001"
    assert document["assignment_artifact_digest"] == sent["assignment_artifact_digest"]
    assert document["assignment_behavior_digest"] == sent["assignment_behavior_digest"]
    assert document["projection"]["demo_id"] is None
    assert "error" not in document
    assert set(document["score"]) == {"canonical_revision", "tab", "notation"}


def test_direct_request_validation_rejects_the_body(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    body = _choose(api, sent)
    cases: list[dict[str, Any] | list[Any]] = [
        {},
        {"delivery_id": "delivery-001"},
        {**body, "choice_status": "CHOSEN_FOR_PRACTICE"},
        {**body, "delivery_id": ""},
        {**body, "delivery_id": 7},
        {**body, "expected_assignment_artifact_digest": "sha256:abcd"},
        {**body, "expected_assignment_behavior_digest": None},
    ]
    for case in cases:
        status, response = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, case)  # type: ignore[arg-type]
        assert status == 400
        assert set(response) == {"error"}
        assert "PREPARED" not in json.dumps(response)
    status, response = api.handle_http(
        "POST", LESSON_PRACTICE_PREPARATION_PATH + "?delivery_id=delivery-001", body
    )
    assert status == 400
    assert response == {"error": "query string is not allowed"}


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_direct_methods_other_than_post_are_405(
    api: LocalLessonDeliveryApi, method: str
) -> None:
    status, response = api.handle_http(method, LESSON_PRACTICE_PREPARATION_PATH, {})
    assert status == 405
    assert response == {"error": "method not allowed"}


@pytest.mark.parametrize(
    "delivery_id",
    ["box/inner", "a%2Fb", "has space", "hash#tag", "what?", "a&b"],
)
def test_opaque_ids_are_preserved(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1, delivery_id: str
) -> None:
    sent = payload_for(assignment, delivery_id)
    body = _choose(api, sent)
    status, document = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 200
    assert document["delivery_id"] == delivery_id


def test_named_failures_carry_no_bundle(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert api.handle_http("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, response = api.handle_http(
        "POST",
        LESSON_PRACTICE_PREPARATION_PATH,
        body_for(
            "delivery-001",
            sent["assignment_artifact_digest"],
            sent["assignment_behavior_digest"],
        ),
    )
    assert status == 404
    assert response == {"error": "unknown_practice_choice"}

    body = body_for(
        "delivery-001", sent["assignment_artifact_digest"], sent["assignment_behavior_digest"]
    )
    assert api.handle_http("POST", LESSON_PRACTICE_CHOICE_PATH, body)[0] == 201
    status, document = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 200
    assert document["preparation_status"] == "PREPARED"

    stale = dict(body)
    stale["expected_assignment_artifact_digest"] = OTHER
    status, response = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, stale)
    assert status == 409
    assert response == {"error": "stale_preview"}


def test_a_direct_pipeline_failure_is_sanitized(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = payload_for(assignment)
    body = _choose(api, sent)

    def boom(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("secret pipeline")

    monkeypatch.setattr(
        "master_all_strings.mvp.application.MvpApplication.run_assignment_json", boom
    )
    status, response = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 500
    assert response == {"error": "internal server error"}


def test_serializing_the_document_is_inside_the_boundary(
    api: LocalLessonDeliveryApi, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = payload_for(assignment)
    body = _choose(api, sent)

    def boom(_prepared: object) -> dict[str, Any]:
        raise RuntimeError("secret serialization")

    monkeypatch.setattr(
        "master_all_strings.mvp.lesson_delivery_api.preparation_to_dict", boom
    )
    status, response = api.handle_http("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 500
    assert response == {"error": "internal server error"}
    assert preparation_to_dict.__name__ == "preparation_to_dict"


def test_the_server_prepares_and_shuts_down(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, preview = server(
        "GET", f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id={quote('delivery-001', safe='')}"
    )
    assert status == 200
    assert preview["preview_status"] == "READY"
    body = body_for(
        "delivery-001", preview["assignment_artifact_digest"], preview["assignment_behavior_digest"]
    )
    status, choice = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 201
    status, document = server("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 200
    assert document["preparation_status"] == "PREPARED"
    assert document["delivery_id"] == choice["delivery_id"]
    status, _index = server("HEAD", "/index.html")
    assert status == 200


@pytest.mark.parametrize(
    "raw",
    [
        b'{"delivery_id": "\xff"}',
        b"{",
        b"[]",
        b"null",
        b'{"delivery_id": "delivery-001"}',
    ],
)
def test_the_server_rejects_a_bad_body(server: Any, raw: bytes) -> None:
    status, response = _wire(server.base, "POST", LESSON_PRACTICE_PREPARATION_PATH, raw)
    assert status == 400
    assert set(response) == {"error"}
    assert "Traceback" not in response["error"]


def test_a_post_query_string_is_rejected(server: Any, assignment: LessonAssignmentV1) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = body_for(
        "delivery-001", sent["assignment_artifact_digest"], sent["assignment_behavior_digest"]
    )
    status, response = server(
        "POST", f"{LESSON_PRACTICE_PREPARATION_PATH}?delivery_id=delivery-001", body
    )
    assert status == 400
    assert response == {"error": "query string is not allowed"}


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_the_server_refuses_other_methods_only_on_the_exact_route(
    server: Any, method: str
) -> None:
    status, response = _wire(server.base, method, LESSON_PRACTICE_PREPARATION_PATH, b"{}")
    assert status == 405
    assert response == {"error": "method not allowed"}
    status, off = _wire(server.base, method, LESSON_PRACTICE_PREPARATION_PATH + "/", b"{}")
    assert status != 405 or off.get("error") != "method not allowed"


def test_neighboring_routes_keep_their_answers(server: Any, assignment: LessonAssignmentV1) -> None:
    status, _body = server("HEAD", "/index.html")
    assert status == 200
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, preview = server(
        "GET", f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id=delivery-001"
    )
    assert status == 200
    assert preview["preview_status"] == "READY"
    status, missing = server(
        "GET", f"{LESSON_PRACTICE_CHOICE_PATH}?delivery_id={quote('delivery-001', safe='')}"
    )
    assert status == 404
    assert missing == {"error": "unknown_practice_choice"}
    status, _guided = server("POST", "/api/education/guided-sessions", {"session_id": "s"})
    assert status == 404
    status, _static_post = server("POST", "/not-a-route", {"a": 1})
    assert status == 404


def test_server_failures_do_not_change_the_inbox(
    server: Any, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = body_for(
        "delivery-001", sent["assignment_artifact_digest"], sent["assignment_behavior_digest"]
    )
    assert server("POST", LESSON_PRACTICE_CHOICE_PATH, body)[0] == 201
    stored_delivery = server.api.service.repository._deliveries["delivery-001"]  # noqa: SLF001
    stored_choice = server.api.choices.get("delivery-001")

    def boom(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("secret pipeline")

    monkeypatch.setattr(
        "master_all_strings.mvp.application.MvpApplication.run_assignment_json", boom
    )
    status, response = server("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 500
    assert response == {"error": "internal server error"}
    assert "secret" not in json.dumps(response)
    assert server.api.service.repository._deliveries["delivery-001"] is stored_delivery  # noqa: SLF001
    assert server.api.choices.get("delivery-001") is stored_choice

    rerouted = envelope_for(
        replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b")),
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    server.api.service.repository._deliveries["delivery-001"] = rerouted  # noqa: SLF001
    monkeypatch.undo()
    status, response = server("POST", LESSON_PRACTICE_PREPARATION_PATH, body)
    assert status == 409
    assert response == {"error": "stale_preview"}
    assert set(response) == {"error"}
