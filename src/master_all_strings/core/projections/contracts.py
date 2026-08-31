"""Canonical projection contracts (DO-013).

These live under Musical Core because governance already says they do:
``ProjectionRequestV1`` and ``ProjectionResultV1`` are registered with
``owning_engine: MUSICAL_CORE``, and ``ProjectionResultV1`` names Core as its
only producer. Putting them in a new top-level package would have created a
second place that looks authoritative about score meaning.

The generic envelope is what governance registered; ``TabProjectionV1`` and
``NotationProjectionV1`` are typed payloads carried inside it, not competing
vocabularies.

Every projection cites a ``canonical_revision_id``. A projection that could not
say which revision it renders would be a picture of nothing in particular.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_identifier,
    require_nonnegative_int,
    require_positive_int,
    require_schema_version,
    require_tuple,
)
from master_all_strings.core.score.meter import MeterChangeV1

__all__ = [
    "DISPLAY_DURATION_QUARTER_FRACTIONS",
    "PROJECTION_SCHEMA_VERSION",
    "DisplayDuration",
    "NotationDisplayPolicy",
    "NotationEventKind",
    "NotationEventV1",
    "NotationMeasureV1",
    "NotationProjectionV1",
    "ProjectionKind",
    "ProjectionRequestV1",
    "ProjectionResultV1",
    "ProjectionUnsupportedFeatureV1",
    "RestDerivation",
    "TabEventStatus",
    "TabEventV1",
    "TabProjectionV1",
    "UnsupportedFeatureCode",
]

PROJECTION_SCHEMA_VERSION = "1.0.0"


class ProjectionKind(StrEnum):
    """Which typed payload a generic request asks for."""

    TAB = "tab"
    NOTATION = "notation"


class TabEventStatus(StrEnum):
    """Whether a canonical note has a playable realization in this projection.

    ``UNRESOLVED`` is not a failure to render; it is the honest answer when
    nothing upstream chose a string and fret. A guess here would be
    indistinguishable from a real fingering decision, and a learner would
    practise it.
    """

    PLAYABLE = "playable"
    UNPLAYABLE = "unplayable"
    UNRESOLVED = "unresolved"


class NotationEventKind(StrEnum):
    NOTE = "note"
    REST = "rest"


class RestDerivation(StrEnum):
    """How a rest came to exist. Rests are projected, never canonical."""

    GLOBAL_SILENCE = "global_silence"


class NotationDisplayPolicy(StrEnum):
    """Named so a reader can tell display spelling from canonical spelling."""

    SHARP_PREFERRED_V1 = "sharp_preferred_v1"


class UnsupportedFeatureCode(StrEnum):
    """Things V1 notation declines to invent.

    Each of these is a place where a plausible-looking guess was available and
    refused. Reporting the refusal keeps the gap visible instead of shipping
    notation that renders cleanly and misstates the music.
    """

    UNSUPPORTED_DISPLAY_DURATION = "unsupported_display_duration"
    TIE_NOT_SUPPORTED = "tie_not_supported"
    VOICE_SPECIFIC_REST_INFERENCE_UNAVAILABLE = (
        "voice_specific_rest_inference_unavailable"
    )


class DisplayDuration(StrEnum):
    """Simple and single-dotted note values. No tuplets, no double dots."""

    WHOLE = "whole"
    DOTTED_WHOLE = "dotted_whole"
    HALF = "half"
    DOTTED_HALF = "dotted_half"
    QUARTER = "quarter"
    DOTTED_QUARTER = "dotted_quarter"
    EIGHTH = "eighth"
    DOTTED_EIGHTH = "dotted_eighth"
    SIXTEENTH = "sixteenth"
    DOTTED_SIXTEENTH = "dotted_sixteenth"
    THIRTY_SECOND = "thirty_second"
    DOTTED_THIRTY_SECOND = "dotted_thirty_second"


#: Each display duration as an exact multiple of one quarter note.
#:
#: Fractions rather than floats: the whole point is that a duration either
#: divides exactly at the current PPQ or is unsupported, and float arithmetic
#: would reintroduce the approximation this policy exists to refuse.
DISPLAY_DURATION_QUARTER_FRACTIONS: dict[DisplayDuration, Fraction] = {
    DisplayDuration.WHOLE: Fraction(4),
    DisplayDuration.DOTTED_WHOLE: Fraction(6),
    DisplayDuration.HALF: Fraction(2),
    DisplayDuration.DOTTED_HALF: Fraction(3),
    DisplayDuration.QUARTER: Fraction(1),
    DisplayDuration.DOTTED_QUARTER: Fraction(3, 2),
    DisplayDuration.EIGHTH: Fraction(1, 2),
    DisplayDuration.DOTTED_EIGHTH: Fraction(3, 4),
    DisplayDuration.SIXTEENTH: Fraction(1, 4),
    DisplayDuration.DOTTED_SIXTEENTH: Fraction(3, 8),
    DisplayDuration.THIRTY_SECOND: Fraction(1, 8),
    DisplayDuration.DOTTED_THIRTY_SECOND: Fraction(3, 16),
}


def _coerce(enum_cls: type[StrEnum], value: object, field_name: str) -> StrEnum:
    if isinstance(value, enum_cls):
        return value
    if not isinstance(value, str):
        raise ScoreContractError(f"invalid {field_name}: {value!r}")
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ScoreContractError(f"invalid {field_name}: {value!r}") from exc


def _require_midi_note(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoreContractError(f"{field_name} must be an integer MIDI note")
    if not 0 <= value <= 127:
        raise ScoreContractError(f"{field_name} must be between 0 and 127")


@dataclass(frozen=True)
class ProjectionUnsupportedFeatureV1:
    """One thing the projection declined to represent, and where.

    ``canonical_event_id`` is optional because some refusals are about a span
    rather than an event -- a rest that would need voice allocation belongs to no
    single note.
    """

    schema_version: str
    code: UnsupportedFeatureCode
    detail: str
    canonical_event_id: str | None = None
    start_tick: int | None = None

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        object.__setattr__(self, "code", _coerce(UnsupportedFeatureCode, self.code, "code"))
        require_identifier(self.detail, "detail")
        if self.canonical_event_id is not None:
            require_identifier(self.canonical_event_id, "canonical_event_id")
        if self.start_tick is not None:
            require_nonnegative_int(self.start_tick, "start_tick")


@dataclass(frozen=True)
class TabEventV1:
    """One canonical note as TAB, or an explicit statement that it is not.

    Spatial fields are present only for ``PLAYABLE``. An ``UNPLAYABLE`` or
    ``UNRESOLVED`` row carrying a string and fret would be a fingering nobody
    chose.
    """

    schema_version: str
    canonical_event_id: str
    start_tick: int
    duration_ticks: int
    midi_note: int
    status: TabEventStatus
    string_id: str | None = None
    fret: int | None = None
    cents_offset: float | None = None

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.canonical_event_id, "canonical_event_id")
        require_nonnegative_int(self.start_tick, "start_tick")
        require_positive_int(self.duration_ticks, "duration_ticks")
        _require_midi_note(self.midi_note, "midi_note")
        object.__setattr__(self, "status", _coerce(TabEventStatus, self.status, "status"))

        spatial = (self.string_id, self.fret)
        if self.status is TabEventStatus.PLAYABLE:
            if any(value is None for value in spatial):
                raise ScoreContractError("a playable TAB event requires string_id and fret")
            require_identifier(self.string_id, "string_id")  # type: ignore[arg-type]
            require_nonnegative_int(self.fret, "fret")  # type: ignore[arg-type]
        elif any(value is not None for value in spatial):
            raise ScoreContractError(
                f"a {self.status.value} TAB event must not carry a string or fret"
            )
        if self.cents_offset is not None and not isinstance(self.cents_offset, (int, float)):
            raise ScoreContractError("cents_offset must be a number when present")


@dataclass(frozen=True)
class TabProjectionV1:
    """Guitar TAB for one canonical revision under one instrument profile."""

    schema_version: str
    canonical_revision_id: str
    instrument_profile_id: str
    events: tuple[TabEventV1, ...]
    unsupported_features: tuple[ProjectionUnsupportedFeatureV1, ...] = ()

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        require_identifier(self.instrument_profile_id, "instrument_profile_id")
        require_tuple(self.events, "events")
        require_tuple(self.unsupported_features, "unsupported_features")
        ids = [event.canonical_event_id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ScoreContractError("TAB events must carry unique canonical_event_id values")
        previous = -1
        for event in self.events:
            if event.start_tick < previous:
                raise ScoreContractError("TAB events must be ordered by start_tick")
            previous = event.start_tick


@dataclass(frozen=True)
class NotationEventV1:
    """A note or a projected rest inside one measure.

    A rest has no ``canonical_event_id`` because no canonical event exists for
    it: silence is derived, not stored. That absence is deliberate and explicit
    rather than an empty string standing in for an identity.
    """

    schema_version: str
    event_kind: NotationEventKind
    start_tick: int
    duration_ticks: int
    canonical_event_id: str | None = None
    midi_note: int | None = None
    display_pitch: str | None = None
    display_duration: DisplayDuration | None = None
    derivation: RestDerivation | None = None

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        object.__setattr__(
            self, "event_kind", _coerce(NotationEventKind, self.event_kind, "event_kind")
        )
        require_nonnegative_int(self.start_tick, "start_tick")
        require_positive_int(self.duration_ticks, "duration_ticks")
        if self.display_duration is not None:
            object.__setattr__(
                self,
                "display_duration",
                _coerce(DisplayDuration, self.display_duration, "display_duration"),
            )

        if self.event_kind is NotationEventKind.NOTE:
            if self.canonical_event_id is None:
                raise ScoreContractError("a notated note requires its canonical_event_id")
            require_identifier(self.canonical_event_id, "canonical_event_id")
            if self.midi_note is None:
                raise ScoreContractError("a notated note requires midi_note")
            _require_midi_note(self.midi_note, "midi_note")
            require_identifier(self.display_pitch, "display_pitch")  # type: ignore[arg-type]
            if self.derivation is not None:
                raise ScoreContractError("a note is not derived; derivation belongs to rests")
            return

        # Rest.
        if self.canonical_event_id is not None:
            raise ScoreContractError(
                "a rest is projection-derived and must not cite a canonical event"
            )
        if self.midi_note is not None or self.display_pitch is not None:
            raise ScoreContractError("a rest has no pitch")
        object.__setattr__(
            self, "derivation", _coerce(RestDerivation, self.derivation, "derivation")
        )


@dataclass(frozen=True)
class NotationMeasureV1:
    """One measure: its span, the meter in force, and what sounds inside it."""

    schema_version: str
    measure_index: int
    start_tick: int
    end_tick: int
    meter: MeterChangeV1
    events: tuple[NotationEventV1, ...] = ()

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_nonnegative_int(self.measure_index, "measure_index")
        require_nonnegative_int(self.start_tick, "start_tick")
        require_positive_int(self.end_tick, "end_tick")
        if self.end_tick <= self.start_tick:
            raise ScoreContractError("end_tick must exceed start_tick")
        if not isinstance(self.meter, MeterChangeV1):
            raise ScoreContractError("meter must be a MeterChangeV1")
        require_tuple(self.events, "events")
        previous = -1
        for event in self.events:
            if event.start_tick < previous:
                raise ScoreContractError("measure events must be ordered by start_tick")
            previous = event.start_tick


@dataclass(frozen=True)
class NotationProjectionV1:
    """Standard notation for one canonical revision.

    Carries no instrument profile: notation of a melody is the same notation
    whichever way it is fingered.
    """

    schema_version: str
    canonical_revision_id: str
    ticks_per_quarter: int
    display_policy: NotationDisplayPolicy
    measures: tuple[NotationMeasureV1, ...]
    unsupported_features: tuple[ProjectionUnsupportedFeatureV1, ...] = ()

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        require_positive_int(self.ticks_per_quarter, "ticks_per_quarter")
        object.__setattr__(
            self,
            "display_policy",
            _coerce(NotationDisplayPolicy, self.display_policy, "display_policy"),
        )
        require_tuple(self.measures, "measures")
        require_tuple(self.unsupported_features, "unsupported_features")
        for index, measure in enumerate(self.measures):
            if measure.measure_index != index:
                raise ScoreContractError(
                    "measures must be contiguous and zero-indexed in order"
                )


@dataclass(frozen=True)
class ProjectionRequestV1:
    """Ask Musical Core to project an existing revision.

    Carries no projection identity and no payload: a request states what the
    caller wants rendered, and Core answers. A request able to name its own
    result would let a caller assert a projection it never computed.
    """

    schema_version: str
    request_id: str
    canonical_revision_id: str
    projection_kind: ProjectionKind
    instrument_profile_id: str | None = None
    options: tuple[tuple[str, str], ...] = ()

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.request_id, "request_id")
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        object.__setattr__(
            self,
            "projection_kind",
            _coerce(ProjectionKind, self.projection_kind, "projection_kind"),
        )
        if self.instrument_profile_id is not None:
            require_identifier(self.instrument_profile_id, "instrument_profile_id")
        require_tuple(self.options, "options")
        # TAB is realized on an instrument; notation is not. Requiring the profile
        # here means a TAB request cannot reach a builder without one.
        if (
            self.projection_kind is ProjectionKind.TAB
            and self.instrument_profile_id is None
        ):
            raise ScoreContractError("a TAB request requires an instrument_profile_id")


@dataclass(frozen=True)
class ProjectionResultV1:
    """The registered envelope carrying one typed projection payload."""

    schema_version: str
    projection_id: str
    canonical_revision_id: str
    projection_kind: ProjectionKind
    payload: TabProjectionV1 | NotationProjectionV1
    digest: str
    unsupported_features: tuple[ProjectionUnsupportedFeatureV1, ...] = ()

    SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.projection_id, "projection_id")
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        require_identifier(self.digest, "digest")
        object.__setattr__(
            self,
            "projection_kind",
            _coerce(ProjectionKind, self.projection_kind, "projection_kind"),
        )
        require_tuple(self.unsupported_features, "unsupported_features")

        expected = {
            ProjectionKind.TAB: TabProjectionV1,
            ProjectionKind.NOTATION: NotationProjectionV1,
        }[self.projection_kind]
        if not isinstance(self.payload, expected):
            raise ScoreContractError(
                f"projection_kind {self.projection_kind.value} requires a "
                f"{expected.__name__} payload"
            )
        # An envelope and its payload disagreeing about which revision was
        # rendered is the one inconsistency that would make the citation useless.
        if self.payload.canonical_revision_id != self.canonical_revision_id:
            raise ScoreContractError(
                "envelope and payload must cite the same canonical_revision_id"
            )
