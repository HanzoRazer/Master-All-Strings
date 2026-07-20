"""Enumerations used by the Musical Spatial Mapping Engine."""

from __future__ import annotations

from enum import Enum


class FingerboardMode(str, Enum):
    """Supported fingerboard semantics."""

    FRETTED = "fretted"
    FRETLESS = "fretless"
    HYBRID = "hybrid"


class SpatialReferenceType(str, Enum):
    """Coordinate reference semantics for a spatial position."""

    PHYSICAL_FRET = "physical_fret"
    IMAGINARY_SEMITONE = "imaginary_semitone"
    CONTINUOUS_POSITION = "continuous_position"


class OpenStringPolicy(str, Enum):
    """Deterministic open-string preference policy."""

    ALLOW = "allow"
    PREFER = "prefer"
    AVOID = "avoid"
    EXCLUDE = "exclude"


class SelectionStatus(str, Enum):
    """Selection result status."""

    SELECTED = "selected"
    AMBIGUOUS = "ambiguous"
    UNPLAYABLE = "unplayable"


class CandidateRejectionCode(str, Enum):
    """Stable rejection codes for excluded or invalid candidates."""

    STRING_DISABLED = "string_disabled"
    BELOW_OPEN_PITCH = "below_open_pitch"
    ABOVE_MAXIMUM_POSITION = "above_maximum_position"
    OPEN_STRING_EXCLUDED = "open_string_excluded"
    INVALID_REFERENCE = "invalid_reference"
