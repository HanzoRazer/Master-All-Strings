"""Capture and evaluate one attempt against a received-lesson snapshot.

Begin asks the existing preparation service for a fresh bundle and freezes
that bundle on the attempt. Later inbox changes do not replace it. Append,
finish, and cancel then talk only to that attempt.

The musical work is delegated. This module normalizes MIDI through the
Performance capture services, pairs notes through the existing pairing
authority, and evaluates through the public alignment, evaluation, and
guidance entry points. It does not score notes itself, and it does not touch
the process-global capture or evaluation facades.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.evaluation import evaluate_practice_attempt
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.local_practice_choice import LocalPracticeChoiceService
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.education.messages import MESSAGE_CATALOG_V1
from master_all_strings.education.serialization import to_dict as education_to_dict
from master_all_strings.education.session_history import PracticeSessionHistory
from master_all_strings.mvp.local_practice_preparation import (
    LocalPracticePreparationService,
    preparation_to_dict,
    shared_application,
)
from master_all_strings.mvp.received_lesson_attempt_repository import (
    AttemptCollisionError,
    ReceivedLessonAttemptRepository,
    StoredAttempt,
)
from master_all_strings.performance.alignment import align_performance
from master_all_strings.performance.capture_normalization import (
    append_events,
    build_raw_capture,
    close_capture,
    normalize_midi_event,
)
from master_all_strings.performance.contracts.alignment import PerformanceAlignmentPolicyV1
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CaptureSourceV1,
    MidiEventType,
)
from master_all_strings.performance.contracts.live_midi import ObservedMidiNoteV1
from master_all_strings.performance.contracts.runtime import RuntimeIdentityV1, RuntimeKind
from master_all_strings.performance.contracts.session import MeterV1
from master_all_strings.performance.export import to_dict as performance_to_dict
from master_all_strings.performance.note_pairing import pair_midi_notes

__all__ = [
    "ATTEMPT_STATUS_CAPTURING",
    "ATTEMPT_STATUS_EVALUATED",
    "ATTEMPT_STATUS_INTERRUPTED",
    "CAPTURE_CLOCK",
    "RECEIVED_LESSON_ATTEMPT_SCHEMA_ID",
    "RECEIVED_LESSON_ATTEMPT_SCHEMA_VERSION",
    "AttemptClosedError",
    "AttemptConflictError",
    "AttemptEvaluationError",
    "AttemptRequestError",
    "AttemptSnapshotError",
    "ReceivedLessonAttemptService",
    "SequenceConflictError",
    "UnknownAttemptError",
    "attempt_policy_document",
]

RECEIVED_LESSON_ATTEMPT_SCHEMA_ID = "master_all_strings.received_lesson_attempt"
RECEIVED_LESSON_ATTEMPT_SCHEMA_VERSION = "1.0.0"
ATTEMPT_STATUS_CAPTURING = "CAPTURING"
ATTEMPT_STATUS_EVALUATED = "EVALUATED"
ATTEMPT_STATUS_INTERRUPTED = "INTERRUPTED"
CAPTURE_CLOCK = "browser_performance_time"
_PHASE_CLOSING = "CLOSING"
_PHASE_FAILED = "FAILED"
_INTENT_FINISH = "finish"
_INTENT_CANCEL = "cancel"
_PASS_COUNT = 1
_PLAYBACK_RATE = 1.0

_HARDWARE_STATUS = {
    "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
    "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
}


class AttemptRequestError(Exception):
    """The caller's values are not a usable attempt request."""


class UnknownAttemptError(Exception):
    """No attempt has that id."""


class SequenceConflictError(Exception):
    """The sequence number is not the next consecutive one."""


class AttemptClosedError(Exception):
    """The attempt is no longer accepting messages."""


class AttemptConflictError(Exception):
    """This terminal operation disagrees with the one already taken."""


class AttemptEvaluationError(Exception):
    """The capture is closed, and evaluation did not produce a stored result."""


class AttemptSnapshotError(Exception):
    """The prepared bundle cannot be consumed as trusted evaluation input."""


