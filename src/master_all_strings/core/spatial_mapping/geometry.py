"""Equal-temperament geometry helpers."""

from __future__ import annotations

from .validation import require_finite, require_nonnegative, require_positive

_EQUAL_TEMPERAMENT_DIVISOR = 12.0
_GEOMETRY_TOLERANCE = 1e-9


def geometry_tolerance() -> float:
    """Return the centralized floating-point tolerance used by geometry helpers."""

    return _GEOMETRY_TOLERANCE


def normalized_position_for_semitones(semitone_distance: float) -> float:
    """Return the normalized distance from the nut for an equal-tempered semitone position."""

    require_finite(semitone_distance, "semitone_distance")
    require_nonnegative(semitone_distance, "semitone_distance")
    position = 1.0 - (2.0 ** (-semitone_distance / _EQUAL_TEMPERAMENT_DIVISOR))
    return float(position)


def distance_from_nut_mm(scale_length_mm: float | None, semitone_distance: float) -> float | None:
    """Return the equal-temperament distance from the nut in millimeters."""

    require_finite(semitone_distance, "semitone_distance")
    require_nonnegative(semitone_distance, "semitone_distance")
    if scale_length_mm is None:
        return None
    require_finite(scale_length_mm, "scale_length_mm")
    require_positive(scale_length_mm, "scale_length_mm")
    return scale_length_mm * normalized_position_for_semitones(semitone_distance)
