"""Enumerations used by the Musical Spatial Mapping Engine.

``FingerboardMode`` is a cross-cutting instrument concept and lives in the
dependency-neutral ``core.foundation`` module; it is re-exported here so existing
``from .enums import FingerboardMode`` call sites keep working. The remaining enums
are spatial-mapping-specific and defined locally.
"""

from __future__ import annotations

from enum import StrEnum

from master_all_strings.core.foundation import FingerboardMode

__all__ = [
    "CandidateRejectionCode",
    "FingerboardMode",
    "OpenStringPolicy",
    "SelectionStatus",
    "SpatialReferenceType",
]


class SpatialReferenceType(StrEnum):
    """Coordinate reference semantics for a spatial position."""

    PHYSICAL_FRET = "physical_fret"
    IMAGINARY_SEMITONE = "imaginary_semitone"
    CONTINUOUS_POSITION = "continuous_position"


class OpenStringPolicy(StrEnum):
    """Deterministic open-string preference policy."""

    ALLOW = "allow"
    PREFER = "prefer"
    AVOID = "avoid"
    EXCLUDE = "exclude"


class SelectionStatus(StrEnum):
    """Selection result status."""

    SELECTED = "selected"
    AMBIGUOUS = "ambiguous"
    UNPLAYABLE = "unplayable"


class CandidateRejectionCode(StrEnum):
    """Stable rejection codes for excluded or invalid candidates."""

    STRING_DISABLED = "string_disabled"
    BELOW_OPEN_PITCH = "below_open_pitch"
    ABOVE_MAXIMUM_POSITION = "above_maximum_position"
    OPEN_STRING_EXCLUDED = "open_string_excluded"
    INVALID_REFERENCE = "invalid_reference"
