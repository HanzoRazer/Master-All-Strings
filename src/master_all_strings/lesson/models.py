"""Frozen LessonAssignmentV1 contracts.

Educational Engine owns instructional intent and portability. Canonical musical
truth remains Musical Core after resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from master_all_strings.core.foundation import (
    require_finite,
    require_index,
    require_midi_note,
    require_non_empty,
    require_positive,
)

from .enums import (
    AssessmentMode,
    LessonContentFormat,
    LessonSourceType,
    OpenStringPreference,
)
from .errors import LessonSchemaError, LessonValidationError

__all__ = [
    "LESSON_ASSIGNMENT_SCHEMA_ID",
    "LESSON_ASSIGNMENT_SCHEMA_VERSION",
    "LessonAssessmentV1",
    "LessonAssignmentV1",
    "LessonIdentityV1",
    "LessonInstructionV1",
    "LessonMusicalContentV1",
    "LessonPlaybackPolicyV1",
    "LessonProvenanceV1",
    "LessonRoutingV1",
    "LessonSpatialGuidanceV1",
    "SerializedCanonicalEventV1",
    "SerializedMeterChangeV1",
    "SerializedTempoChangeV1",
    "TeacherOverrideV1",
]

LESSON_ASSIGNMENT_SCHEMA_ID = "master_all_strings.lesson_assignment"
LESSON_ASSIGNMENT_SCHEMA_VERSION = "1.0.0"


def _coerce_enum(enum_cls: type, value: object, field_name: str) -> object:
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise LessonValidationError(
            f"invalid {field_name}: {value!r}",
            code=f"invalid_{field_name}",
        ) from exc


@dataclass(frozen=True)
class SerializedCanonicalEventV1:
    """Serialized canonical-event representation that resolves 1:1 into MusicalEvent."""

    event_id: str
    midi_note: int
    start_tick: int
    duration_ticks: int
    velocity: int = 64
    cents_offset: float = 0.0
    voice_id: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.event_id, "event_id")
        require_midi_note(self.midi_note, "midi_note")
        require_index(self.start_tick, "start_tick")
        if isinstance(self.duration_ticks, bool) or not isinstance(self.duration_ticks, int):
            raise LessonValidationError(
                "duration_ticks must be an integer",
                code="malformed_timing",
            )
        if self.duration_ticks <= 0:
            raise LessonValidationError(
                "duration_ticks must be positive",
                code="malformed_timing",
            )
        if (
            isinstance(self.velocity, bool)
            or not isinstance(self.velocity, int)
            or not 0 <= self.velocity <= 127
        ):
            raise LessonValidationError(
                "velocity must be an integer between 0 and 127",
                code="invalid_velocity",
            )
        require_finite(self.cents_offset, "cents_offset")
        if self.voice_id is not None:
            require_non_empty(self.voice_id, "voice_id")


@dataclass(frozen=True)
class SerializedTempoChangeV1:
    """A tempo change expressed in microseconds-per-quarter and tick position."""

    tick: int
    tempo_bpm: float

    def __post_init__(self) -> None:
        require_index(self.tick, "tick")
        require_finite(self.tempo_bpm, "tempo_bpm")
        if not 1.0 <= self.tempo_bpm <= 400.0:
            raise LessonValidationError(
                "tempo_bpm must be between 1 and 400",
                code="invalid_tempo",
            )


@dataclass(frozen=True)
class SerializedMeterChangeV1:
    """A meter change at a tick position."""

    tick: int
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        require_index(self.tick, "tick")
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise LessonValidationError("numerator must be an integer", code="invalid_meter")
        if self.numerator <= 0:
            raise LessonValidationError("numerator must be positive", code="invalid_meter")
        if self.denominator not in (1, 2, 4, 8, 16, 32):
            raise LessonValidationError(
                "denominator must be a standard note value",
                code="invalid_meter",
            )


@dataclass(frozen=True)
class LessonIdentityV1:
    """Assignment versus content identity."""

    assignment_id: str
    content_id: str
    title: str
    description: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.assignment_id, "assignment_id")
        require_non_empty(self.content_id, "content_id")
        require_non_empty(self.title, "title")
        if self.description is not None:
            require_non_empty(self.description, "description")


@dataclass(frozen=True)
class LessonMusicalContentV1:
    """Portable musical content embedded for MVP-1."""

    format: LessonContentFormat
    ticks_per_quarter: int
    events: tuple[SerializedCanonicalEventV1, ...]
    tempo_changes: tuple[SerializedTempoChangeV1, ...] = ()
    meter_changes: tuple[SerializedMeterChangeV1, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "format", _coerce_enum(LessonContentFormat, self.format, "format"))
        if isinstance(self.ticks_per_quarter, bool) or not isinstance(self.ticks_per_quarter, int):
            raise LessonValidationError(
                "ticks_per_quarter must be an integer",
                code="invalid_ppq",
            )
        if self.ticks_per_quarter <= 0:
            raise LessonValidationError(
                "ticks_per_quarter must be positive",
                code="invalid_ppq",
            )
        if not isinstance(self.events, tuple):
            raise LessonValidationError("events must be a tuple", code="invalid_events")
        if not self.events:
            raise LessonValidationError(
                "musical content must include at least one event",
                code="missing_content",
            )
        ids = [event.event_id for event in self.events]
        if len(set(ids)) != len(ids):
            raise LessonValidationError(
                "duplicate event_id values are not allowed",
                code="duplicate_event_id",
            )


@dataclass(frozen=True)
class LessonPlaybackPolicyV1:
    """Playback requests; transport owns execution."""

    tempo_override: float | None = None
    start_tick: int | None = None
    end_tick: int | None = None
    loop_enabled: bool = False
    count_in_bars: int | None = None

    def __post_init__(self) -> None:
        if self.tempo_override is not None:
            require_finite(self.tempo_override, "tempo_override")
            if not 1.0 <= self.tempo_override <= 400.0:
                raise LessonValidationError(
                    "tempo_override must be between 1 and 400",
                    code="invalid_tempo",
                )
        if self.start_tick is not None:
            require_index(self.start_tick, "start_tick")
        if self.end_tick is not None:
            require_index(self.end_tick, "end_tick")
        if not isinstance(self.loop_enabled, bool):
            raise LessonValidationError(
                "loop_enabled must be a boolean",
                code="invalid_loop_range",
            )
        if (
            self.start_tick is not None
            and self.end_tick is not None
            and self.end_tick <= self.start_tick
        ):
            raise LessonValidationError(
                "end_tick must be greater than start_tick",
                code="invalid_loop_range",
            )
        if self.loop_enabled and (self.start_tick is None or self.end_tick is None):
            raise LessonValidationError(
                "loop_enabled requires start_tick and end_tick",
                code="invalid_loop_range",
            )
        if self.count_in_bars is not None:
            require_index(self.count_in_bars, "count_in_bars")


@dataclass(frozen=True)
class LessonSpatialGuidanceV1:
    """Instructional spatial intent; MSME/selector derive positions."""

    instrument_profile_id: str
    fingering_policy_id: str
    preferred_fret_min: int | None = None
    preferred_fret_max: int | None = None
    open_string_preference: OpenStringPreference = OpenStringPreference.ALLOW

    def __post_init__(self) -> None:
        require_non_empty(self.instrument_profile_id, "instrument_profile_id")
        require_non_empty(self.fingering_policy_id, "fingering_policy_id")
        object.__setattr__(
            self,
            "open_string_preference",
            _coerce_enum(
                OpenStringPreference,
                self.open_string_preference,
                "open_string_preference",
            ),
        )
        if self.preferred_fret_min is not None:
            require_index(self.preferred_fret_min, "preferred_fret_min")
        if self.preferred_fret_max is not None:
            require_index(self.preferred_fret_max, "preferred_fret_max")
        if (
            self.preferred_fret_min is not None
            and self.preferred_fret_max is not None
            and self.preferred_fret_max < self.preferred_fret_min
        ):
            raise LessonValidationError(
                "preferred_fret_max must be >= preferred_fret_min",
                code="invalid_fret_region",
            )


@dataclass(frozen=True)
class TeacherOverrideV1:
    """Hard instructional location after physical validity succeeds."""

    event_id: str
    string_id: str
    physical_fret_number: int
    reason: str | None = None
    teacher_note: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.event_id, "event_id")
        require_non_empty(self.string_id, "string_id")
        require_index(self.physical_fret_number, "physical_fret_number")
        if self.reason is not None:
            require_non_empty(self.reason, "reason")
        if self.teacher_note is not None:
            require_non_empty(self.teacher_note, "teacher_note")


@dataclass(frozen=True)
class LessonInstructionV1:
    """Preserve-only instructional metadata for future curriculum stages."""

    objective: str | None = None
    repetitions: int | None = None
    difficulty: str | None = None
    curriculum_ref: str | None = None
    teacher_note: str | None = None

    def __post_init__(self) -> None:
        if self.objective is not None:
            require_non_empty(self.objective, "objective")
        if self.repetitions is not None:
            if isinstance(self.repetitions, bool) or not isinstance(self.repetitions, int):
                raise LessonValidationError(
                    "repetitions must be an integer",
                    code="invalid_instruction",
                )
            require_positive(self.repetitions, "repetitions")
        if self.difficulty is not None:
            require_non_empty(self.difficulty, "difficulty")
        if self.curriculum_ref is not None:
            require_non_empty(self.curriculum_ref, "curriculum_ref")
        if self.teacher_note is not None:
            require_non_empty(self.teacher_note, "teacher_note")


@dataclass(frozen=True)
class LessonAssessmentV1:
    """Preserve-only assessment metadata; no scoring engine in this tranche."""

    enabled: bool = False
    mode: AssessmentMode = AssessmentMode.DISABLED
    note_accuracy_required: float | None = None
    timing_tolerance_ms: int | None = None
    required_successful_repetitions: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise LessonValidationError("enabled must be a boolean", code="invalid_assessment")
        object.__setattr__(self, "mode", _coerce_enum(AssessmentMode, self.mode, "mode"))
        if self.note_accuracy_required is not None:
            require_finite(self.note_accuracy_required, "note_accuracy_required")
            if not 0.0 <= self.note_accuracy_required <= 1.0:
                raise LessonValidationError(
                    "note_accuracy_required must be between 0 and 1",
                    code="invalid_assessment",
                )
        if self.timing_tolerance_ms is not None:
            require_index(self.timing_tolerance_ms, "timing_tolerance_ms")
        if self.required_successful_repetitions is not None:
            if isinstance(self.required_successful_repetitions, bool) or not isinstance(
                self.required_successful_repetitions, int
            ):
                raise LessonValidationError(
                    "required_successful_repetitions must be an integer",
                    code="invalid_assessment",
                )
            if self.required_successful_repetitions <= 0:
                raise LessonValidationError(
                    "required_successful_repetitions must be positive",
                    code="invalid_assessment",
                )


@dataclass(frozen=True)
class LessonProvenanceV1:
    """Creation provenance without requiring future account identity."""

    created_by: str
    created_at_utc: str
    source_type: LessonSourceType
    source_name: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.created_by, "created_by")
        require_non_empty(self.created_at_utc, "created_at_utc")
        object.__setattr__(
            self,
            "source_type",
            _coerce_enum(LessonSourceType, self.source_type, "source_type"),
        )
        if self.source_name is not None:
            require_non_empty(self.source_name, "source_name")
            if _looks_like_absolute_path(self.source_name):
                raise LessonValidationError(
                    "portable assignments must not depend on absolute paths",
                    code="absolute_path_dependency",
                )


@dataclass(frozen=True)
class LessonRoutingV1:
    """Semantically inert future routing metadata."""

    sender_device_id: str | None = None
    recipient_device_id: str | None = None
    classroom_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("sender_device_id", "recipient_device_id", "classroom_id"):
            value = getattr(self, name)
            if value is not None:
                require_non_empty(value, name)


@dataclass(frozen=True)
class LessonAssignmentV1:
    """Portable, versioned lesson-entry envelope for MVP-1."""

    schema_id: str
    schema_version: str
    identity: LessonIdentityV1
    musical_content: LessonMusicalContentV1
    playback: LessonPlaybackPolicyV1
    spatial_guidance: LessonSpatialGuidanceV1
    teacher_overrides: tuple[TeacherOverrideV1, ...] = ()
    instruction: LessonInstructionV1 = field(default_factory=LessonInstructionV1)
    assessment: LessonAssessmentV1 = field(default_factory=LessonAssessmentV1)
    provenance: LessonProvenanceV1 = field(
        default_factory=lambda: LessonProvenanceV1(
            created_by="system",
            created_at_utc="1970-01-01T00:00:00Z",
            source_type=LessonSourceType.UNKNOWN,
        )
    )
    routing: LessonRoutingV1 | None = None

    # Convenience identity mirrors for callers that expect top-level fields.
    @property
    def assignment_id(self) -> str:
        return self.identity.assignment_id

    @property
    def content_id(self) -> str:
        return self.identity.content_id

    @property
    def title(self) -> str:
        return self.identity.title

    def __post_init__(self) -> None:
        require_non_empty(self.schema_id, "schema_id")
        require_non_empty(self.schema_version, "schema_version")
        if self.schema_id != LESSON_ASSIGNMENT_SCHEMA_ID:
            raise LessonSchemaError(
                f"unsupported schema_id: {self.schema_id!r}",
                code="unsupported_schema",
            )
        major = self.schema_version.split(".", 1)[0]
        expected_major = LESSON_ASSIGNMENT_SCHEMA_VERSION.split(".", 1)[0]
        if major != expected_major:
            raise LessonSchemaError(
                f"unsupported schema_version: {self.schema_version!r}",
                code="unsupported_schema",
            )
        if self.schema_version != LESSON_ASSIGNMENT_SCHEMA_VERSION:
            raise LessonSchemaError(
                f"unsupported schema_version: {self.schema_version!r}",
                code="unsupported_schema",
            )
        if not isinstance(self.teacher_overrides, tuple):
            raise LessonValidationError(
                "teacher_overrides must be a tuple",
                code="invalid_overrides",
            )
        override_events = [item.event_id for item in self.teacher_overrides]
        if len(set(override_events)) != len(override_events):
            raise LessonValidationError(
                "duplicate teacher overrides for the same event_id",
                code="duplicate_override",
            )


def _looks_like_absolute_path(value: str) -> bool:
    if value.startswith("/") or value.startswith("\\\\"):
        return True
    if len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/"):
        return True
    return False
