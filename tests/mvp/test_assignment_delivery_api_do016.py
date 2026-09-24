"""The delivery API over a real localhost server.

A delivery crossing a process boundary is the thing this tranche exists to
prove, so these drive an actual HTTP server rather than calling the API object:
serialization, status codes and routing only count if they survive the wire.

Status codes carry meaning here. A duplicate identity is not the same failure
as a bad digest, and a sender that retried has to be able to tell them apart.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


def payload_for(
    assignment: LessonAssignmentV1,
    delivery_id: str = "delivery-001",
    *,
    recipient_ref: str = "student-bo",
    classroom_ref: str | None = None,
) -> dict[str, Any]:
    return delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id=delivery_id,
            sender_ref="teacher-ana",
            recipient_ref=recipient_ref,
            classroom_ref=classroom_ref,
        )
    )


@pytest.fixture
def server(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    api = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(
        tmp_path, open_browser=False, lesson_delivery_api=api
    )
    base = url.rsplit("/", 1)[0]

    def request(
        method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, method=method, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return exc.code, {"error": raw.decode("utf-8", "replace")}

    try:
        yield request
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_delivery_is_received_over_http(server: Any, assignment: LessonAssignmentV1) -> None:
    status, body = server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment))
    assert status == 201
    assert body["delivery_id"] == "delivery-001"
    assert body["assignment"]["schema_id"] == "master_all_strings.lesson_assignment"


def test_a_received_lesson_comes_back_byte_identical(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    server("POST", LESSON_DELIVERY_API_PREFIX, sent)
    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert status == 200
    assert fetched == sent
    # The point of the whole boundary: the student's copy is the teacher's.
    assert deserialize_lesson_assignment(fetched["assignment"]) == assignment


@pytest.mark.parametrize(
    "delivery_id",
    ["delivery/001", "delivery 001", "delivery#001", "delivery?001", "deliver%y"],
)
def test_an_opaque_id_can_be_fetched_back(
    server: Any, assignment: LessonAssignmentV1, delivery_id: str
) -> None:
    # The promise Stage 1 makes is that what the boundary accepted, the
    # boundary returns. An id containing a character that means something in a
    # URL is still an opaque id -- it was accepted as one, so it has to come
    # back as one.
    from urllib.parse import quote

    status, _ = server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, delivery_id))
    assert status == 201

    encoded = quote(delivery_id, safe="")
    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/{encoded}")
    assert status == 200
    assert fetched["delivery_id"] == delivery_id

    _, listed = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert [item["delivery_id"] for item in listed["deliveries"]] == [delivery_id]


def test_malformed_json_is_refused(server: Any, tmp_path: Path) -> None:
    status, body = server("POST", LESSON_DELIVERY_API_PREFIX, None)
    assert status == 400
    assert "error" in body


def test_a_bad_digest_is_refused(server: Any, assignment: LessonAssignmentV1) -> None:
    tampered = payload_for(assignment)
    tampered["assignment_artifact_digest"] = "sha256:" + "0" * 64
    status, body = server("POST", LESSON_DELIVERY_API_PREFIX, tampered)
    assert status == 400
    assert "assignment_artifact_digest" in body["error"]


def test_an_unknown_field_is_refused(server: Any, assignment: LessonAssignmentV1) -> None:
    extra = payload_for(assignment)
    extra["priority"] = "urgent"
    status, body = server("POST", LESSON_DELIVERY_API_PREFIX, extra)
    assert status == 400
    assert "priority" in body["error"]


def test_a_repeated_delivery_id_is_a_conflict_not_a_bad_request(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment))
    status, body = server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment))
    assert status == 409
    assert "delivery-001" in body["error"]


def test_an_unknown_delivery_is_not_found(server: Any) -> None:
    status, body = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-404")
    assert status == 404
    assert "delivery-404" in body["error"]


def test_listing_is_ordered_and_carries_no_lessons(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    for delivery_id in ("delivery-003", "delivery-001", "delivery-002"):
        server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, delivery_id))
    status, body = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert status == 200
    assert body["count"] == 3
    assert [item["delivery_id"] for item in body["deliveries"]] == [
        "delivery-001",
        "delivery-002",
        "delivery-003",
    ]
    assert all("assignment" not in item for item in body["deliveries"])
    assert all(item["assignment_id"] for item in body["deliveries"])


def test_listing_filters_by_recipient(server: Any, assignment: LessonAssignmentV1) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, "delivery-001"))
    server(
        "POST",
        LESSON_DELIVERY_API_PREFIX,
        payload_for(assignment, "delivery-002", recipient_ref="student-dee"),
    )
    status, body = server("GET", f"{LESSON_DELIVERY_API_PREFIX}?recipient_ref=student-dee")
    assert status == 200
    assert [item["delivery_id"] for item in body["deliveries"]] == ["delivery-002"]
    assert body["recipient_ref"] == "student-dee"


def test_one_lesson_reaches_two_students_unchanged(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, "delivery-001"))
    server(
        "POST",
        LESSON_DELIVERY_API_PREFIX,
        payload_for(assignment, "delivery-002", recipient_ref="student-dee"),
    )
    _, first = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    _, second = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-002")
    assert first["assignment"] == second["assignment"]
    assert first["recipient_ref"] != second["recipient_ref"]


def test_two_simultaneous_deliveries_of_one_id_produce_one_winner(
    tmp_path: Path, assignment: LessonAssignmentV1
) -> None:
    """The race the threading server makes real.

    ``contains()`` then ``put()`` is two operations, and this server handles
    requests on threads: both requests could pass the check before either
    wrote, both be told 201, and one lesson silently replace the other. The
    two payloads carry *different* assignments under one delivery_id so that
    an overwrite is visible rather than merely possible.
    """

    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    httpd, _thread, url = serve_mvp_directory(
        tmp_path, open_browser=False, lesson_delivery_api=LocalLessonDeliveryApi()
    )
    base = url.rsplit("/", 1)[0]
    other = deserialize_lesson_assignment((EXAMPLES / "local_midi_loop.json").read_text("utf-8"))
    payloads = {
        "first": payload_for(assignment, "delivery-001"),
        "second": payload_for(other, "delivery-001", recipient_ref="student-dee"),
    }

    start = threading.Barrier(len(payloads))
    results: dict[str, tuple[int, dict[str, Any]]] = {}

    def post(name: str) -> None:
        body = json.dumps(payloads[name]).encode()
        request = urllib.request.Request(
            base + LESSON_DELIVERY_API_PREFIX,
            data=body,
            method="POST",
            headers={"content-type": "application/json"},
        )
        start.wait(timeout=10)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                results[name] = (response.status, json.loads(response.read() or b"{}"))
        except urllib.error.HTTPError as exc:
            results[name] = (exc.code, json.loads(exc.read() or b"{}"))

    threads = [threading.Thread(target=post, args=(name,)) for name in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    try:
        statuses = Counter(status for status, _ in results.values())
        assert statuses == Counter({201: 1, 409: 1}), results

        winner = next(name for name, (status, _) in results.items() if status == 201)
        request = urllib.request.Request(
            base + f"{LESSON_DELIVERY_API_PREFIX}/delivery-001", method="GET"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            stored = json.loads(response.read())
        assert stored == payloads[winner]

        request = urllib.request.Request(base + LESSON_DELIVERY_API_PREFIX, method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            listed = json.loads(response.read())
        assert listed["count"] == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_an_unexpected_defect_is_a_500_and_says_nothing_else(
    tmp_path: Path, assignment: LessonAssignmentV1
) -> None:
    # A defect in this application is not a malformed request. Answering 400
    # would send a caller looking for a mistake in a correct payload, and the
    # exception's text is not written for whoever is on the other end.
    class BrokenService:
        def receive(self, envelope: object) -> object:
            raise RuntimeError("a database socket in a parallel universe")

        def get(self, delivery_id: str) -> object:
            raise RuntimeError("secret internal detail")

        def list(self, *, recipient_ref: str | None = None) -> object:
            raise RuntimeError("secret internal detail")

    api = LocalLessonDeliveryApi(service=BrokenService())  # type: ignore[arg-type]
    for method, path, payload in (
        ("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment)),
        ("GET", LESSON_DELIVERY_API_PREFIX, {}),
        ("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001", {}),
    ):
        status, body = api.handle_http(method, path, payload)
        assert status == 500
        assert body == {"error": "internal server error"}
        assert "parallel universe" not in json.dumps(body)
        assert "secret internal detail" not in json.dumps(body)


@pytest.mark.parametrize(
    "path",
    [
        "/api/education/lesson-deliveries-summary",
        "/api/education/lesson-deliveriesX",
        "/api/education/lesson-deliveries-not-a-route",
    ],
)
def test_a_sibling_route_is_not_swallowed_by_the_delivery_prefix(
    server: Any, path: str
) -> None:
    # The route owns its own path, not every path beginning with its name.
    # Under a startswith match these arrived at the delivery handler and were
    # read as delivery identities, so a sibling route added later would have
    # answered 404 from the wrong place.
    from master_all_strings.mvp.local_server import _is_lesson_delivery

    assert not _is_lesson_delivery(path)
    status, _ = server("GET", path)
    assert status == 404


def test_the_route_still_owns_its_own_paths() -> None:
    from master_all_strings.mvp.local_server import _is_lesson_delivery

    assert _is_lesson_delivery(LESSON_DELIVERY_API_PREFIX)
    assert _is_lesson_delivery(f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert _is_lesson_delivery(f"{LESSON_DELIVERY_API_PREFIX}/")
