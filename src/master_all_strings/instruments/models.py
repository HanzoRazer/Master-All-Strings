"""Instrument profile contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from master_all_strings.core.spatial_mapping.enums import FingerboardMode
from master_all_strings.core.spatial_mapping.errors import SpatialMappingError
from master_all_strings.core.spatial_mapping.models import JSONScalar
from master_all_strings.core.spatial_mapping.validation import (
    require_finite,
    require_midi_note,
    require_non_empty,
    require_nonnegative,
    require_positive,
)


@dataclass(frozen=True)
class StringProfile:
    """Immutable description of an instrument string or course representative."""

    string_id: str
    display_label: str
    display_order: int
    open_midi_note: int
    course_id: str | None = None
    enabled: bool = True
    maximum_semitone_position: float | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.string_id, "string_id")
        require_non_empty(self.display_label, "display_label")
        require_midi_note(self.open_midi_note, "open_midi_note")
        if self.display_order < 0:
            raise SpatialMappingError("display_order must be nonnegative")
        if self.maximum_semitone_position is not None:
            require_finite(self.maximum_semitone_position, "maximum_semitone_position")
            require_nonnegative(self.maximum_semitone_position, "maximum_semitone_position")


@dataclass(frozen=True)
class ReferenceMarker:
    """Immutable marker for a semitone-based spatial reference."""

    marker_id: str
    semitone_offset: float
    label: str

    def __post_init__(self) -> None:
        require_non_empty(self.marker_id, "marker_id")
        require_non_empty(self.label, "label")
        require_finite(self.semitone_offset, "semitone_offset")
        require_nonnegative(self.semitone_offset, "semitone_offset")


@dataclass(frozen=True)
class InstrumentProfile:
    """Immutable instrument profile consumed by the mapping engine."""

    schema_version: str
    instrument_id: str
    display_name: str
    family: str
    fingerboard_mode: FingerboardMode
    strings: tuple[StringProfile, ...]
    scale_length_mm: float | None
    physical_fret_count: int | None
    reference_markers: tuple[ReferenceMarker, ...] = ()
    metadata: Mapping[str, JSONScalar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty(self.schema_version, "schema_version")
        require_non_empty(self.instrument_id, "instrument_id")
        require_non_empty(self.display_name, "display_name")
        require_non_empty(self.family, "family")
        if not self.strings:
            raise SpatialMappingError("strings must not be empty")
        string_ids = [string.string_id for string in self.strings]
        if len(set(string_ids)) != len(string_ids):
            raise SpatialMappingError("string_id values must be unique")
        display_orders = [string.display_order for string in self.strings]
        if len(set(display_orders)) != len(display_orders):
            raise SpatialMappingError("display_order values must be unique")
        if self.scale_length_mm is not None:
            require_finite(self.scale_length_mm, "scale_length_mm")
            require_positive(self.scale_length_mm, "scale_length_mm")
        if self.physical_fret_count is not None and self.physical_fret_count < 0:
            raise SpatialMappingError("physical_fret_count must be nonnegative")
        if self.fingerboard_mode is FingerboardMode.FRETTED and self.physical_fret_count is None:
            raise SpatialMappingError("fretted instruments must declare physical_fret_count")
        if (
            self.fingerboard_mode is FingerboardMode.FRETLESS
            and self.physical_fret_count is not None
        ):
            raise SpatialMappingError("fretless instruments must not declare physical_fret_count")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