def attempt_policy_document() -> dict[str, Any]:
    """One pass at rate 1. Looping, seeking, and lesson switches stay off.

    Reference sound is not part of the capture. A later screen may play it
    or leave it silent without changing what this attempt records.
    """

    return {
        "schema_version": RECEIVED_LESSON_ATTEMPT_SCHEMA_VERSION,
        "pass_count": _PASS_COUNT,
        "playback_rate": 1,
        "looping_allowed": False,
        "seeking_allowed": False,
        "lesson_switching_allowed": False,
        "reference_sound": "independent_of_capture",
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AttemptRequestError(f"{name} must be a nonblank string")
    return value


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AttemptRequestError(f"{name} must be a nonnegative integer")
    return value


def _practice_position(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AttemptRequestError(
            "practice_position_seconds must be a finite nonnegative number"
        )
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise AttemptRequestError(
            "practice_position_seconds must be a finite nonnegative number"
        )
    return number


def _midi_message(payload: object) -> tuple[int, int, int]:
    if not isinstance(payload, list) or len(payload) != 3:
        raise AttemptRequestError("raw_payload must be three MIDI bytes")
    values: list[int] = []
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255:
            raise AttemptRequestError("raw_payload bytes must be integers from 0 through 255")
        values.append(item)
    status, data1, data2 = values
    if (status & 0xF0) not in (0x80, 0x90):
        raise AttemptRequestError("raw_payload must be a note-on or note-off message")
    if not 0 <= data1 <= 127 or not 0 <= data2 <= 127:
        raise AttemptRequestError("MIDI data bytes must be integers from 0 through 127")
    return status, data1, data2


def _event_type(status: int, velocity: int) -> MidiEventType:
    # MIDI: note-on with velocity 0 is a note-off. Preserve that convention.
    if (status & 0xF0) == 0x80 or velocity == 0:
        return MidiEventType.NOTE_OFF
    return MidiEventType.NOTE_ON


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AttemptSnapshotError(f"{label} is not an object")
    return value


def _events_from_revision(revision: dict[str, Any]) -> tuple[MusicalEvent, ...]:
    rows = revision.get("events")
    if not isinstance(rows, list) or not rows:
        raise AttemptSnapshotError("canonical revision has no events")
    events: list[MusicalEvent] = []
    for row in rows:
        item = _mapping(row, "canonical event")
        try:
            events.append(
                MusicalEvent(
                    event_id=str(item["event_id"]),
                    midi_note=int(item["midi_note"]),
                    start_tick=int(item["start_tick"]),
                    duration_ticks=int(item["duration_ticks"]),
                    velocity=int(item["velocity"]),
                    cents_offset=float(item.get("cents_offset", 0.0)),
                    voice_id=None if item.get("voice_id") is None else str(item["voice_id"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AttemptSnapshotError("canonical event is incomplete") from exc
    return tuple(events)


def _tempo_from_playback(playback: dict[str, Any]) -> tuple[tuple[TempoChangeV1, ...], int, float]:
    timeline = _mapping(playback.get("timeline"), "playback timeline")
    rows = timeline.get("tempo_changes")
    if not isinstance(rows, list) or not rows:
        raise AttemptSnapshotError("playback timeline has no tempo map")
    changes: list[TempoChangeV1] = []
    for row in rows:
        item = _mapping(row, "tempo change")
        try:
            changes.append(
                TempoChangeV1(
                    "1.0.0",
                    int(item["tick"]),
                    int(item["microseconds_per_quarter"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AttemptSnapshotError("playback tempo change is incomplete") from exc
    ticks = timeline.get("ticks_per_quarter")
    total = playback.get("total_seconds")
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1:
        raise AttemptSnapshotError("playback ticks_per_quarter is unusable")
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(
        float(total)
    ):
        raise AttemptSnapshotError("playback total_seconds is unusable")
    if float(total) <= 0:
        raise AttemptSnapshotError("playback total_seconds is unusable")
    opening = min(changes, key=lambda change: change.tick)
    return tuple(changes), ticks, 60_000_000 / opening.microseconds_per_quarter


def _meter_from_revision(revision: dict[str, Any]) -> MeterV1:
    rows = revision.get("meter_changes")
    if not isinstance(rows, list) or not rows:
        raise AttemptSnapshotError("canonical revision has no meter map")
    maps = [_mapping(row, "meter change") for row in rows]
    opening = min(maps, key=lambda item: int(item["tick"]))
    try:
        return MeterV1("1.0.0", int(opening["numerator"]), int(opening["denominator"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AttemptSnapshotError("canonical meter is unusable") from exc


@dataclass(frozen=True)
class _TrustedInputs:
    expected: tuple[MusicalEvent, ...]
    tempo_changes: tuple[TempoChangeV1, ...]
    ticks_per_quarter: int
    total_seconds: float
    tempo_context: float
    meter: MeterV1
    canonical_revision_id: str


def trusted_evaluation_inputs(preparation: dict[str, Any]) -> _TrustedInputs:
    """Expected music and playback timing taken only from the snapshot.

    Pin equality was already required by preparation. This does not recompute
    a digest, invent a tempo, or read a demo.
    """

    playback = _mapping(preparation.get("playback"), "playback")
    score = _mapping(preparation.get("score"), "score")
    revision = _mapping(score.get("canonical_revision"), "canonical revision")
    revision_id = revision.get("revision_id")
    if not isinstance(revision_id, str) or not revision_id.strip():
        raise AttemptSnapshotError("canonical revision id is missing")
    expected = _events_from_revision(revision)
    tempo_changes, ticks, tempo_context = _tempo_from_playback(playback)
    revision_ticks = revision.get("ticks_per_quarter")
    if revision_ticks != ticks:
        raise AttemptSnapshotError("revision and playback disagree on ticks_per_quarter")
    playback_ids = {
        str(_mapping(row, "playback event")["event_id"])
        for row in _mapping_list(playback.get("events"), "playback events")
    }
    if playback_ids != {event.event_id for event in expected}:
        raise AttemptSnapshotError("playback events do not match the canonical revision")
    return _TrustedInputs(
        expected=expected,
        tempo_changes=tempo_changes,
        ticks_per_quarter=ticks,
        total_seconds=float(playback["total_seconds"]),
        tempo_context=tempo_context,
        meter=_meter_from_revision(revision),
        canonical_revision_id=revision_id,
    )


def _mapping_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise AttemptSnapshotError(f"{label} are missing")
    return value


def _identity(attempt: StoredAttempt, status: str) -> dict[str, Any]:
    preparation = attempt.preparation
    return {
        "schema_id": RECEIVED_LESSON_ATTEMPT_SCHEMA_ID,
        "schema_version": RECEIVED_LESSON_ATTEMPT_SCHEMA_VERSION,
        "attempt_status": status,
        "attempt_id": attempt.attempt_id,
        "capture_id": attempt.capture_id,
        "performance_session_id": attempt.performance_session_id,
        "delivery_id": preparation["delivery_id"],
        "assignment_id": preparation["assignment_id"],
        "content_id": preparation["content_id"],
        "assignment_artifact_digest": preparation["assignment_artifact_digest"],
        "assignment_behavior_digest": preparation["assignment_behavior_digest"],
        "capture_clock": CAPTURE_CLOCK,
    }


def _messages_for(evaluation: dict[str, Any]) -> dict[str, str]:
    messages: dict[str, str] = {}
    for finding in evaluation["findings"]:
        key = finding["message_key"]
        if key in MESSAGE_CATALOG_V1:
            messages[key] = MESSAGE_CATALOG_V1[key]
    primary = evaluation["primary_next_action"]["message_key"]
    messages[primary] = MESSAGE_CATALOG_V1[primary]
    for action in evaluation["secondary_actions"]:
        messages[action["message_key"]] = MESSAGE_CATALOG_V1[action["message_key"]]
    return messages


class ReceivedLessonAttemptService:
    """One in-memory attempt at a time, isolated from every other attempt."""

    def __init__(
        self,
        deliveries: LessonDeliveryService,
        choices: InMemoryLocalPracticeChoiceRepository,
        *,
        repository: ReceivedLessonAttemptRepository | None = None,
        ids: Callable[[], str] | None = None,
        now_utc: Callable[[], str] | None = None,
        align: Callable[..., Any] = align_performance,
        evaluate: Callable[..., Any] = evaluate_practice_attempt,
        guide: Callable[..., Any] = build_teaching_guidance_projection,
        encode_performance: Callable[[Any], dict[str, Any]] = performance_to_dict,
        encode_education: Callable[[Any], dict[str, Any]] = education_to_dict,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._deliveries = deliveries
        self._choices = choices
        self.repository = repository or ReceivedLessonAttemptRepository()
        self._ids = ids or (lambda: str(uuid4()))
        self._now_utc = now_utc or _utc_now
        self._align = align
        self._evaluate = evaluate
        self._guide = guide
        self._encode_performance = encode_performance
        self._encode_education = encode_education
        self.before_commit = before_commit

    def _preparations(self) -> LocalPracticePreparationService:
        return LocalPracticePreparationService(
            self._deliveries,
            LocalPracticeChoiceService(
                LessonDeliveryPreviewService(self._deliveries),
                self._choices,
            ),
            shared_application(),
        )

    def begin(
        self,
        delivery_id: str,
        artifact_digest: str,
        behavior_digest: str,
        device_id: str,
        capture_time_ns: int,
    ) -> dict[str, Any]:
        """Prepare a fresh snapshot and open a capture. Do not start playback."""

        delivery_id = _nonblank(delivery_id, "delivery_id")
        device_id = _nonblank(device_id, "device_id")
        capture_time_ns = _nonnegative_int(capture_time_ns, "capture_time_ns")
        prepared = self._preparations().prepare(delivery_id, artifact_digest, behavior_digest)
        document = preparation_to_dict(prepared)
        trusted = trusted_evaluation_inputs(document)
        history = PracticeSessionHistory()
        history.begin_lesson(
            assignment_id=document["assignment_id"],
            content_id=document["content_id"],
        )
        attempt_id = self._ids()
        capture_id = self._ids()
        session_id = self._ids()
        attempt = StoredAttempt(
            attempt_id=attempt_id,
            capture_id=capture_id,
            performance_session_id=session_id,
            device_id=device_id,
            begin_capture_time_ns=capture_time_ns,
            preparation=deepcopy(document),
            policy=attempt_policy_document(),
            expected_events=trusted.expected,
            tempo_changes=trusted.tempo_changes,
            ticks_per_quarter=trusted.ticks_per_quarter,
            total_seconds=trusted.total_seconds,
            tempo_context=trusted.tempo_context,
            meter_context=trusted.meter,
            canonical_revision_id=trusted.canonical_revision_id,
            capture=self._open_capture(
                capture_id=capture_id,
                session_id=session_id,
                device_id=device_id,
                tempo_context=trusted.tempo_context,
                meter=trusted.meter,
            ),
            history=history,
        )
        try:
            self.repository.insert(attempt)
        except AttemptCollisionError as exc:
            raise AttemptSnapshotError("attempt id collided") from exc
        body = _identity(attempt, ATTEMPT_STATUS_CAPTURING)
        body["preparation"] = deepcopy(attempt.preparation)
        body["attempt_policy"] = deepcopy(attempt.policy)
        return body

    def _open_capture(
        self,
        *,
        capture_id: str,
        session_id: str,
        device_id: str,
        tempo_context: float,
        meter: MeterV1,
    ) -> Any:
        return build_raw_capture(
            capture_id=capture_id,
            session_id=session_id,
            runtime_identity=RuntimeIdentityV1(
                "1.0.0",
                "web-midi",
                RuntimeKind.LIGHTWEIGHT,
                "1",
                "web-midi-v1",
                True,
            ),
            source_identity=CaptureSourceV1("1.0.0", device_id, "browser", device_id, False),
            started_at=self._now_utc(),
            tempo_context=tempo_context,
            meter_context=meter,
            provenance=(("clock_domain", CAPTURE_CLOCK),),
        )

    def append_message(
        self,
        attempt_id: str,
        sequence_number: int,
        capture_time_ns: int,
        practice_position_seconds: float,
        raw_payload: list[int],
    ) -> dict[str, Any]:
        """Accept the next note message, or leave the capture unchanged."""

        attempt_id = _nonblank(attempt_id, "attempt_id")
        sequence_number = _nonnegative_int(sequence_number, "sequence_number")
        capture_time_ns = _nonnegative_int(capture_time_ns, "capture_time_ns")
        position = _practice_position(practice_position_seconds)
        status, note, velocity = _midi_message(raw_payload)
        attempt = self._require(attempt_id)
        with attempt.lock:
            if attempt.phase != ATTEMPT_STATUS_CAPTURING:
                raise AttemptClosedError("attempt_closed")
            if sequence_number != attempt.next_sequence:
                raise SequenceConflictError("sequence_conflict")
            self._check_clock(attempt, capture_time_ns)
            if (
                attempt.last_practice_position is not None
                and position < attempt.last_practice_position
            ):
                raise AttemptRequestError("practice_position_seconds must not decrease")
            if position > attempt.total_seconds:
                raise AttemptRequestError(
                    "practice_position_seconds is outside the prepared playback"
                )
            if self.before_commit is not None:
                self.before_commit()
            event_id = self._ids()
            event = normalize_midi_event(
                event_id=event_id,
                sequence_number=sequence_number,
                event_type=_event_type(status, velocity),
                capture_time_ns=capture_time_ns,
                channel=status & 0x0F,
                source_port="browser",
                source_device=attempt.device_id,
                note=note,
                velocity=velocity,
                raw_payload=(status, note, velocity),
            )
            attempt.capture = append_events(attempt.capture, (event,))
            attempt.positions[event_id] = position
            attempt.next_sequence += 1
            attempt.last_capture_time_ns = capture_time_ns
            attempt.last_practice_position = position
            count = len(attempt.capture.events)
        body = _identity(attempt, ATTEMPT_STATUS_CAPTURING)
        body["accepted_event_count"] = count
        return body

    def finish(self, attempt_id: str, capture_time_ns: int) -> dict[str, Any]:
        """Close, pair, and evaluate once. A repeat returns the stored result."""

        return self._terminal(attempt_id, capture_time_ns, _INTENT_FINISH)

    def cancel(self, attempt_id: str, capture_time_ns: int) -> dict[str, Any]:
        """Close as interrupted. Do not evaluate or claim success."""

        return self._terminal(attempt_id, capture_time_ns, _INTENT_CANCEL)

    def _terminal(self, attempt_id: str, capture_time_ns: int, intent: str) -> dict[str, Any]:
        attempt_id = _nonblank(attempt_id, "attempt_id")
        capture_time_ns = _nonnegative_int(capture_time_ns, "capture_time_ns")
        attempt = self._require(attempt_id)
        winner = False
        with attempt.lock:
            if attempt.phase == ATTEMPT_STATUS_CAPTURING:
                self._check_clock(attempt, capture_time_ns)
                attempt.phase = _PHASE_CLOSING
                attempt.intent = intent
                state = (
                    CaptureCompletionState.COMPLETE
                    if intent == _INTENT_FINISH
                    else CaptureCompletionState.INTERRUPTED
                )
                attempt.capture = close_capture(
                    attempt.capture,
                    ended_at=self._now_utc(),
                    completion_state=state,
                )
                winner = True
            elif attempt.intent == intent and attempt.phase == _PHASE_CLOSING:
                while attempt.phase == _PHASE_CLOSING:
                    attempt.ready.wait()
            if not winner:
                return self._stored_terminal(attempt, intent)
        try:
            if intent == _INTENT_FINISH:
                document = self._evaluate_closed(attempt)
                status = ATTEMPT_STATUS_EVALUATED
            else:
                document = self._interrupted_document(attempt)
                status = ATTEMPT_STATUS_INTERRUPTED
        except AttemptEvaluationError:
            self._mark_failed(attempt)
            raise
        except Exception as exc:
            self._mark_failed(attempt)
            raise AttemptEvaluationError("evaluation failed") from exc
        with attempt.lock:
            attempt.result = document
            attempt.phase = status
            attempt.ready.notify_all()
        return deepcopy(document)

    def _stored_terminal(self, attempt: StoredAttempt, intent: str) -> dict[str, Any]:
        """Read a terminal outcome. The caller holds the attempt lock."""

        if attempt.intent == intent and attempt.phase in (
            ATTEMPT_STATUS_EVALUATED,
            ATTEMPT_STATUS_INTERRUPTED,
        ):
            if attempt.result is None:
                raise AttemptEvaluationError("evaluation failed")
            return deepcopy(attempt.result)
        if attempt.intent == intent and attempt.phase == _PHASE_FAILED:
            raise AttemptEvaluationError("evaluation failed")
        raise AttemptConflictError("attempt_conflict")

    def _mark_failed(self, attempt: StoredAttempt) -> None:
        with attempt.lock:
            if attempt.phase == _PHASE_CLOSING:
                attempt.phase = _PHASE_FAILED
                attempt.ready.notify_all()

    def _evaluate_closed(self, attempt: StoredAttempt) -> dict[str, Any]:
        paired = self._paired(attempt)
        observed = self._with_positions(attempt, paired.observed_notes)
        alignment = self._align(
            assignment_id=attempt.preparation["assignment_id"],
            content_id=attempt.preparation["content_id"],
            performance_session_id=attempt.performance_session_id,
            expected=attempt.expected_events,
            observed=tuple(observed),
            policy=PerformanceAlignmentPolicyV1(),
            ticks_per_quarter=attempt.ticks_per_quarter,
            tempo_changes=attempt.tempo_changes,
            repetition_count=_PASS_COUNT,
        )
        result = self._evaluate(
            alignment,
            history=attempt.history,
            current_rate=_PLAYBACK_RATE,
        )
        guidance = self._guide(result, canonical_revision_id=attempt.canonical_revision_id)
        evaluation = self._encode_education(result)
        body = _identity(attempt, ATTEMPT_STATUS_EVALUATED)
        body["raw_capture"] = self._encode_performance(attempt.capture)
        body["observed_events"] = [self._encode_performance(note) for note in observed]
        body["unmatched_note_offs"] = [
            self._encode_performance(note) for note in paired.unmatched_note_offs
        ]
        body["evaluation"] = evaluation
        body["messages"] = _messages_for(evaluation)
        body["guidance"] = self._encode_education(guidance)
        body["hardware_status"] = dict(_HARDWARE_STATUS)
        return body

    def _interrupted_document(self, attempt: StoredAttempt) -> dict[str, Any]:
        paired = self._paired(attempt)
        observed = self._with_positions(attempt, paired.observed_notes)
        body = _identity(attempt, ATTEMPT_STATUS_INTERRUPTED)
        body["raw_capture"] = self._encode_performance(attempt.capture)
        body["observed_events"] = [self._encode_performance(note) for note in observed]
        body["unmatched_note_offs"] = [
            self._encode_performance(note) for note in paired.unmatched_note_offs
        ]
        body["hardware_status"] = dict(_HARDWARE_STATUS)
        return body

    def _paired(self, attempt: StoredAttempt) -> Any:
        return pair_midi_notes(
            attempt.capture,
            observed_id_factory=lambda _index: self._ids(),
            repetition_resolver=lambda _event: 0,
        )

    def _with_positions(
        self, attempt: StoredAttempt, notes: tuple[ObservedMidiNoteV1, ...]
    ) -> tuple[ObservedMidiNoteV1, ...]:
        placed: list[ObservedMidiNoteV1] = []
        for note in notes:
            onset = attempt.positions.get(note.note_on_event_id)
            if onset is None:
                raise AttemptSnapshotError("accepted note is missing its practice position")
            placed.append(replace(note, practice_onset_seconds=onset))
        return tuple(placed)

    def _check_clock(self, attempt: StoredAttempt, capture_time_ns: int) -> None:
        if capture_time_ns < attempt.last_capture_time_ns:
            raise AttemptRequestError("capture_time_ns must not decrease")

    def _require(self, attempt_id: str) -> StoredAttempt:
        attempt = self.repository.get(attempt_id)
        if attempt is None:
            raise UnknownAttemptError("unknown_attempt")
        return attempt
