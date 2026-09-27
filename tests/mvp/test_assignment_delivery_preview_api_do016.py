"""Preview over a real localhost server.

Selecting a delivery is a query on a sibling route, not a path under the
collection. These tests drive the threaded server so a prefix match, a second
percent-decode, or a preview that also writes would fail here rather than only
in a direct function call.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.models import LessonAssignmentV1, TeacherOverrideV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LESSON_DELIVERY_PREVIEW_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"


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


def _request(
    base: str, method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path, data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            loaded = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"error": raw.decode("utf-8", "replace")}
        if isinstance(loaded, dict):
            return exc.code, loaded
        return exc.code, {"error": raw.decode("utf-8", "replace")}


@pytest.fixture
def server(tmp_path: Path) -> Any:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    api = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(tmp_path, open_browser=False, lesson_delivery_api=api)
    base = url.rsplit("/", 1)[0]

    def request(
        method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        return _request(base, method, path, body)

    request.api = api  # type: ignore[attr-defined]
    try:
        yield request
    finally:
        httpd.shutdown()
        httpd.server_close()


def preview_query(delivery_id: str) -> str:
    return f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id={quote(delivery_id, safe='')}"


def test_post_list_preview_and_get_share_one_inbox(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    status, created = server("POST", LESSON_DELIVERY_API_PREFIX, sent)
    assert status == 201
    assert created == sent

    status, listed = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert status == 200
    assert [item["delivery_id"] for item in listed["deliveries"]] == ["delivery-001"]

    status, preview = server("GET", preview_query("delivery-001"))
    assert status == 200
    assert preview["preview_status"] == "READY"
    assert preview["delivery_id"] == "delivery-001"
    assert preview["title"] == "Blues Turnaround"
    assert preview["canonical_event_ids"] == ["ev-1", "ev-2", "ev-3"]
    assert preview["assignment_artifact_digest"] == sent["assignment_artifact_digest"]
    assert preview["assignment_behavior_digest"] == sent["assignment_behavior_digest"]
    assert "assignment" not in preview
    assert "recipient_ref" not in preview

    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert status == 200
    assert fetched == sent


def test_a_second_query_parameter_does_not_filter_or_authorize(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment))
    status, preview = server(
        "GET",
        preview_query("delivery-001") + "&recipient_ref=someone-else",
    )
    assert status == 200
    assert preview["delivery_id"] == "delivery-001"


@pytest.mark.parametrize(
    "delivery_id",
    [
        "delivery/001",
        "delivery 001",
        "delivery#001",
        "delivery?001",
        "delivery&001",
        "deliver%y",
        "box/preview",
        "a%2Fpreview",
    ],
)
def test_opaque_ids_round_trip_once_including_a_preview_suffix(
    server: Any, assignment: LessonAssignmentV1, delivery_id: str
) -> None:
    sent = payload_for(assignment, delivery_id)
    assert server("POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201

    status, preview = server("GET", preview_query(delivery_id))
    assert status == 200
    assert preview["delivery_id"] == delivery_id
    assert preview["preview_status"] == "READY"

    status, fetched = server(
        "GET", f"{LESSON_DELIVERY_API_PREFIX}/{quote(delivery_id, safe='')}"
    )
    assert status == 200
    assert fetched["delivery_id"] == delivery_id
    assert fetched["assignment"] == sent["assignment"]
    assert "preview_status" not in fetched


def test_the_preview_route_does_not_capture_its_neighbors(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, "box/preview"))

    status, body = server("GET", f"{LESSON_DELIVERY_PREVIEW_PATH}/extra")
    assert status == 404
    assert "preview_status" not in body

    status, body = server("GET", f"{LESSON_DELIVERY_API_PREFIX}?delivery_id=box/preview")
    assert status == 200
    assert "deliveries" in body
    assert "preview_status" not in body

    status, body = server(
        "GET", f"{LESSON_DELIVERY_API_PREFIX}/{quote('box/preview', safe='')}"
    )
    assert status == 200
    assert body["delivery_id"] == "box/preview"
    assert "assignment" in body


@pytest.mark.parametrize(
    "query",
    ["", "?delivery_id=", "?delivery_id=%20%20", "?delivery_id=a&delivery_id=b", "?delivery_id"],
)
def test_missing_blank_or_repeated_identity_is_400(server: Any, query: str) -> None:
    status, body = server("GET", LESSON_DELIVERY_PREVIEW_PATH + query)
    assert status == 400
    assert "error" in body
    assert "preview_status" not in body
    assert "canonical_event_ids" not in body


def test_padding_is_not_stripped_into_another_delivery(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment, "delivery-001"))
    status, body = server("GET", f"{LESSON_DELIVERY_PREVIEW_PATH}?delivery_id=%20delivery-001")
    assert status == 404
    assert body["error"] == "unknown delivery_id ' delivery-001'"
    assert "preview_status" not in body


def test_an_unknown_delivery_is_404(server: Any) -> None:
    status, body = server("GET", preview_query("delivery-404"))
    assert status == 404
    assert body["error"] == "unknown delivery_id 'delivery-404'"


@pytest.mark.parametrize("field_name", ["assignment_artifact_digest", "assignment_behavior_digest"])
def test_a_stored_digest_mismatch_is_409_without_a_preview(
    server: Any, assignment: LessonAssignmentV1, field_name: str
) -> None:
    envelope = envelope_for(
        assignment,
        delivery_id=f"bad-{field_name}",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    corrupt = replace(envelope, **{field_name: "sha256:" + "ab" * 32})
    assert server.api.service.repository.put_if_absent(corrupt)
    status, body = server("GET", preview_query(corrupt.delivery_id))
    assert status == 409
    assert body == {"error": "integrity_mismatch"}


def test_an_unresolvable_assignment_is_422_and_stays_in_the_inbox(
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

    status, body = server("GET", preview_query("delivery-broken"))
    assert status == 422
    assert body == {"error": "unresolvable_assignment"}

    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-broken")
    assert status == 200
    assert fetched == sent
    _status, listed = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert [item["delivery_id"] for item in listed["deliveries"]] == ["delivery-broken"]


def test_post_and_put_on_the_preview_route_are_405_and_do_not_receive(
    server: Any, assignment: LessonAssignmentV1
) -> None:
    sent = payload_for(assignment)
    status, body = server("POST", preview_query("delivery-001"), sent)
    assert status == 405
    assert body == {"error": "method not allowed"}
    status, body = server("PUT", preview_query("delivery-001"), sent)
    assert status == 405
    assert body == {"error": "method not allowed"}
    status, body = server("DELETE", LESSON_DELIVERY_PREVIEW_PATH)
    assert status == 405
    assert body == {"error": "method not allowed"}

    status, listed = server("GET", LESSON_DELIVERY_API_PREFIX)
    assert status == 200
    assert listed["count"] == 0


def test_put_elsewhere_stays_unsupported(server: Any) -> None:
    status, _body = server("PUT", "/index.html")
    assert status == 501


def test_an_unexpected_failure_is_a_sanitized_500(
    server: Any, assignment: LessonAssignmentV1, monkeypatch: pytest.MonkeyPatch
) -> None:
    server("POST", LESSON_DELIVERY_API_PREFIX, payload_for(assignment))

    def boom(_self: LessonDeliveryPreviewService, _delivery_id: str) -> None:
        raise RuntimeError("secret boom")

    monkeypatch.setattr(LessonDeliveryPreviewService, "preview", boom)
    status, body = server("GET", preview_query("delivery-001"))
    assert status == 500
    assert body == {"error": "internal server error"}
    status, fetched = server("GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
    assert status == 200
    assert fetched["delivery_id"] == "delivery-001"


def test_repeated_and_concurrent_previews_do_not_change_stage_1_bytes(
    tmp_path: Path, assignment: LessonAssignmentV1
) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    api = LocalLessonDeliveryApi()
    httpd, _thread, url = serve_mvp_directory(tmp_path, open_browser=False, lesson_delivery_api=api)
    base = url.rsplit("/", 1)[0]
    sent = payload_for(assignment)
    assert _request(base, "POST", LESSON_DELIVERY_API_PREFIX, sent)[0] == 201
    path = preview_query("delivery-001")
    first = _request(base, "GET", path)
    assert first[0] == 200

    start = threading.Barrier(8)
    results: list[tuple[int, dict[str, Any]]] = []
    lock = threading.Lock()

    def fetch() -> None:
        start.wait()
        outcome = _request(base, "GET", path)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=fetch) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        assert len(results) == 8
        assert all(item == first for item in results)
        status, fetched = _request(base, "GET", f"{LESSON_DELIVERY_API_PREFIX}/delivery-001")
        assert status == 200
        assert fetched == sent
        _status, listed = _request(base, "GET", LESSON_DELIVERY_API_PREFIX)
        assert [item["delivery_id"] for item in listed["deliveries"]] == ["delivery-001"]
        assert api.service.get("delivery-001").assignment == assignment
    finally:
        httpd.shutdown()
        httpd.server_close()
