"""Practice choice over a real localhost server.

POST and GET share one exact path. The body is the only place a choice learns
its delivery id, and a second identical POST is the same record. These tests
drive the threaded server so a prefix match, a second percent-decode, or a
choice that also starts a lesson would fail here.
"""

from __future__ import annotations

import json
import socket
import threading
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
from master_all_strings.education.local_practice_choice import (
    CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
    LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
    LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
    LocalPracticeChoiceService,
    LocalPracticeChoiceV1,
)
from master_all_strings.lesson.models import LessonAssignmentV1, LessonRoutingV1, TeacherOverrideV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LESSON_DELIVERY_PREVIEW_PATH,
    LESSON_PRACTICE_CHOICE_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
OTHER_DIGEST = "sha256:" + "cd" * 32


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment(
        (EXAMPLES / "instruction_future_fields.json").read_text(encoding="utf-8")
    )


def payload_for(
    assignment: LessonAssignmentV1,
    delivery_id: str = "delivery-001",
    *,
    recipient_ref: str = "student-bo",
) -> dict[str, Any]:
    return delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id=delivery_id,
            sender_ref="teacher-ana",
            recipient_ref=recipient_ref,
        )
    )


def choice_body(delivery_id: str, artifact: str, behavior: str) -> dict[str, str]:
    return {
        "delivery_id": delivery_id,
        "expected_assignment_artifact_digest": artifact,
        "expected_assignment_behavior_digest": behavior,
    }


def choice_query(delivery_id: str) -> str:
    return f"{LESSON_PRACTICE_CHOICE_PATH}?delivery_id={quote(delivery_id, safe='')}"


