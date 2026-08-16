"""Derived live-MIDI note evidence built from immutable raw capture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.foundation import require_midi_note
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_range,
    require_schema_version,
)


class ObservedMidiNoteStatus(StrEnum):
    COMPLETE = "complete"
    UNMATCHED_NOTE_ON = "unmatched_note_on"


@dataclass(frozen=True)
class ObservedMidiNoteV1:
    """One learner note derived from raw messages without rewriting them."""

    schema_version: str
    observed_event_id: str
    capture_id: str
    note_on_event_id: str
    note_off_event_id: str | None
    midi_note: int
    velocity: int
    channel: int
    source_device: str
    note_on_time_ns: int
    note_off_time_ns: int | None
    duration_ns: int | None
    source_string: int | None
    status: ObservedMidiNoteStatus
    repetition_index: int
    practice_onset_seconds: float | None = None
    estimated_start_tick: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.observed_event_id, "observed_event_id")
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.note_on_event_id, "note_on_event_id")
        require_optional_identifier(self.note_off_event_id, "note_off_event_id")
        require_midi_note(self.midi_note, "midi_note")
        require_range(self.velocity, "velocity", 1, 127)
        require_range(self.channel, "channel", 0, 15)
        require_identifier(self.source_device, "source_device")
        require_nonnegative_int(self.note_on_time_ns, "note_on_time_ns")
        require_nonnegative_int(self.repetition_index, "repetition_index")
        if self.source_string is not None:
            require_range(self.source_string, "source_string", 0, 15)
        if not isinstance(self.status, ObservedMidiNoteStatus):
            raise PerformanceContractError("status must be an ObservedMidiNoteStatus")
        self._validate_closure()
        self._validate_derived_location()

    def _validate_closure(self) -> None:
        optional = (self.note_off_event_id, self.note_off_time_ns, self.duration_ns)
        if self.status is ObservedMidiNoteStatus.COMPLETE:
            if any(value is None for value in optional):
                raise PerformanceContractError("complete note requires note-off evidence")
            assert self.note_off_time_ns is not None
            assert self.duration_ns is not None
            if self.note_off_time_ns < self.note_on_time_ns:
                raise PerformanceContractError("note_off_time_ns must not precede note_on_time_ns")
            if self.duration_ns != self.note_off_time_ns - self.note_on_time_ns:
                raise PerformanceContractError(
                    "duration_ns must equal the observed timestamp delta"
                )
        elif any(value is not None for value in optional):
            raise PerformanceContractError("unmatched note-on must not invent note-off evidence")

    def _validate_derived_location(self) -> None:
        if self.practice_onset_seconds is not None:
            value = self.practice_onset_seconds
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PerformanceContractError("practice_onset_seconds must be a number")
            if value != value or value in (float("inf"), float("-inf")) or value < 0:
                raise PerformanceContractError(
                    "practice_onset_seconds must be finite and nonnegative"
                )
        if self.estimated_start_tick is not None:
            require_nonnegative_int(self.estimated_start_tick, "estimated_start_tick")


@dataclass(frozen=True)
class UnmatchedMidiNoteOffV1:
    """A note-off that had no eligible preceding note-on."""

    schema_version: str
    raw_event_id: str
    capture_id: str
    midi_note: int
    channel: int
    source_device: str
    capture_time_ns: int
    source_string: int | None
    repetition_index: int

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.raw_event_id, "raw_event_id")
        require_identifier(self.capture_id, "capture_id")
        require_midi_note(self.midi_note, "midi_note")
        require_range(self.channel, "channel", 0, 15)
        require_identifier(self.source_device, "source_device")
        require_nonnegative_int(self.capture_time_ns, "capture_time_ns")
        require_nonnegative_int(self.repetition_index, "repetition_index")
        if self.source_string is not None:
            require_range(self.source_string, "source_string", 0, 15)
