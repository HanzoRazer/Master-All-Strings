"""Immutable contracts for the Musical Spatial Mapping Engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from master_all_strings.core.foundation import (
    JSONScalar,
    JSONValue,
    SpatialMappingError,
    require_finite,
    require_index,
    require_midi_note,
    require_non_empty,
    require_nonnegative,
)

from .enums import OpenStringPolicy, SpatialReferenceType

__all__ = [
    "AuditoryPositionReference",
    "CandidateScore",
    "JSONScalar",
    "JSONValue",
    "MappingConstraints",
    "MappingPreferences",
    "SpatialAnnotation",
    "SpatialPosition",
]


@dataclass(frozen=True)
class MappingConstraints:
    """Hard constraints applied during candidate generation."""

    capo_position: float = 0.0
    maximum_relative_semitone_position: float | None = None
    allowed_string_ids: tuple[str, ...] | None = None
    excluded_string_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_finite(self.capo_position, "capo_position")
        require_nonnegative(self.capo_position, "capo_position")
        if self.maximum_relative_semitone_position is not None:
            require_finite(
                self.maximum_relative_semitone_position,
                "maximum_relative_semitone_position",
            )
            require_nonnegative(
                self.maximum_relative_semitone_position,
                "maximum_relative_semitone_position",
            )
        for group_name, group in (
            ("allowed_string_ids", self.allowed_string_ids),
            ("excluded_string_ids", self.excluded_string_ids),
        ):
            if group is None:
                continue
            for string_id in group:
                require_non_empty(string_id, f"{group_name} entry")
            if len(set(group)) != len(group):
                raise SpatialMappingError(f"{group_name} must not contain duplicate string ids")
        if self.allowed_string_ids is not None:
            overlap = set(self.allowed_string_ids) & set(self.excluded_string_ids)
            if overlap:
                raise SpatialMappingError(
                    f"string ids cannot be both allowed and excluded: {sorted(overlap)}"
                )


@dataclass(frozen=True)
class MappingPreferences:
    """Deterministic preferences reserved for later selection phases."""

    open_string_policy: OpenStringPolicy = OpenStringPolicy.ALLOW
    lower_position_bias: float = 0.0
    preferred_string_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_finite(self.lower_position_bias, "lower_position_bias")
        # Mirror the identifier discipline MappingConstraints applies; without this a
        # blank or duplicated preferred id could enter through the preferences path.
        for string_id in self.preferred_string_ids:
            require_non_empty(string_id, "preferred_string_ids entry")
        if len(set(self.preferred_string_ids)) != len(self.preferred_string_ids):
            raise SpatialMappingError(
                "preferred_string_ids must not contain duplicate string ids",
            )


@dataclass(frozen=True)
class AuditoryPositionReference:
    """Fretless auditory reference information for future practice flows."""

    open_string_midi_note: int
    target_midi_note: int
    interval_semitones: float
    target_cents_offset: float
    interval_label: str | None = None

    def __post_init__(self) -> None:
        require_midi_note(self.open_string_midi_note, "open_string_midi_note")
        require_midi_note(self.target_midi_note, "target_midi_note")
        require_finite(self.interval_semitones, "interval_semitones")
        require_finite(self.target_cents_offset, "target_cents_offset")
        if self.interval_label is not None:
            require_non_empty(self.interval_label, "interval_label")


@dataclass(frozen=True)
class SpatialPosition:
    """A single playable spatial location for a sounding pitch.

    ``display_order`` is copied from the originating :class:`StringProfile` so a
    candidate stays independently interpretable outside the sequence that produced
    it. It is the instrument-defined stable display and enumeration order of the
    candidate's string or course. It is NOT candidate quality, musical ranking,
    pedagogical priority, preference, or ease of performance.

    ``display_order`` is meaningful **only relative to its originating instrument**.
    It is an index into one profile's string list, not a global identifier: a
    ``display_order`` of 0 on a guitar and on a mandolin denote different strings and
    are not comparable. Do not use it to match, cache, or deduplicate positions
    across instruments.

    ``is_open_string`` means **unstopped by a finger**, i.e. sounding at the position
    the string is fretted from -- which a capo redefines. It does NOT mean "at the
    nut" or "fret zero". With a capo at the 3rd fret, an open candidate carries
    ``relative_semitone_position == 0.0`` together with
    ``physical_semitone_position_from_nut == 3.0`` and ``physical_fret_number == 3``.
    A consumer that suppresses fret numbers for open strings will mis-render capoed
    notes; read ``physical_fret_number``/``physical_semitone_position_from_nut`` for
    physical placement and ``is_open_string`` only for stopped-versus-unstopped.
    """

    string_id: str
    course_id: str | None
    display_order: int
    sounding_midi_note: int
    cents_offset: float
    relative_semitone_position: float
    physical_semitone_position_from_nut: float
    physical_fret_number: int | None
    reference_type: SpatialReferenceType
    normalized_position: float
    distance_from_nut_mm: float | None
    is_open_string: bool

    def __post_init__(self) -> None:
        # Normalize the reference type so identity (`is`) checks below cannot be
        # silently bypassed when a raw string reaches this contract. The coercion is
        # wrapped so an invalid value raises the domain error rather than the bare
        # ValueError the enum constructor emits, matching InstrumentProfile.
        try:
            reference_type = SpatialReferenceType(self.reference_type)
        except ValueError as exc:
            raise SpatialMappingError(
                f"invalid reference_type: {self.reference_type!r}",
            ) from exc
        object.__setattr__(self, "reference_type", reference_type)
        require_non_empty(self.string_id, "string_id")
        if self.course_id is not None:
            require_non_empty(self.course_id, "course_id")
        require_index(self.display_order, "display_order")
        require_midi_note(self.sounding_midi_note, "sounding_midi_note")
        require_finite(self.cents_offset, "cents_offset")
        require_finite(self.relative_semitone_position, "relative_semitone_position")
        require_nonnegative(self.relative_semitone_position, "relative_semitone_position")
        require_finite(
            self.physical_semitone_position_from_nut,
            "physical_semitone_position_from_nut",
        )
        require_nonnegative(
            self.physical_semitone_position_from_nut,
            "physical_semitone_position_from_nut",
        )
        require_finite(self.normalized_position, "normalized_position")
        if not 0.0 <= self.normalized_position <= 1.0:
            raise SpatialMappingError("normalized_position must be between 0.0 and 1.0")
        if self.distance_from_nut_mm is not None:
            require_finite(self.distance_from_nut_mm, "distance_from_nut_mm")
            require_nonnegative(self.distance_from_nut_mm, "distance_from_nut_mm")
        if self.is_open_string and self.relative_semitone_position != 0.0:
            raise SpatialMappingError(
                "open-string positions must have a relative semitone position of 0.0",
            )
        if self.relative_semitone_position == 0.0 and not self.is_open_string:
            raise SpatialMappingError(
                "a relative semitone position of 0.0 must be marked is_open_string=True",
            )
        # Validate the fret number itself, not merely its presence: it previously
        # accepted negatives, bools, floats, and strings for PHYSICAL_FRET references.
        if self.physical_fret_number is not None:
            require_index(self.physical_fret_number, "physical_fret_number")
        if (
            self.reference_type is SpatialReferenceType.PHYSICAL_FRET
            and self.physical_fret_number is None
        ):
            raise SpatialMappingError(
                "physical_fret_number is required for physical fret references",
            )
        if (
            self.reference_type is not SpatialReferenceType.PHYSICAL_FRET
            and self.physical_fret_number is not None
        ):
            raise SpatialMappingError(
                "physical_fret_number must be None for non-physical reference types",
            )


@dataclass(frozen=True)
class SpatialAnnotation:
    """Annotation-ready description of a playable spatial location."""

    primary_label: str
    secondary_label: str | None
    pitch_label: str
    string_label: str
    position_label: str
    reference_marker_label: str | None
    accessibility_text: str
    auditory_reference: AuditoryPositionReference | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.primary_label, "primary_label")
        require_non_empty(self.pitch_label, "pitch_label")
        require_non_empty(self.string_label, "string_label")
        require_non_empty(self.position_label, "position_label")
        require_non_empty(self.accessibility_text, "accessibility_text")
        if self.secondary_label is not None:
            require_non_empty(self.secondary_label, "secondary_label")
        if self.reference_marker_label is not None:
            require_non_empty(self.reference_marker_label, "reference_marker_label")


@dataclass(frozen=True)
class CandidateScore:
    """Transparent deterministic score explanation for future selection phases."""

    total: float
    components: Mapping[str, float] = field(default_factory=dict)
    explanation: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_finite(self.total, "total")
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))
        for name, score in self.components.items():
            require_non_empty(name, "components key")
            require_finite(score, f"components[{name!r}]")
        for entry in self.explanation:
            require_non_empty(entry, "explanation entry")
