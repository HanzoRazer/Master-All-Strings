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
                raise ValueError(f"{group_name} must not contain duplicate string ids")
        if self.allowed_string_ids is not None:
            overlap = set(self.allowed_string_ids) & set(self.excluded_string_ids)
            if overlap:
                raise ValueError(
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


@dataclass(frozen=True)
class SpatialPosition:
    """A single playable spatial location for a sounding pitch."""

    string_id: str
    course_id: str | None
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
        # silently bypassed when a raw string reaches this contract.
        object.__setattr__(self, "reference_type", SpatialReferenceType(self.reference_type))
        require_non_empty(self.string_id, "string_id")
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
            raise ValueError(
                "a relative semitone position of 0.0 must be marked is_open_string=True",
            )
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
