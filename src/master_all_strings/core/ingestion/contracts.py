"""The Performance-to-Musical-Core ingestion request.

**These contracts live in Musical Core because Core owns them.** The registry has
always said so — ``CanonicalIngestionRequestV1`` is ``owning_engine: MUSICAL_CORE``,
``producers: [PERFORMANCE_ENGINE]`` — but DO-006 placed the class inside the
Performance package, which was harmless only while Core had no ingestion service. Now
that Core consumes the request, leaving it there would force ``core`` to import from
``performance`` and break the dependency matrix. Performance imports these from Core,
which is the permitted direction.

Two consequences follow, and both are deliberate.

**Core never sees ``RawPerformanceCaptureV1``.** That contract genuinely is
Performance-owned, so Core cannot import it. The request therefore carries the source
events in a Core-owned neutral form (``SourceMidiEventV1``) that Performance fills in.
The raw capture stays where it belongs, is never handed across, and is never mutated —
Core works from a copy of what it was told.

**The request carries a capture origin and an authoritative tempo.** Elapsed time needs
an origin, and ``RawPerformanceCaptureV1`` has only an ISO wall-clock ``started_at``,
not a monotonic one. Tempo is carried as integer microseconds-per-quarter rather than
float BPM, matching ``TempoChangeV1``, so the value that ends up in the content digest
cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.foundation import require_midi_note
from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_positive_int,
    require_prefixed_digest,
    require_schema_version,
    require_tuple,
    require_unique,
    require_utc_timestamp,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import SUPPORTED_TICKS_PER_QUARTER
from master_all_strings.core.score.provenance import MAX_MIDI_CHANNEL, MAX_SOURCE_STRING

MAX_VELOCITY = 127


class ProjectionType(StrEnum):
    """Which Musical Core projections a requester wants from the revision.

    Piano roll sits beside notation and TAB because it is the same kind of thing: a
    projection of one canonical revision, not a second score model (ADR-0008 D10).
    """

    PIANO_ROLL = "piano_roll"
    NOTATION = "notation"
    TAB = "tab"
    MIDI = "midi"


class SourceMidiEventKind(StrEnum):
    """The captured event kinds ``DIRECT_EVENT_IMPORT_V1`` can pair into notes.

    Deliberately narrow. Controller, pitch-bend, program-change, and channel-pressure
    events exist in a capture and are preserved there, but this policy has no canonical
    representation for them, so it does not pretend to import them.
    """

    NOTE_ON = "note_on"
    NOTE_OFF = "note_off"


@dataclass(frozen=True)
class SourceMidiEventV1:
    """One captured note event, in a form Musical Core can read.

    A neutral restatement of what Performance observed. ``observed_source_string`` is
    carried through because a divided pickup reports it and TAB projection can cite it
    as observed rather than computed — but it is evidence about the capture, so it lands
    in provenance, never on ``MusicalEvent`` (ADR-0008 D9).
    """

    schema_version: str
    source_event_id: str
    kind: SourceMidiEventKind
    capture_time_ns: int
    channel: int
    midi_note: int
    velocity: int
    observed_source_string: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.source_event_id, "source_event_id")
        if not isinstance(self.kind, SourceMidiEventKind):
            raise ScoreContractError("kind must be a SourceMidiEventKind")
        require_nonnegative_int(self.capture_time_ns, "capture_time_ns")
        self._require_range(self.channel, "channel", 0, MAX_MIDI_CHANNEL)
        require_midi_note(self.midi_note, "midi_note")
        self._require_range(self.velocity, "velocity", 0, MAX_VELOCITY)
        if self.observed_source_string is not None:
            self._require_range(
                self.observed_source_string, "observed_source_string", 0, MAX_SOURCE_STRING
            )

    @staticmethod
    def _require_range(value: int, field_name: str, low: int, high: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ScoreContractError(f"{field_name} must be an integer")
        if not low <= value <= high:
            raise ScoreContractError(f"{field_name} must be between {low} and {high}")

    @property
    def releases_a_note(self) -> bool:
        """Whether this event ends a sounding note.

        A note-on with velocity 0 is a note-off by MIDI convention. Treating it
        otherwise would leave a phantom sounding note and reject a valid take.
        """
        return self.kind is SourceMidiEventKind.NOTE_OFF or (
            self.kind is SourceMidiEventKind.NOTE_ON and self.velocity == 0
        )


@dataclass(frozen=True)
class CanonicalIngestionRequestV1:
    """Ask Musical Core to ingest captured performance into a canonical revision.

    Carries no revision id at all. DO-006's version had an optional one that Core would
    fill in; that was the wrong shape, because a request is what Performance *asks* and
    a revision id is what Core *answers*. The answer now lives on
    ``CanonicalIngestionResultV1``, so Performance has no field it could populate even
    by mistake.
    """

    schema_version: str
    request_id: str
    capture_id: str
    source_session_id: str
    raw_capture_digest: str
    capture_origin_ns: int
    tempo_microseconds_per_quarter: int
    meter: MeterChangeV1
    requested_at: str
    source_events: tuple[SourceMidiEventV1, ...] = ()
    instrument_profile_id: str | None = None
    tuning_profile_id: str | None = None
    requested_projection_types: tuple[ProjectionType, ...] = ()
    ticks_per_quarter: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.request_id, "request_id")
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.source_session_id, "source_session_id")
        # A real digest, not any non-blank string. This value stands in for the capture
        # Core is never handed, and ingestion fingerprints it into request identity, so
        # an unchecked field would let a fabricated or truncated digest key a duplicate
        # check on nothing.
        require_prefixed_digest(self.raw_capture_digest, "raw_capture_digest")
        require_nonnegative_int(self.capture_origin_ns, "capture_origin_ns")
        require_positive_int(
            self.tempo_microseconds_per_quarter, "tempo_microseconds_per_quarter"
        )
        if not isinstance(self.meter, MeterChangeV1):
            raise ScoreContractError("meter must be a MeterChangeV1")
        if self.meter.tick != 0:
            raise ScoreContractError("the ingestion meter must be declared at tick 0")
        require_utc_timestamp(self.requested_at, "requested_at")
        require_optional_identifier(self.instrument_profile_id, "instrument_profile_id")
        require_optional_identifier(self.tuning_profile_id, "tuning_profile_id")
        if self.ticks_per_quarter is not None:
            require_positive_int(self.ticks_per_quarter, "ticks_per_quarter")
            # The revision contract accepts only the conventional divisions, so a
            # request naming any other value can never produce a revision. Refusing it
            # here turns what was an unhandled contract error thrown from the middle of
            # Core's ingestion service into a validation failure the caller can act on,
            # and does it before a document id has been spent.
            if self.ticks_per_quarter not in SUPPORTED_TICKS_PER_QUARTER:
                raise ScoreContractError(
                    "ticks_per_quarter must be one of "
                    f"{list(SUPPORTED_TICKS_PER_QUARTER)}, got {self.ticks_per_quarter}"
                )

        require_tuple(self.source_events, "source_events")
        for event in self.source_events:
            if not isinstance(event, SourceMidiEventV1):
                raise ScoreContractError("source_events must contain SourceMidiEventV1 values")
        require_unique(
            [event.source_event_id for event in self.source_events], "source_event_id"
        )

        require_tuple(self.requested_projection_types, "requested_projection_types")
        for projection in self.requested_projection_types:
            if not isinstance(projection, ProjectionType):
                raise ScoreContractError(
                    "requested_projection_types must contain ProjectionType values"
                )
        require_unique(self.requested_projection_types, "requested_projection_types")

        # A request naming no revision is the whole point; assert the field does not
        # exist rather than trusting a reviewer to notice one being added.
        if hasattr(self, "canonical_revision_id"):  # pragma: no cover - guard
            raise ScoreContractError(
                "an ingestion request must not carry a revision id; Core answers with one"
            )

    @property
    def event_count(self) -> int:
        """How many source events this request carries."""
        return len(self.source_events)
