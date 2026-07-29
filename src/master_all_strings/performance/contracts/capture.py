"""Raw capture contracts — the evidence record of what was actually played.

This is the most consequential module in the package, because everything downstream
cites it and nothing may rewrite it (ADR-0007 D6). Three invariants carry that
weight, and each is enforced at construction:

* **Order and timing are preserved.** ``sequence_number`` is strictly increasing and
  ``capture_time_ns`` is non-decreasing across a capture. Quantization, cleanup, and
  notation spelling happen later, elsewhere, to derived records.
* **Closure is explicit.** A capture is ``IN_PROGRESS`` until someone closes it with a
  terminal state. A crash produces ``INTERRUPTED``, never ``COMPLETE`` — a partial
  take is never silently promoted to a whole one (ADR-0007 D15).
* **String identity is observed or unresolved, never inferred.** ``source_string`` is
  ``None`` when the source did not supply it. TAB fingering is a Musical Core
  projection produced later; recording a guess here would make an inference
  indistinguishable from a measurement (ADR-0007 D7).

Timing representation: ``capture_time_ns`` is integer nanoseconds from a monotonic
source, so it survives wall-clock adjustment mid-take. Session boundaries
(``started_at``, ``ended_at``) are ISO-8601 UTC strings. The two never mix.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.foundation import require_midi_note
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
    require_nonnegative_int,
    require_range,
    require_raw_payload,
    require_schema_version,
    require_tuple,
    require_unique,
    require_utc_timestamp,
)
from master_all_strings.performance.contracts.runtime import (
    RuntimeFaultV1,
    RuntimeIdentityV1,
    RuntimeState,
)
from master_all_strings.performance.contracts.session import MeterV1

# ``source_string`` uses None for "the source did not tell us". Named so the intent is
# legible at call sites: an unresolved string is a fact about the evidence, not a gap
# to be filled in later by a guess.
SOURCE_STRING_UNRESOLVED: None = None

# 14-bit signed pitch bend, centred at zero.
MIN_PITCH_BEND = -8192
MAX_PITCH_BEND = 8191


class MidiEventType(StrEnum):
    """The kind of MIDI event captured."""

    NOTE_ON = "note_on"
    NOTE_OFF = "note_off"
    CONTROL_CHANGE = "control_change"
    PITCH_BEND = "pitch_bend"
    PROGRAM_CHANGE = "program_change"
    CHANNEL_PRESSURE = "channel_pressure"


# Which fields each event type requires. Held as data rather than as a chain of
# conditionals so the rule can be asserted directly in tests and mirrored in the
# JSON Schema without the two drifting.
NOTE_EVENT_TYPES = (MidiEventType.NOTE_ON, MidiEventType.NOTE_OFF)
CONTROLLER_EVENT_TYPES = (MidiEventType.CONTROL_CHANGE,)


class CaptureCompletionState(StrEnum):
    """How a capture ended.

    ``INTERRUPTED`` and ``FAILED`` are distinct: interrupted means events were
    accepted and the take was cut short; failed means the capture could not produce a
    usable record at all.
    """

    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_COMPLETION_STATES = (
    CaptureCompletionState.COMPLETE,
    CaptureCompletionState.INTERRUPTED,
    CaptureCompletionState.FAILED,
    CaptureCompletionState.CANCELLED,
)


@dataclass(frozen=True)
class CaptureSourceV1:
    """Where captured events came from."""

    schema_version: str
    source_id: str
    port: str
    device: str
    supplies_string_identity: bool

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.source_id, "source_id")
        require_identifier(self.port, "port")
        require_identifier(self.device, "device")
        if not isinstance(self.supplies_string_identity, bool):
            raise PerformanceContractError("supplies_string_identity must be a boolean")


@dataclass(frozen=True)
class CapturedMidiEventV1:
    """One captured MIDI event, exactly as received (§6.2).

    Conditional fields are enforced both ways: a note event must carry note data, and
    a controller event must not. Permitting stray fields would let two different
    events serialize identically.
    """

    schema_version: str
    event_id: str
    sequence_number: int
    event_type: MidiEventType
    capture_time_ns: int
    channel: int
    source_port: str
    source_device: str
    note: int | None = None
    velocity: int | None = None
    controller: int | None = None
    controller_value: int | None = None
    pitch_bend: int | None = None
    source_string: int | None = SOURCE_STRING_UNRESOLVED
    raw_payload: tuple[int, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.event_id, "event_id")
        require_nonnegative_int(self.sequence_number, "sequence_number")
        if not isinstance(self.event_type, MidiEventType):
            raise PerformanceContractError("event_type must be a MidiEventType")
        require_nonnegative_int(self.capture_time_ns, "capture_time_ns")
        require_range(self.channel, "channel", 0, 15)
        require_identifier(self.source_port, "source_port")
        require_identifier(self.source_device, "source_device")
        require_raw_payload(self.raw_payload, "raw_payload")

        self._validate_note_fields()
        self._validate_controller_fields()
        self._validate_pitch_bend()
        self._validate_source_string()

    def _validate_note_fields(self) -> None:
        if self.event_type in NOTE_EVENT_TYPES:
            if self.note is None:
                raise PerformanceContractError(f"{self.event_type} requires note")
            require_midi_note(self.note, "note")
            if self.velocity is None:
                raise PerformanceContractError(f"{self.event_type} requires velocity")
            require_range(self.velocity, "velocity", 0, 127)
        else:
            if self.note is not None:
                raise PerformanceContractError(f"{self.event_type} must not carry note")
            if self.velocity is not None:
                raise PerformanceContractError(f"{self.event_type} must not carry velocity")

    def _validate_controller_fields(self) -> None:
        if self.event_type in CONTROLLER_EVENT_TYPES:
            if self.controller is None:
                raise PerformanceContractError(f"{self.event_type} requires controller")
            require_range(self.controller, "controller", 0, 127)
            if self.controller_value is None:
                raise PerformanceContractError(f"{self.event_type} requires controller_value")
            require_range(self.controller_value, "controller_value", 0, 127)
        else:
            if self.controller is not None:
                raise PerformanceContractError(f"{self.event_type} must not carry controller")
            if self.controller_value is not None:
                raise PerformanceContractError(f"{self.event_type} must not carry controller_value")

    def _validate_pitch_bend(self) -> None:
        if self.event_type is MidiEventType.PITCH_BEND:
            if self.pitch_bend is None:
                raise PerformanceContractError("pitch_bend event requires pitch_bend")
            require_range(self.pitch_bend, "pitch_bend", MIN_PITCH_BEND, MAX_PITCH_BEND)
        elif self.pitch_bend is not None:
            raise PerformanceContractError(f"{self.event_type} must not carry pitch_bend")

    def _validate_source_string(self) -> None:
        # Optional by design. None means the source did not report a string; it does
        # not mean string 0, and it must never be replaced by an inferred value.
        if self.source_string is not None:
            require_range(self.source_string, "source_string", 0, 15)

    @property
    def string_identity_resolved(self) -> bool:
        """Whether the source actually reported a string for this event."""
        return self.source_string is not None


@dataclass(frozen=True)
class RawPerformanceCaptureV1:
    """The immutable record of one take (§6.3).

    Immutability is structural: the dataclass is frozen and every collection is a
    tuple, so a closed capture cannot be edited in place by any downstream consumer.
    Producing a changed version means producing a *new* record that cites this one.
    """

    schema_version: str
    capture_id: str
    session_id: str
    runtime_identity: RuntimeIdentityV1
    source_identity: CaptureSourceV1
    started_at: str
    completion_state: CaptureCompletionState
    tempo_context: float
    meter_context: MeterV1
    events: tuple[CapturedMidiEventV1, ...] = ()
    ended_at: str | None = None
    warnings: tuple[str, ...] = ()
    faults: tuple[RuntimeFaultV1, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.session_id, "session_id")
        if not isinstance(self.runtime_identity, RuntimeIdentityV1):
            raise PerformanceContractError("runtime_identity must be a RuntimeIdentityV1")
        if not isinstance(self.source_identity, CaptureSourceV1):
            raise PerformanceContractError("source_identity must be a CaptureSourceV1")
        require_utc_timestamp(self.started_at, "started_at")
        if not isinstance(self.completion_state, CaptureCompletionState):
            raise PerformanceContractError("completion_state must be a CaptureCompletionState")
        if isinstance(self.tempo_context, bool) or not isinstance(
            self.tempo_context, (int, float)
        ):
            raise PerformanceContractError("tempo_context must be a number")
        if not isinstance(self.meter_context, MeterV1):
            raise PerformanceContractError("meter_context must be a MeterV1")

        self._validate_closure()
        self._validate_events()
        self._validate_collections()

    def _validate_closure(self) -> None:
        closed = self.completion_state in TERMINAL_COMPLETION_STATES
        if closed:
            if self.ended_at is None:
                raise PerformanceContractError(
                    f"completion_state {self.completion_state} requires ended_at; "
                    "a closed capture must say when it closed"
                )
            require_utc_timestamp(self.ended_at, "ended_at")
        elif self.ended_at is not None:
            raise PerformanceContractError("an IN_PROGRESS capture must not have ended_at")

    def _validate_events(self) -> None:
        require_tuple(self.events, "events")
        previous_sequence: int | None = None
        previous_time: int | None = None
        for event in self.events:
            if not isinstance(event, CapturedMidiEventV1):
                raise PerformanceContractError("events must contain CapturedMidiEventV1 values")
            if previous_sequence is not None and event.sequence_number <= previous_sequence:
                raise PerformanceContractError(
                    "sequence_number must strictly increase; "
                    f"{event.sequence_number} followed {previous_sequence}"
                )
            if previous_time is not None and event.capture_time_ns < previous_time:
                raise PerformanceContractError(
                    "capture_time_ns must not decrease; "
                    f"{event.capture_time_ns} followed {previous_time}"
                )
            previous_sequence = event.sequence_number
            previous_time = event.capture_time_ns
        require_unique([e.event_id for e in self.events], "event_id")

    def _validate_collections(self) -> None:
        require_tuple(self.warnings, "warnings")
        for warning in self.warnings:
            require_identifier(warning, "warnings entry")
        require_tuple(self.faults, "faults")
        for fault in self.faults:
            if not isinstance(fault, RuntimeFaultV1):
                raise PerformanceContractError("faults must contain RuntimeFaultV1 values")
        require_tuple(self.provenance, "provenance")
        for entry in self.provenance:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise PerformanceContractError("provenance entries must be (key, value) pairs")
            require_identifier(entry[0], "provenance key")
        require_unique([k for k, _ in self.provenance], "provenance keys")

    @property
    def is_closed(self) -> bool:
        """Whether this capture has reached a terminal state."""
        return self.completion_state in TERMINAL_COMPLETION_STATES

    @property
    def event_count(self) -> int:
        """How many events this capture holds."""
        return len(self.events)


@dataclass(frozen=True)
class PerformanceObservationV1:
    """Factual evidence derived from a capture (§6.5).

    The constitutional contract from ADR-0006 Seam 4, implemented here for the first
    time. Every field is a count, a bound, or a state — never a judgment. Educational
    interprets these facts and cites this record; Performance never draws the
    conclusion itself (ADR-0007 D10).

    What may never appear here: mastery, difficulty, technique quality, lesson
    outcomes, curriculum recommendations, or learner classification. That is enforced
    by an allowlist test, because the boundary erodes one plausible field at a time.
    """

    schema_version: str
    observation_id: str
    capture_id: str
    session_id: str
    observed_at: str
    event_count: int
    note_on_count: int
    note_off_count: int
    completion_state: CaptureCompletionState
    runtime_state: RuntimeState
    first_event_time_ns: int | None = None
    last_event_time_ns: int | None = None
    velocity_min: int | None = None
    velocity_max: int | None = None
    channels_observed: tuple[int, ...] = ()
    source_strings_observed: tuple[int, ...] = ()
    unresolved_string_event_count: int = 0
    missing_note_off_count: int = 0
    fault_codes: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.observation_id, "observation_id")
        # An observation without its source is an assertion without evidence.
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.session_id, "session_id")
        require_utc_timestamp(self.observed_at, "observed_at")
        for name in (
            "event_count",
            "note_on_count",
            "note_off_count",
            "unresolved_string_event_count",
            "missing_note_off_count",
        ):
            require_nonnegative_int(getattr(self, name), name)
        if not isinstance(self.completion_state, CaptureCompletionState):
            raise PerformanceContractError("completion_state must be a CaptureCompletionState")
        if not isinstance(self.runtime_state, RuntimeState):
            raise PerformanceContractError("runtime_state must be a RuntimeState")

        for name in ("first_event_time_ns", "last_event_time_ns"):
            value = getattr(self, name)
            if value is not None:
                require_nonnegative_int(value, name)
        if (
            self.first_event_time_ns is not None
            and self.last_event_time_ns is not None
            and self.last_event_time_ns < self.first_event_time_ns
        ):
            raise PerformanceContractError(
                "last_event_time_ns must not precede first_event_time_ns"
            )

        for name in ("velocity_min", "velocity_max"):
            value = getattr(self, name)
            if value is not None:
                require_range(value, name, 0, 127)
        if (
            self.velocity_min is not None
            and self.velocity_max is not None
            and self.velocity_max < self.velocity_min
        ):
            raise PerformanceContractError("velocity_max must not be below velocity_min")

        require_tuple(self.channels_observed, "channels_observed")
        for channel in self.channels_observed:
            require_range(channel, "channels_observed entry", 0, 15)
        require_unique(self.channels_observed, "channels_observed")

        require_tuple(self.source_strings_observed, "source_strings_observed")
        for string_index in self.source_strings_observed:
            require_range(string_index, "source_strings_observed entry", 0, 15)
        require_unique(self.source_strings_observed, "source_strings_observed")

        require_tuple(self.fault_codes, "fault_codes")
        for code in self.fault_codes:
            require_identifier(code, "fault_codes entry")

        if self.note_on_count + self.note_off_count > self.event_count:
            raise PerformanceContractError(
                "note_on_count + note_off_count cannot exceed event_count"
            )

    @property
    def has_unresolved_string_identity(self) -> bool:
        """Whether any captured event lacked a reported string."""
        return self.unresolved_string_event_count > 0
