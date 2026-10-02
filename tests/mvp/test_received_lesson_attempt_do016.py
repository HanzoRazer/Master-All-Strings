"""Isolated attempts against a prepared received lesson.

Begin freezes a snapshot. Finish evaluates that snapshot through the existing
authorities. A later change to the inbox does not replace the snapshot, and
one attempt cannot see another attempt's notes.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.evaluation import evaluate_practice_attempt
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.local_practice_choice import LocalPracticeChoiceService
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.education.serialization import to_dict as education_to_dict
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import (
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)
from master_all_strings.mvp.received_lesson_attempt import (
    ATTEMPT_STATUS_CAPTURING,
    ATTEMPT_STATUS_EVALUATED,
    ATTEMPT_STATUS_INTERRUPTED,
    CAPTURE_CLOCK,
    RECEIVED_LESSON_ATTEMPT_SCHEMA_ID,
    AttemptClosedError,
    AttemptConflictError,
    AttemptEvaluationError,
    AttemptRequestError,
    AttemptSnapshotError,
    ReceivedLessonAttemptService,
    SequenceConflictError,
    UnknownAttemptError,
)
from master_all_strings.performance.alignment import align_performance
from master_all_strings.performance.contracts.alignment import (
    PerformanceAlignmentPolicyV1,
)
from master_all_strings.performance.contracts.capture import CaptureCompletionState
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
)
from master_all_strings.performance.export import to_dict as performance_to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
UTC = "2026-10-02T19:42:00Z"


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


def _ids() -> Any:
    count = {"n": 0}
    lock = threading.Lock()

    def mint() -> str:
        with lock:
            count["n"] += 1
            return f"id-{count['n']}"

    return mint


def _open(
    assignment: LessonAssignmentV1,
    delivery_id: str = "delivery-001",
    *,
    evaluate: Any = evaluate_practice_attempt,
    encode_performance: Any = performance_to_dict,
) -> tuple[ReceivedLessonAttemptService, dict[str, Any], Any]:
    deliveries = LessonDeliveryService()
    choices = InMemoryLocalPracticeChoiceRepository()
    envelope = envelope_for(
        assignment,
        delivery_id=delivery_id,
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.receive(envelope)
    LocalPracticeChoiceService(LessonDeliveryPreviewService(deliveries), choices).choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    service = ReceivedLessonAttemptService(
        deliveries,
        choices,
        ids=_ids(),
        now_utc=lambda: UTC,
        evaluate=evaluate,
        encode_performance=encode_performance,
    )
    begun = service.begin(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
        "keyboard-a",
        1_000,
    )
    return service, begun, deliveries


def _events(begun: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["event_id"]: row for row in begun["preparation"]["playback"]["events"]}


def _play(
    service: ReceivedLessonAttemptService,
    attempt_id: str,
    midi_note: int,
    position: float,
    *,
    sequence: int,
    clock: int,
    velocity: int = 90,
    note_off: list[int] | None = None,
) -> int:
    service.append_message(
        attempt_id, sequence, clock, position, [0x90, midi_note, velocity]
    )
    off = note_off if note_off is not None else [0x80, midi_note, 0]
    service.append_message(attempt_id, sequence + 1, clock + 1, position, off)
    return sequence + 2


def _retimed(assignment: LessonAssignmentV1, tempos: list[dict[str, Any]]) -> LessonAssignmentV1:
    payload = json.loads(serialize_lesson_assignment(assignment))
    payload["musical_content"]["tempo_changes"] = tempos
    return deserialize_lesson_assignment(json.dumps(payload))


def _with_event(assignment: LessonAssignmentV1, event: dict[str, Any]) -> LessonAssignmentV1:
    payload = json.loads(serialize_lesson_assignment(assignment))
    payload["musical_content"]["events"].append(event)
    return deserialize_lesson_assignment(json.dumps(payload))


def test_begin_freezes_a_capturing_snapshot(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    assert begun["schema_id"] == RECEIVED_LESSON_ATTEMPT_SCHEMA_ID
    assert begun["attempt_status"] == ATTEMPT_STATUS_CAPTURING
    assert begun["capture_clock"] == CAPTURE_CLOCK
    assert begun["attempt_policy"] == {
        "schema_version": "1.0.0",
        "pass_count": 1,
        "playback_rate": 1,
        "looping_allowed": False,
        "seeking_allowed": False,
        "lesson_switching_allowed": False,
        "reference_sound": "independent_of_capture",
    }
    assert begun["preparation"]["preparation_status"] == "PREPARED"
    assert begun["delivery_id"] == "delivery-001"
    again = service.begin(
        begun["delivery_id"],
        begun["assignment_artifact_digest"],
        begun["assignment_behavior_digest"],
        "keyboard-a",
        1_000,
    )
    assert again["attempt_id"] != begun["attempt_id"]
    assert again["capture_id"] != begun["capture_id"]
    assert again["performance_session_id"] != begun["performance_session_id"]


def test_finish_matches_a_direct_evaluation(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    attempt_id = begun["attempt_id"]
    sequence = 0
    clock = 2_000
    for event in begun["preparation"]["playback"]["events"]:
        sequence = _play(
            service,
            attempt_id,
            event["midi_note"],
            event["onset_seconds"],
            sequence=sequence,
            clock=clock,
        )
        clock += 10
    finished = service.finish(attempt_id, clock)
    assert finished["attempt_status"] == ATTEMPT_STATUS_EVALUATED
    assert finished["hardware_status"] == {
        "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
        "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
    }
    assert finished["guidance"]["canonical_revision_id"] == (
        begun["preparation"]["score"]["canonical_revision"]["revision_id"]
    )
    assert "evaluation" in finished and "messages" in finished
    assert finished["raw_capture"]["completion_state"] == "complete"
    assert finished["raw_capture"]["started_at"] == UTC
    assert finished["raw_capture"]["ended_at"] == UTC
    assert finished["raw_capture"]["provenance"]["clock_domain"] == CAPTURE_CLOCK
    assert finished["raw_capture"]["tempo_context"] != 120

    revision = begun["preparation"]["score"]["canonical_revision"]
    expected = tuple(
        MusicalEvent(
            event_id=row["event_id"],
            midi_note=row["midi_note"],
            start_tick=row["start_tick"],
            duration_ticks=row["duration_ticks"],
            velocity=row["velocity"],
            cents_offset=row["cents_offset"],
            voice_id=row["voice_id"],
        )
        for row in revision["events"]
    )
    tempo = tuple(
        TempoChangeV1("1.0.0", row["tick"], row["microseconds_per_quarter"])
        for row in begun["preparation"]["playback"]["timeline"]["tempo_changes"]
    )
    observed = tuple(
        ObservedMidiNoteV1(
            schema_version=row["schema_version"],
            observed_event_id=row["observed_event_id"],
            capture_id=row["capture_id"],
            note_on_event_id=row["note_on_event_id"],
            note_off_event_id=row["note_off_event_id"],
            midi_note=row["midi_note"],
            velocity=row["velocity"],
            channel=row["channel"],
            source_device=row["source_device"],
            note_on_time_ns=row["note_on_time_ns"],
            note_off_time_ns=row["note_off_time_ns"],
            duration_ns=row["duration_ns"],
            source_string=row["source_string"],
            status=ObservedMidiNoteStatus(row["status"]),
            repetition_index=row["repetition_index"],
            practice_onset_seconds=row["practice_onset_seconds"],
            estimated_start_tick=row["estimated_start_tick"],
        )
        for row in finished["observed_events"]
    )
    alignment = align_performance(
        assignment_id=begun["assignment_id"],
        content_id=begun["content_id"],
        performance_session_id=begun["performance_session_id"],
        expected=expected,
        observed=observed,
        policy=PerformanceAlignmentPolicyV1(),
        ticks_per_quarter=begun["preparation"]["playback"]["timeline"]["ticks_per_quarter"],
        tempo_changes=tempo,
        repetition_count=1,
    )
    direct = evaluate_practice_attempt(alignment, current_rate=1.0)
    assert education_to_dict(direct)["evaluation_digest"] == (
        finished["evaluation"]["evaluation_digest"]
    )
    guidance = build_teaching_guidance_projection(
        direct, canonical_revision_id=revision["revision_id"]
    )
    assert education_to_dict(guidance)["guidance_digest"] == finished["guidance"]["guidance_digest"]
    repeated = service.finish(attempt_id, clock)
    assert repeated == finished
    assert len(service.repository.get(attempt_id).history.attempts) == 1  # type: ignore[union-attr]


def test_wrong_missing_and_extra_notes_stay_evidence(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    rows = begun["preparation"]["playback"]["events"]
    attempt_id = begun["attempt_id"]
    _play(
        service,
        attempt_id,
        rows[0]["midi_note"] + 2,
        rows[0]["onset_seconds"],
        sequence=0,
        clock=2_000,
    )
    _play(
        service,
        attempt_id,
        40,
        begun["preparation"]["playback"]["total_seconds"],
        sequence=2,
        clock=3_000,
    )
    finished = service.finish(attempt_id, 4_000)
    kinds = {row["finding_type"] for row in finished["evaluation"]["findings"]}
    assert "pitch_difference" in kinds
    assert "expected_note_missing" in kinds
    assert "unexpected_note" in kinds


def test_velocity_zero_note_on_pairs_as_note_off(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    event = begun["preparation"]["playback"]["events"][0]
    attempt_id = begun["attempt_id"]
    service.append_message(
        attempt_id, 0, 2_000, event["onset_seconds"], [0x90, event["midi_note"], 90]
    )
    service.append_message(
        attempt_id, 1, 2_100, event["onset_seconds"], [0x90, event["midi_note"], 0]
    )
    finished = service.finish(attempt_id, 2_200)
    note = finished["observed_events"][0]
    assert note["status"] == "complete"
    assert note["velocity"] == 90
    assert finished["unmatched_note_offs"] == []


def test_unmatched_and_missing_note_off_evidence_survives(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    event = begun["preparation"]["playback"]["events"][0]
    attempt_id = begun["attempt_id"]
    service.append_message(attempt_id, 0, 2_000, event["onset_seconds"], [0x80, 40, 0])
    service.append_message(
        attempt_id, 1, 2_100, event["onset_seconds"], [0x90, event["midi_note"], 70]
    )
    finished = service.finish(attempt_id, 2_200)
    assert finished["unmatched_note_offs"][0]["midi_note"] == 40
    assert finished["observed_events"][0]["status"] == "unmatched_note_on"
    assert finished["observed_events"][0]["note_off_event_id"] is None


def test_an_empty_finish_is_an_evaluation_without_invented_notes(
    assignment: LessonAssignmentV1,
) -> None:
    service, begun, _deliveries = _open(assignment)
    finished = service.finish(begun["attempt_id"], 2_000)
    assert finished["attempt_status"] == ATTEMPT_STATUS_EVALUATED
    assert finished["observed_events"] == []
    assert finished["evaluation"]["summary"]["missing_count"] == len(
        begun["preparation"]["playback"]["events"]
    )


def test_tempo_change_uses_the_snapshot_timeline(assignment: LessonAssignmentV1) -> None:
    retimed = _retimed(
        assignment,
        [
            {"tick": 0, "tempo_bpm": 60.0},
            {"tick": 480, "tempo_bpm": 180.0},
        ],
    )
    service, begun, _deliveries = _open(retimed)
    third = _events(begun)["ev-3"]
    flat_120 = ticks_to_seconds(
        960,
        ticks_per_quarter=480,
        tempo_changes=(TempoChangeV1("1.0.0", 0, 500_000),),
    )
    assert abs(third["onset_seconds"] - flat_120) > 0.25
    service.append_message(
        begun["attempt_id"], 0, 2_000, third["onset_seconds"], [0x90, third["midi_note"], 80]
    )
    service.append_message(
        begun["attempt_id"], 1, 2_100, third["onset_seconds"], [0x80, third["midi_note"], 0]
    )
    finished = service.finish(begun["attempt_id"], 2_200)
    missing = [
        row
        for row in finished["evaluation"]["findings"]
        if row["finding_type"] == "expected_note_missing" and "ev-3" in row["expected_event_refs"]
    ]
    assert missing == []
    assert finished["raw_capture"]["tempo_context"] == 60


def test_simultaneous_notes_remain_distinct_events(assignment: LessonAssignmentV1) -> None:
    polyphonic = _with_event(
        assignment,
        {
            "event_id": "ev-sim",
            "midi_note": 60,
            "start_tick": 0,
            "duration_ticks": 480,
            "velocity": 80,
            "cents_offset": 0.0,
            "voice_id": None,
        },
    )
    service, begun, _deliveries = _open(polyphonic)
    rows = _events(begun)
    attempt_id = begun["attempt_id"]
    _play(
        service,
        attempt_id,
        rows["ev-1"]["midi_note"],
        rows["ev-1"]["onset_seconds"],
        sequence=0,
        clock=2_000,
    )
    _play(
        service,
        attempt_id,
        rows["ev-sim"]["midi_note"],
        rows["ev-sim"]["onset_seconds"],
        sequence=2,
        clock=2_100,
    )
    finished = service.finish(attempt_id, 3_000)
    observed_notes = {row["midi_note"] for row in finished["observed_events"]}
    assert rows["ev-1"]["midi_note"] in observed_notes
    assert rows["ev-sim"]["midi_note"] in observed_notes
    assert len(finished["observed_events"]) == 2


def test_two_attempts_do_not_exchange_events(assignment: LessonAssignmentV1) -> None:
    service, first, deliveries = _open(assignment)
    other = envelope_for(
        assignment,
        delivery_id="delivery-002",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.receive(other)
    LocalPracticeChoiceService(
        LessonDeliveryPreviewService(deliveries), service._choices
    ).choose(
        other.delivery_id,
        other.assignment_artifact_digest,
        other.assignment_behavior_digest,
    )
    second = service.begin(
        other.delivery_id,
        other.assignment_artifact_digest,
        other.assignment_behavior_digest,
        "keyboard-b",
        5_000,
    )
    event = _events(first)["ev-1"]
    service.append_message(
        first["attempt_id"], 0, 2_000, event["onset_seconds"], [0x90, event["midi_note"], 90]
    )
    done = service.finish(second["attempt_id"], 6_000)
    assert done["observed_events"] == []
    assert done["delivery_id"] == "delivery-002"
    assert done["attempt_id"] != first["attempt_id"]
    kept = service.finish(first["attempt_id"], 3_000)
    assert len(kept["raw_capture"]["events"]) == 1
    assert kept["delivery_id"] == "delivery-001"


def test_inbox_changes_after_begin_do_not_replace_the_snapshot(
    assignment: LessonAssignmentV1,
) -> None:
    service, begun, deliveries = _open(assignment)
    original = begun["preparation"]["score"]["canonical_revision"]["revision_id"]
    deliveries.repository._deliveries.pop("delivery-001")  # noqa: SLF001
    finished = service.finish(begun["attempt_id"], 2_000)
    assert finished["assignment_artifact_digest"] == begun["assignment_artifact_digest"]
    assert finished["guidance"]["canonical_revision_id"] == original


def test_a_changed_delivery_pin_does_not_rewrite_the_attempt(
    assignment: LessonAssignmentV1,
) -> None:
    service, begun, deliveries = _open(assignment)
    stored = deliveries.get("delivery-001")
    deliveries.repository._deliveries["delivery-001"] = replace(  # noqa: SLF001
        stored, assignment_artifact_digest="sha256:" + "ab" * 32
    )
    finished = service.finish(begun["attempt_id"], 2_000)
    assert finished["assignment_artifact_digest"] == begun["assignment_artifact_digest"]


def test_cancel_keeps_evidence_and_skips_evaluation(assignment: LessonAssignmentV1) -> None:
    calls = {"n": 0}

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return evaluate_practice_attempt(*args, **kwargs)

    service, begun, _deliveries = _open(assignment, evaluate=counting)
    event = _events(begun)["ev-1"]
    service.append_message(
        begun["attempt_id"], 0, 2_000, event["onset_seconds"], [0x90, event["midi_note"], 80]
    )
    cancelled = service.cancel(begun["attempt_id"], 2_100)
    assert cancelled["attempt_status"] == ATTEMPT_STATUS_INTERRUPTED
    assert "evaluation" not in cancelled
    assert "guidance" not in cancelled
    assert cancelled["raw_capture"]["completion_state"] == "interrupted"
    assert len(cancelled["observed_events"]) == 1
    assert calls["n"] == 0
    assert service.cancel(begun["attempt_id"], 2_100) == cancelled
    with pytest.raises(AttemptConflictError):
        service.finish(begun["attempt_id"], 2_100)
    with pytest.raises(AttemptClosedError):
        service.append_message(
            begun["attempt_id"], 1, 2_200, event["onset_seconds"], [0x80, event["midi_note"], 0]
        )
    record = service.repository.get(begun["attempt_id"])
    assert record is not None
    assert len(record.capture.events) == 1


def test_messages_after_finish_do_not_change_the_capture(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    finished = service.finish(begun["attempt_id"], 2_000)
    with pytest.raises(AttemptClosedError):
        service.append_message(begun["attempt_id"], 0, 3_000, 0.0, [0x90, 60, 90])
    with pytest.raises(AttemptConflictError):
        service.cancel(begun["attempt_id"], 3_000)
    assert service.finish(begun["attempt_id"], 2_000) == finished


def test_a_rejected_message_does_not_consume_its_sequence(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)
    attempt_id = begun["attempt_id"]
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 0, 2_000, 0.0, [0x90, 60])
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, True, 2_000, 0.0, [0x90, 60, 90])  # type: ignore[arg-type]
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 0, 2_000, float("nan"), [0x90, 60, 90])
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 0, 2_000, float("inf"), [0x90, 60, 90])
    accepted = service.append_message(attempt_id, 0, 2_000, 0.0, [0x90, 60, 90])
    assert accepted["accepted_event_count"] == 1
    with pytest.raises(SequenceConflictError):
        service.append_message(attempt_id, 0, 2_100, 0.0, [0x80, 60, 0])
    with pytest.raises(SequenceConflictError):
        service.append_message(attempt_id, 2, 2_100, 0.0, [0x80, 60, 0])
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 1, 1_000, 0.0, [0x80, 60, 0])
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 1, 2_100, -0.1, [0x80, 60, 0])
    outside = begun["preparation"]["playback"]["total_seconds"] + 0.01
    with pytest.raises(AttemptRequestError):
        service.append_message(attempt_id, 1, 2_100, outside, [0x80, 60, 0])
    service.append_message(attempt_id, 1, 2_100, 0.0, [0x80, 60, 0])
    record = service.repository.get(attempt_id)
    assert record is not None
    assert record.next_sequence == 2
    assert record.capture.completion_state is CaptureCompletionState.IN_PROGRESS


def test_unknown_attempt_and_malformed_scalars_fail(assignment: LessonAssignmentV1) -> None:
    service, _begun, _deliveries = _open(assignment)
    with pytest.raises(UnknownAttemptError):
        service.finish("missing-attempt", 1)
    with pytest.raises(AttemptRequestError):
        service.begin("delivery-001", "sha256:" + "ab" * 32, "sha256:" + "cd" * 32, "  ", 1)
    with pytest.raises(AttemptRequestError):
        service.append_message("attempt", -1, 1, 0.0, [0x90, 60, 90])
    with pytest.raises(AttemptRequestError):
        service.append_message("attempt", 0, 1, 0.0, [0xB0, 7, 100])
    with pytest.raises(AttemptRequestError):
        service.append_message("attempt", 0, 1, 0.0, [0x90, 200, 90])


def test_evaluation_failure_retains_the_closed_capture(assignment: LessonAssignmentV1) -> None:
    calls = {"n": 0}

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        calls["n"] += 1
        raise RuntimeError("evaluator exploded")

    service, begun, _deliveries = _open(assignment, evaluate=explode)
    with pytest.raises(AttemptEvaluationError):
        service.finish(begun["attempt_id"], 2_000)
    record = service.repository.get(begun["attempt_id"])
    assert record is not None
    assert record.capture.is_closed
    assert record.phase == "FAILED"
    assert record.history.attempts == []
    with pytest.raises(AttemptEvaluationError):
        service.finish(begun["attempt_id"], 2_000)
    assert calls["n"] == 1
    assert record.capture.is_closed


def test_serialization_failure_does_not_evaluate_twice(assignment: LessonAssignmentV1) -> None:
    calls = {"n": 0}

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return evaluate_practice_attempt(*args, **kwargs)

    def bad_encode(_record: Any) -> dict[str, Any]:
        raise RuntimeError("serializer exploded")

    service, begun, _deliveries = _open(
        assignment, evaluate=counting, encode_performance=bad_encode
    )
    with pytest.raises(AttemptEvaluationError):
        service.finish(begun["attempt_id"], 2_000)
    with pytest.raises(AttemptEvaluationError):
        service.finish(begun["attempt_id"], 2_000)
    record = service.repository.get(begun["attempt_id"])
    assert record is not None
    assert calls["n"] == 1
    assert len(record.history.attempts) == 1
    assert record.capture.is_closed


def test_a_duplicate_attempt_id_does_not_replace_the_first(assignment: LessonAssignmentV1) -> None:
    service, begun, _deliveries = _open(assignment)

    def stuck() -> str:
        return begun["attempt_id"]

    service._ids = stuck  # noqa: SLF001
    with pytest.raises(AttemptSnapshotError):
        service.begin(
            begun["delivery_id"],
            begun["assignment_artifact_digest"],
            begun["assignment_behavior_digest"],
            "other-device",
            9,
        )
    kept = service.repository.get(begun["attempt_id"])
    assert kept is not None
    assert kept.device_id == "keyboard-a"
