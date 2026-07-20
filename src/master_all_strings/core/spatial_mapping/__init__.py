"""Public contracts and utilities for the Musical Spatial Mapping Engine."""

from .enums import (
    CandidateRejectionCode,
    FingerboardMode,
    OpenStringPolicy,
    SelectionStatus,
    SpatialReferenceType,
)
from .errors import SpatialMappingError
from .geometry import distance_from_nut_mm, geometry_tolerance, normalized_position_for_semitones
from .models import (
    AuditoryPositionReference,
    CandidateScore,
    JSONScalar,
    MappingConstraints,
    MappingPreferences,
    SpatialAnnotation,
    SpatialPosition,
)
from .pitch import midi_note_to_pitch_label, semitone_distance
from .serialization import instrument_profile_from_mapping, to_serializable_dict

__all__ = [
    "AuditoryPositionReference",
    "CandidateRejectionCode",
    "CandidateScore",
    "FingerboardMode",
    "JSONScalar",
    "MappingConstraints",
    "MappingPreferences",
    "OpenStringPolicy",
    "SelectionStatus",
    "SpatialAnnotation",
    "SpatialMappingError",
    "SpatialPosition",
    "SpatialReferenceType",
    "distance_from_nut_mm",
    "geometry_tolerance",
    "instrument_profile_from_mapping",
    "midi_note_to_pitch_label",
    "normalized_position_for_semitones",
    "semitone_distance",
    "to_serializable_dict",
]
