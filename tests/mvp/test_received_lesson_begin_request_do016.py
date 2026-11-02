"""Keyed Begin creates one attempt. Recovery never creates one.

A matching repeat reads the stored result. A different payload conflicts
before that result can change. Recovery before arrival seals a tombstone.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.local_practice_choice import LocalPracticeChoiceService
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.local_practice_preparation import LocalPracticePreparationService
from master_all_strings.mvp.received_lesson_attempt import ReceivedLessonAttemptService
from master_all_strings.mvp.received_lesson_attempt_api import (
    LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
    LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
    LESSON_PRACTICE_ATTEMPT_PATH,
    LESSON_PRACTICE_BEGIN_RECOVERY_PATH,
    LESSON_PRACTICE_BEGIN_REQUEST_PATH,
    LocalReceivedLessonAttemptApi,
)
from master_all_strings.mvp.received_lesson_begin_request import ReceivedLessonBeginGateway
from master_all_strings.mvp.received_lesson_begin_request_repository import BeginPayload

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY = "abcdefab-abcd-4abc-8abc-abcdefabcdef"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _open() -> tuple[ReceivedLessonAttemptService, BeginPayload, Any]:
    assignment = deserialize_lesson_assignment(
        (REPO_ROOT / "resources" / "lesson" / "examples" / "local_midi_basic.json").read_text(
            "utf-8"
        )
    )
    deliveries = LessonDeliveryService()
    choices = InMemoryLocalPracticeChoiceRepository()
    envelope = envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.receive(envelope)
    LocalPracticeChoiceService(LessonDeliveryPreviewService(deliveries), choices).choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    count = {"n": 0}
    lock = threading.Lock()

    def mint() -> str:
        with lock:
            count["n"] += 1
            return f"id-{count['n']}"

    service = ReceivedLessonAttemptService(
        deliveries, choices, ids=mint, now_utc=lambda: "2026-11-01T00:00:00Z"
    )
    payload = BeginPayload(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
        "keyboard-a",
        1_000,
    )
    return service, payload, envelope


def _gateway() -> tuple[ReceivedLessonBeginGateway, BeginPayload]:
    service, payload, _envelope = _open()
    return ReceivedLessonBeginGateway(service), payload


def _changed(payload: BeginPayload, **kwargs: object) -> BeginPayload:
    data = {
        "delivery_id": payload.delivery_id,
        "artifact_digest": payload.artifact_digest,
        "behavior_digest": payload.behavior_digest,
        "device_id": payload.device_id,
        "capture_time_ns": payload.capture_time_ns,
    }
    data.update(kwargs)
    return BeginPayload(**data)  # type: ignore[arg-type]


def test_keyed_begin_creates_one_attempt_and_a_repeat_is_the_same_document() -> None:
    gateway, payload = _gateway()
    status, first = gateway.begin(KEY, payload)
    assert status == 201
    assert first["status"] == "STARTED"
    assert first["attempt"]["attempt_status"] == "CAPTURING"
    again_status, again = gateway.begin(KEY, payload)
    assert again_status == 200
    assert again == first
    assert len(gateway.service.repository._attempts) == 1  # noqa: SLF001


def test_concurrent_identical_keys_allocate_one_attempt() -> None:
    gateway, payload = _gateway()
    started = threading.Event()
    release = threading.Event()
    real = LocalPracticePreparationService.prepare

    def blocked(self: Any, *args: object, **kwargs: object) -> Any:
        started.set()
        assert release.wait(2)
        return real(self, *args, **kwargs)

    LocalPracticePreparationService.prepare = blocked  # type: ignore[method-assign]
    results: list[tuple[int, dict[str, Any]]] = []

    def call() -> None:
        results.append(gateway.begin(KEY, payload))

    try:
        first = threading.Thread(target=call)
        first.start()
        assert started.wait(2)
        second = gateway.begin(KEY, payload)
        release.set()
        first.join(2)
    finally:
        LocalPracticePreparationService.prepare = real  # type: ignore[method-assign]
    assert second[0] == 202
    assert second[1]["status"] == "PENDING"
    assert second[1]["attempt"] is None
    assert second[1]["begin_request_id"] == KEY
    assert len(results) == 1
    assert results[0][0] == 201
    follow = gateway.begin(KEY, payload)
    assert follow[0] == 200
    assert follow[1]["attempt"]["attempt_id"] == results[0][1]["attempt"]["attempt_id"]
    assert len(gateway.service.repository._attempts) == 1  # noqa: SLF001


def test_every_changed_field_conflicts_without_replacing_the_binding() -> None:
    gateway, payload = _gateway()
    status, stored = gateway.begin(KEY, payload)
    assert status == 201
    variants = [
        _changed(payload, delivery_id="delivery-002"),
        _changed(payload, artifact_digest="sha256:" + "ab" * 32),
        _changed(payload, behavior_digest="sha256:" + "cd" * 32),
        _changed(payload, device_id="keyboard-b"),
        _changed(payload, capture_time_ns=2_000),
    ]
    for variant in variants:
        code, body = gateway.begin(KEY, variant)
        assert code == 409
        assert body == {"error": "begin_request_conflict"}
        code, body = gateway.recover(KEY, variant)
        assert code == 409
        assert body == {"error": "begin_request_conflict"}
    kept = gateway.begin(KEY, payload)
    assert kept[1] == stored


def test_recovery_before_begin_seals_a_tombstone() -> None:
    gateway, payload = _gateway()
    status, body = gateway.recover(KEY, payload)
    assert status == 200
    assert body["status"] == "NO_ATTEMPT"
    assert body["attempt"] is None
    refused, error = gateway.begin(KEY, payload)
    assert refused == 409
    assert error == {"error": "begin_request_closed"}
    assert gateway.service.repository._attempts == {}  # noqa: SLF001
    repeated = gateway.recover(KEY, payload)
    assert repeated == (status, body)


def test_recovery_during_preparation_cancels_and_does_not_publish_started() -> None:
    gateway, payload = _gateway()
    started = threading.Event()
    release = threading.Event()
    real = LocalPracticePreparationService.prepare

    def blocked(self: Any, *args: object, **kwargs: object) -> Any:
        started.set()
        assert release.wait(2)
        return real(self, *args, **kwargs)

    LocalPracticePreparationService.prepare = blocked  # type: ignore[method-assign]
    begun: list[tuple[int, dict[str, Any]]] = []

    def call() -> None:
        begun.append(gateway.begin(KEY, payload))

    try:
        worker = threading.Thread(target=call)
        worker.start()
        assert started.wait(2)
        pending = gateway.recover(KEY, payload)
        assert pending[0] == 202
        assert pending[1]["status"] == "PENDING"
        release.set()
        worker.join(2)
    finally:
        LocalPracticePreparationService.prepare = real  # type: ignore[method-assign]
    assert begun[0][0] == 200
    assert begun[0][1]["status"] == "INTERRUPTED"
    assert begun[0][1]["attempt"]["observed_events"] == []
    settled = gateway.recover(KEY, payload)
    assert settled == begun[0]
    assert "evaluation" not in settled[1]["attempt"]


def test_recovery_cancels_the_attempt_whose_begin_response_was_lost() -> None:
    gateway, payload = _gateway()
    status, started = gateway.begin(KEY, payload)
    assert status == 201
    attempt_id = started["attempt"]["attempt_id"]
    recovered, body = gateway.recover(KEY, payload)
    assert recovered == 200
    assert body["status"] == "INTERRUPTED"
    assert body["attempt"]["attempt_id"] == attempt_id
    assert body["attempt"]["observed_events"] == []
    assert gateway.service.repository.get(attempt_id) is not None
    assert gateway.service.repository.get(attempt_id).phase == "INTERRUPTED"  # type: ignore[union-attr]


def test_duplicate_recovery_returns_one_complete_document() -> None:
    gateway, payload = _gateway()
    gateway.begin(KEY, payload)
    started = threading.Event()
    release = threading.Event()
    real = gateway.service.cancel

    def blocked(attempt_id: str, capture_time_ns: int) -> dict[str, Any]:
        started.set()
        assert release.wait(2)
        return real(attempt_id, capture_time_ns)

    gateway.service.cancel = blocked  # type: ignore[method-assign]
    results: list[tuple[int, dict[str, Any]]] = []

    def call() -> None:
        results.append(gateway.recover(KEY, payload))

    try:
        first = threading.Thread(target=call)
        first.start()
        assert started.wait(2)
        pending = gateway.recover(KEY, payload)
        release.set()
        first.join(2)
    finally:
        gateway.service.cancel = real  # type: ignore[method-assign]
    assert pending[0] == 202
    assert results[0][1]["status"] == "INTERRUPTED"
    repeat = gateway.recover(KEY, payload)
    assert repeat == results[0]
    assert repeat[1]["attempt"]["raw_capture"]["events"] == []


def test_a_pre_insert_failure_seals_no_attempt_and_a_post_insert_failure_stays_open() -> None:
    gateway, payload = _gateway()
    missing = _changed(payload, delivery_id="missing-delivery")
    status, body = gateway.begin(KEY, missing)
    assert status == 404
    assert body == {"error": "unknown_practice_choice"}
    assert gateway.service.repository._attempts == {}  # noqa: SLF001
    closed = gateway.begin(KEY, missing)
    assert closed == (409, {"error": "begin_request_closed"})
    recovered = gateway.recover(KEY, missing)
    assert recovered[1]["status"] == "NO_ATTEMPT"

    fresh, fresh_payload = _gateway()
    real = fresh.repository.claim_publication

    def explode(key: str, attempt_id: str, document: dict[str, Any]) -> Any:
        raise RuntimeError(f"after {attempt_id}")

    fresh.repository.claim_publication = explode  # type: ignore[method-assign]
    failed, error = fresh.begin(OTHER, fresh_payload)
    assert failed == 500
    assert error == {"error": "internal server error"}
    assert len(fresh.service.repository._attempts) == 1  # noqa: SLF001
    fresh.repository.claim_publication = real  # type: ignore[method-assign]
    saved = fresh.recover(OTHER, fresh_payload)
    assert saved[0] == 200
    assert saved[1]["status"] == "INTERRUPTED"


def test_a_failed_cancel_can_be_completed_by_a_later_recovery() -> None:
    gateway, payload = _gateway()
    gateway.begin(KEY, payload)
    calls = {"n": 0}
    real = gateway.service.cancel

    def flaky(attempt_id: str, capture_time_ns: int) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("cancel failed")
        return real(attempt_id, capture_time_ns)

    gateway.service.cancel = flaky  # type: ignore[method-assign]
    failed = gateway.recover(KEY, payload)
    assert failed == (500, {"error": "internal server error"})
    assert gateway.repository.phase(KEY) == "unresolved"
    saved = gateway.recover(KEY, payload)
    assert saved[0] == 200
    assert saved[1]["status"] == "INTERRUPTED"
    assert calls["n"] == 2


def test_an_unrelated_key_proceeds_while_another_is_blocked() -> None:
    gateway, payload = _gateway()
    started = threading.Event()
    release = threading.Event()
    real = LocalPracticePreparationService.prepare

    def blocked(self: Any, *args: object, **kwargs: object) -> Any:
        if not started.is_set():
            started.set()
            assert release.wait(2)
        return real(self, *args, **kwargs)

    LocalPracticePreparationService.prepare = blocked  # type: ignore[method-assign]
    held: list[tuple[int, dict[str, Any]]] = []

    def call() -> None:
        held.append(gateway.begin(KEY, payload))

    try:
        worker = threading.Thread(target=call)
        worker.start()
        assert started.wait(2)
        other = gateway.begin(OTHER, payload)
        release.set()
        worker.join(2)
    finally:
        LocalPracticePreparationService.prepare = real  # type: ignore[method-assign]
    assert other[0] == 201
    assert held[0][0] == 201
    assert other[1]["attempt"]["attempt_id"] != held[0][1]["attempt"]["attempt_id"]


def test_a_nonempty_attempt_is_not_advertised_as_recovered() -> None:
    gateway, payload = _gateway()
    _status, started = gateway.begin(KEY, payload)
    attempt_id = started["attempt"]["attempt_id"]
    gateway.service.append_message(attempt_id, 0, 1_100, 0.0, [0x90, 64, 80])
    status, body = gateway.recover(KEY, payload)
    assert status == 409
    assert body == {"error": "attempt_conflict"}
    stored = gateway.service.repository.get(attempt_id)
    assert stored is not None
    assert stored.phase == "CAPTURING"
    assert stored.next_sequence == 1


def test_callers_cannot_mutate_the_stored_result() -> None:
    gateway, payload = _gateway()
    _status, started = gateway.begin(KEY, payload)
    started["attempt"]["attempt_id"] = "mutated"
    started["status"] = "NO_ATTEMPT"
    again = gateway.begin(KEY, payload)
    assert again[1]["status"] == "STARTED"
    assert again[1]["attempt"]["attempt_id"] != "mutated"
    recovered, document = gateway.recover(KEY, payload)
    assert recovered == 200
    document["attempt"]["attempt_id"] = "changed"
    repeat = gateway.recover(KEY, payload)
    assert repeat[1]["attempt"]["attempt_id"] != "changed"


def test_http_rejects_malformed_keys_and_keeps_the_four_routes() -> None:
    service, payload, _envelope = _open()
    api = LocalReceivedLessonAttemptApi(service._deliveries, service._choices, service=service)  # noqa: SLF001
    body = {
        "begin_request_id": KEY,
        "begin": {
            "delivery_id": payload.delivery_id,
            "expected_assignment_artifact_digest": payload.artifact_digest,
            "expected_assignment_behavior_digest": payload.behavior_digest,
            "device_id": payload.device_id,
            "capture_time_ns": payload.capture_time_ns,
        },
    }
    status, document = api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, body)
    assert status == 201
    assert document["status"] == "STARTED"
    legacy, legacy_body = api.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_PATH,
        body["begin"],
    )
    assert legacy == 201
    assert legacy_body["attempt_id"] != document["attempt"]["attempt_id"]
    upper = dict(body)
    upper["begin_request_id"] = "ABCDEFAB-ABCD-4ABC-8ABC-ABCDEFABCDEF"
    assert api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, upper)[0] == 400
    boolean = dict(body)
    boolean["begin_request_id"] = OTHER
    nested = dict(body["begin"])
    nested["capture_time_ns"] = True
    boolean["begin"] = nested
    refused = api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, boolean)
    assert refused[0] == 400
    assert "PREPARED" not in str(refused[1])
    slash = api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH + "/", body)
    assert slash[0] == 404
    queried = api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH + "?x=1", body)
    assert queried == (400, {"error": "query string is not allowed"})
    assert api.handle_http("GET", LESSON_PRACTICE_BEGIN_RECOVERY_PATH, body)[0] == 405
    recovered = api.handle_http("POST", LESSON_PRACTICE_BEGIN_RECOVERY_PATH, body)
    assert recovered[0] == 200
    assert recovered[1]["status"] == "INTERRUPTED"


def test_restart_forgets_the_key_and_refuses_the_delayed_begin() -> None:
    _gateway_begun, payload = _gateway()
    _gateway_begun.begin(KEY, payload)
    restarted, _same = _gateway()
    sealed = restarted.recover(KEY, payload)
    assert sealed[1]["status"] == "NO_ATTEMPT"
    refused = restarted.begin(KEY, payload)
    assert refused == (409, {"error": "begin_request_closed"})
    assert restarted.service.repository._attempts == {}  # noqa: SLF001


def _http_begin(key: str, payload: BeginPayload) -> dict[str, Any]:
    return {
        "begin_request_id": key,
        "begin": {
            "delivery_id": payload.delivery_id,
            "expected_assignment_artifact_digest": payload.artifact_digest,
            "expected_assignment_behavior_digest": payload.behavior_digest,
            "device_id": payload.device_id,
            "capture_time_ns": payload.capture_time_ns,
        },
    }


@pytest.mark.parametrize("original_was_stored", [False, True])
def test_a_begin_delayed_past_recovery_cannot_disturb_the_next_attempt(
    original_was_stored: bool,
) -> None:
    """The server half of the browser race test in received_attempt_controller.test.js.

    The original Begin either never reached the server before recovery, or was
    stored and only its response was lost. Either way the browser recovers, a
    fresh key starts and evaluates, and the original request arriving late is
    refused without creating or touching an attempt.
    """

    service, payload, _envelope = _open()
    api = LocalReceivedLessonAttemptApi(service._deliveries, service._choices, service=service)  # noqa: SLF001
    original = _http_begin(KEY, payload)
    if original_was_stored:
        assert api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, original)[0] == 201
    status, recovered = api.handle_http("POST", LESSON_PRACTICE_BEGIN_RECOVERY_PATH, original)
    assert status == 200
    assert recovered["status"] == ("INTERRUPTED" if original_was_stored else "NO_ATTEMPT")

    status, fresh = api.handle_http(
        "POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, _http_begin(OTHER, payload)
    )
    assert status == 201
    assert fresh["status"] == "STARTED"
    attempt_id = fresh["attempt"]["attempt_id"]
    before = dict(service.repository._attempts)  # noqa: SLF001

    late = api.handle_http("POST", LESSON_PRACTICE_BEGIN_REQUEST_PATH, original)
    assert late == (409, {"error": "begin_request_closed"})
    assert service.repository._attempts == before  # noqa: SLF001

    status, ack = api.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
        {
            "attempt_id": attempt_id,
            "sequence_number": 0,
            "capture_time_ns": 2_000,
            "practice_position_seconds": 0.0,
            "raw_payload": [144, 60, 80],
        },
    )
    assert status == 200
    assert ack["accepted_event_count"] == 1
    status, done = api.handle_http(
        "POST",
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        {"attempt_id": attempt_id, "capture_time_ns": 3_000},
    )
    assert status == 200
    assert done["attempt_status"] == "EVALUATED"
