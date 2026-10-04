"""Concurrent appends and terminal operations on isolated attempts."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.evaluation import evaluate_practice_attempt
from master_all_strings.education.local_practice_choice import LocalPracticeChoiceService
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.received_lesson_attempt import (
    AttemptConflictError,
    ReceivedLessonAttemptService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UTC = "2026-10-02T19:42:00Z"


def _service() -> tuple[ReceivedLessonAttemptService, dict[str, Any]]:
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
        deliveries, choices, ids=mint, now_utc=lambda: UTC
    )
    begun = service.begin(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
        "keyboard-a",
        1_000,
    )
    return service, begun


def test_an_accepted_message_is_still_in_the_closed_capture() -> None:
    service, begun = _service()
    started = threading.Event()
    release = threading.Event()

    def hold() -> None:
        started.set()
        assert release.wait(2)

    service.before_commit = hold
    errors: list[BaseException] = []
    accepted: list[dict[str, Any]] = []

    def append() -> None:
        try:
            accepted.append(
                service.append_message(begun["attempt_id"], 0, 2_000, 0.0, [0x90, 64, 90])
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def finish() -> None:
        try:
            accepted.append(service.finish(begun["attempt_id"], 3_000))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    first = threading.Thread(target=append)
    first.start()
    assert started.wait(2)
    second = threading.Thread(target=finish)
    second.start()
    release.set()
    first.join(2)
    second.join(2)
    assert errors == []
    finished = next(item for item in accepted if item.get("attempt_status") == "EVALUATED")
    assert len(finished["raw_capture"]["events"]) == 1


def test_concurrent_finishes_evaluate_once() -> None:
    service, begun = _service()
    entered = threading.Event()
    gate = threading.Event()
    calls = {"n": 0}

    def slow(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        entered.set()
        assert gate.wait(2)
        return evaluate_practice_attempt(*args, **kwargs)

    service._evaluate = slow  # noqa: SLF001
    results: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def finish() -> None:
        try:
            results.append(service.finish(begun["attempt_id"], 2_000))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=finish) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert entered.wait(2)
    gate.set()
    for thread in threads:
        thread.join(2)
    assert errors == []
    assert calls["n"] == 1
    assert results[0] == results[1]
    assert results[0]["attempt_status"] == "EVALUATED"


def test_concurrent_finish_and_cancel_have_one_winner() -> None:
    service, begun = _service()
    outcomes: list[Any] = []
    lock = threading.Lock()

    def run(action: str) -> None:
        try:
            if action == "finish":
                value: Any = service.finish(begun["attempt_id"], 2_000)
            else:
                value = service.cancel(begun["attempt_id"], 2_000)
        except AttemptConflictError as exc:
            value = exc
        with lock:
            outcomes.append(value)

    threads = [
        threading.Thread(target=run, args=("finish",)),
        threading.Thread(target=run, args=("cancel",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    successes = [item for item in outcomes if isinstance(item, dict)]
    conflicts = [item for item in outcomes if isinstance(item, AttemptConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert successes[0]["attempt_status"] in {"EVALUATED", "INTERRUPTED"}
    record = service.repository.get(begun["attempt_id"])
    assert record is not None
    if successes[0]["attempt_status"] == "INTERRUPTED":
        assert record.history.attempts == []
    else:
        assert len(record.history.attempts) == 1