def preview_query(delivery_id: str) -> str:
    return f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id={quote(delivery_id, safe='')}"


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
    base: str, method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Read status and body off the socket, including a HEAD response body."""

    host_port = base.removeprefix("http://")
    host, port_text = host_port.rsplit(":", 1)
    payload = json.dumps(body).encode() if body is not None else b""
    headers = [
        f"{method} {path} HTTP/1.1",
        f"Host: {host}:{port_text}",
        "Connection: close",
    ]
    if body is not None:
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
    head, _, raw = data.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    try:
        loaded = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return status, {"error": raw.decode("utf-8", "replace")}
    if isinstance(loaded, dict):
        return status, loaded
    return status, {"error": raw.decode("utf-8", "replace")}


@pytest.fixture
def server(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    api = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(tmp_path, open_browser=False, lesson_delivery_api=api)
    base = url.rsplit("/", 1)[0]

    def request(
        method: str, path: str, body: dict[str, Any] | list[Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        return _request(base, method, path, body)

    request.api = api  # type: ignore[attr-defined]
    request.base = base  # type: ignore[attr-defined]
    try:
        yield request
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_post_preview_choice_and_get_share_one_inbox(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, preview = server("GET", preview_query("delivery-001"))
    assert status == 200
    body = choice_body(
        "delivery-001",
        preview["assignment_artifact_digest"],
        preview["assignment_behavior_digest"],
    )

    status, choice = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 201
    assert choice["schema_id"] == LOCAL_PRACTICE_CHOICE_SCHEMA_ID
    assert choice["schema_version"] == LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION
    assert choice["choice_status"] == CHOICE_STATUS_CHOSEN_FOR_PRACTICE
    assert choice["delivery_id"] == "delivery-001"
    assert choice["assignment_id"] == preview["assignment_id"]
    assert choice["content_id"] == preview["content_id"]
    assert choice["assignment_artifact_digest"] == preview["assignment_artifact_digest"]
    assert choice["assignment_behavior_digest"] == preview["assignment_behavior_digest"]
    for absent in ("sender_ref", "recipient_ref", "accepted", "assignment"):
        assert absent not in choice

    status, fetched_choice = server("GET", choice_query("delivery-001"))
    assert status == 200
    assert fetched_choice == choice
    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert status == 200
    assert fetched == sent
    status, preview_again = server("GET", preview_query("delivery-001"))
    assert status == 200
    assert preview_again == preview


def test_an_identical_second_post_is_200_and_the_same_record(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, first = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 201
    status, second = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 200
    assert second == first


def test_two_concurrent_identical_posts_store_one_choice(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    start = threading.Barrier(2)
    results: list[tuple[int, dict[str, Any]]] = []
    lock = threading.Lock()

    def post() -> None:
        start.wait()
        outcome = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(status for status, _body in results) == [200, 201]
    assert results[0][1] == results[1][1]
    status, fetched = server("GET", choice_query("delivery-001"))
    assert status == 200
    assert fetched == results[0][1]


def test_recipients_do_not_merge_choices(server: Any, assignment: LessonAssignmentV1) -> None:
    first = payload_for(assignment, "delivery-001", recipient_ref="student-bo")
    second = payload_for(assignment, "delivery-002", recipient_ref="student-dee")
    assert server("POST", LESSON_DELIVERY_API_PREFIX, first)[0] == 201
    assert server("POST", LESSON_DELIVERY_API_PREFIX, second)[0] == 201
    left = choice_body(
        "delivery-001",
        first["assignment_artifact_digest"],
        first["assignment_behavior_digest"],
    )
    right = choice_body(
        "delivery-002",
        second["assignment_artifact_digest"],
        second["assignment_behavior_digest"],
    )
    assert server("POST", LESSON_PRACTICE_CHOICE_PATH, left)[0] == 201
    assert server("POST", LESSON_PRACTICE_CHOICE_PATH, right)[0] == 201
    status, fetched = server("GET", choice_query("delivery-001"))
    assert status == 200
    assert fetched["delivery_id"] == "delivery-001"
    status, other = server("GET", choice_query("delivery-002"))
    assert other["delivery_id"] == "delivery-002"
    assert "recipient_ref" not in fetched


@pytest.mark.parametrize(
    "field_name",
    ["assignment_artifact_digest", "assignment_behavior_digest"],
)
def test_a_tampered_stored_digest_is_409_before_a_choice_write(
    server: Any, assignment: LessonAssignmentV1, field_name: str
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    stored = server.api.service.get("delivery-001")
    server.api.service.repository._deliveries["delivery-001"] = replace(
        stored, **{field_name: OTHER_DIGEST}
    )
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 409
    assert response == {"error": "integrity_mismatch"}
    assert server.api.choices.get("delivery-001") is None


@pytest.mark.parametrize("which", ["artifact", "behavior"])
def test_a_stale_expected_digest_is_409_and_does_not_replace_a_choice(
    server: Any, assignment: LessonAssignmentV1, which: str
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, first = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 201
    stale = dict(body)
    stale[
        "expected_assignment_artifact_digest"
        if which == "artifact"
        else "expected_assignment_behavior_digest"
    ] = OTHER_DIGEST
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, stale)
    assert status == 409
    assert response == {"error": "stale_preview"}
    status, fetched = server("GET", choice_query("delivery-001"))
    assert status == 200
    assert fetched == first


def test_an_unresolvable_assignment_is_422_and_stores_no_choice(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    broken = replace(
        assignment,
        teacher_overrides=(
            TeacherOverrideV1(
                event_id="not-in-the-lesson",
                string_id="1",
                physical_fret_number=1,
            ),
        ),
    )
    sent = payload_for(broken, "delivery-broken")
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-broken",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 422
    assert response == {"error": "unresolvable_assignment"}
    status, missing = server("GET", choice_query("delivery-broken"))
    assert status == 404
    assert missing == {"error": "unknown_practice_choice"}


def test_unknown_and_unchosen_deliveries_are_different_404s(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, missing_delivery = server(
        "POST",
        LESSON_PRACTICE_CHOICE_PATH,
        choice_body("missing", sent["assignment_artifact_digest"], OTHER_DIGEST),
    )
    assert status == 404
    assert missing_delivery == {"error": "unknown_delivery_id"}
    status, unchosen = server("GET", choice_query("delivery-001"))
    assert status == 404
    assert unchosen == {"error": "unknown_practice_choice"}
    status, stage1 = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/missing")
    assert status == 404
    assert stage1 == {"error": "unknown delivery_id 'missing'"}


@pytest.mark.parametrize(
    "delivery_id",
    [
        "box/preview",
        "a%2Fpreview",
        "a/b",
        "100%",
        "has space",
        "hash#tag",
        "what?",
        "a&b",
        "lesson-practice-choices",
    ],
)
def test_opaque_ids_round_trip_without_a_second_decode(
    server: Any, assignment: LessonAssignmentV1, delivery_id: str
) -> None:
    sent = payload_for(assignment, delivery_id)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        delivery_id,
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, choice = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 201
    assert choice["delivery_id"] == delivery_id
    status, fetched = server("GET", choice_query(delivery_id))
    assert status == 200
    assert fetched == choice
    status, envelope = server(
        "GET", f"{LESSON_DELIVERY_API_PREFIX}/{quote(delivery_id, safe='')}"
    )
    assert status == 200
    assert envelope["delivery_id"] == delivery_id
    assert "choice_status" not in envelope


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?delivery_id=",
        "?delivery_id=%20%20",
        "?delivery_id=delivery-001&delivery_id=delivery-001",
        "?delivery_id",
    ],
)
def test_missing_blank_or_repeated_choice_identity_is_400(server: Any, query: str) -> None:
    status, body = server("GET", LESSON_PRACTICE_CHOICE_PATH + query)
    assert status == 400
    assert "delivery_id" in body["error"]
    assert "choice_status" not in body


def test_a_padded_id_is_not_the_stored_delivery(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        " delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 404
    assert response == {"error": "unknown_delivery_id"}


@pytest.mark.parametrize(
    "body",
    [
        {"delivery_id": "delivery-001", "choice_status": "ACCEPTED"},
        {"delivery_id": "delivery-001"},
        {
            "delivery_id": "delivery-001",
            "expected_assignment_artifact_digest": "sha256:" + "ab" * 32,
            "expected_assignment_behavior_digest": "sha256:" + "ab" * 32,
            "choice_status": "CHOSEN_FOR_PRACTICE",
        },
        {
            "delivery_id": "delivery-001",
            "expected_assignment_artifact_digest": "sha256:NOPE",
            "expected_assignment_behavior_digest": "sha256:" + "ab" * 32,
        },
        {
            "delivery_id": 1,
            "expected_assignment_artifact_digest": "sha256:" + "ab" * 32,
            "expected_assignment_behavior_digest": "sha256:" + "ab" * 32,
        },
        {
            "delivery_id": "delivery-001",
            "expected_assignment_artifact_digest": None,
            "expected_assignment_behavior_digest": "sha256:" + "ab" * 32,
        },
        {
            "delivery_id": "   ",
            "expected_assignment_artifact_digest": "sha256:" + "ab" * 32,
            "expected_assignment_behavior_digest": "sha256:" + "ab" * 32,
        },
    ],
)
def test_a_malformed_choice_body_is_400_and_writes_nothing(
    server: Any, assignment: LessonAssignmentV1, body: dict[str, Any]
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 400
    assert set(response) == {"error"}
    assert "CHOSEN_FOR_PRACTICE" not in response["error"]
    assert server.api.choices.get("delivery-001") is None


def test_a_query_on_post_is_400_and_the_body_is_not_the_id(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, response = server(
        "POST", f"{LESSON_PRACTICE_CHOICE_PATH}?delivery_id=other", body
    )
    assert status == 400
    assert response == {"error": "query string is not allowed"}
    assert server.api.choices.get("delivery-001") is None
    assert server.api.choices.get("other") is None


def test_a_choice_collision_keeps_the_original_record(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    planted = LocalPracticeChoiceV1(
        schema_id=LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
        schema_version=LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
        choice_status=CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
        delivery_id="delivery-001",
        assignment_id="other-assignment",
        content_id="other-content",
        assignment_artifact_digest=OTHER_DIGEST,
        assignment_behavior_digest=OTHER_DIGEST,
    )
    assert server.api.choices.put_if_absent(planted) is True
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 409
    assert response == {"error": "choice_conflict"}
    assert server.api.choices.get("delivery-001") is planted


def test_get_fails_closed_after_the_delivery_changes(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )
    assert server("POST", LESSON_PRACTICE_CHOICE_PATH, body)[0] == 201
    stored_choice = server.api.choices.get("delivery-001")
    stored = server.api.service.get("delivery-001")
    server.api.service.repository._deliveries["delivery-001"] = replace(
        stored, assignment_artifact_digest=OTHER_DIGEST
    )
    status, response = server("GET", choice_query("delivery-001"))
    assert status == 409
    assert response == {"error": "integrity_mismatch"}
    assert server.api.choices.get("delivery-001") is stored_choice

    rerouted = envelope_for(
        replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b")),
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    server.api.service.repository._deliveries["delivery-001"] = rerouted
    status, response = server("GET", choice_query("delivery-001"))
    assert status == 409
    assert response == {"error": "stale_preview"}
    assert server.api.choices.get("delivery-001") is stored_choice

    broken = envelope_for(
        replace(
            assignment,
            teacher_overrides=(
                TeacherOverrideV1(
                    event_id="not-in-the-lesson",
                    string_id="1",
                    physical_fret_number=1,
                ),
            ),
        ),
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    server.api.service.repository._deliveries["delivery-001"] = broken
    status, response = server("GET", choice_query("delivery-001"))
    assert status == 422
    assert response == {"error": "unresolvable_assignment"}
    assert server.api.choices.get("delivery-001") is stored_choice

    del server.api.service.repository._deliveries["delivery-001"]
    status, response = server("GET", choice_query("delivery-001"))
    assert status == 404
    assert response == {"error": "unknown_delivery_id"}
    assert server.api.choices.get("delivery-001") is stored_choice


@pytest.mark.parametrize("method", ["HEAD", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CUSTOM"])
def test_other_methods_on_the_choice_route_are_405(
    server: Any, assignment: LessonAssignmentV1, method: str
) -> None:
    sent = payload_for(assignment)
    status, body = _wire(server.base, method, LESSON_PRACTICE_CHOICE_PATH, sent)
    assert status == 405
    assert body == {"error": "method not allowed"}
    assert server.api.choices.get("delivery-001") is None
    status, listed = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert listed["count"] == 0


def test_neighboring_routes_keep_their_answers(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    status, _body = server("HEAD", "/index.html")
    assert status == 200
    status, _body = server("PUT", "/index.html")
    assert status == 501
    status, body = server("POST", LESSON_DELIVERY_PREVIEW_PATH, payload_for(assignment))
    assert status == 405
    assert body == {"error": "method not allowed"}
    status, body = _wire(server.base, "GET", f"{LESSON_PRACTICE_CHOICE_PATH}/extra")
    assert "choice_status" not in body
    assert status != 201


def test_a_serializer_failure_is_a_sanitized_500(
    server: Any, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    body = choice_body(
        "delivery-001",
        sent["assignment_artifact_digest"],
        sent["assignment_behavior_digest"],
    )

    def boom(_choice: object) -> dict[str, Any]:
        raise RuntimeError("serializer secret")

    monkeypatch.setattr(
        "master_all_strings.mvp.lesson_delivery_api.choice_to_dict",
        boom,
    )
    status, response = server("POST", LESSON_PRACTICE_CHOICE_PATH, body)
    assert status == 500
    assert response == {"error": "internal server error"}
    assert "serializer secret" not in json.dumps(response)
    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert status == 200
    assert fetched == sent


def test_an_unexpected_choice_failure_is_a_sanitized_500(
    server: Any, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = payload_for(assignment)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret boom")

    monkeypatch.setattr(LocalPracticeChoiceService, "get", boom)
    status, response = server("GET", choice_query("delivery-001"))
    assert status == 500
    assert response == {"error": "internal server error"}
