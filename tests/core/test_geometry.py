from __future__ import annotations

import math

import pytest

from master_all_strings.core.spatial_mapping import (
    distance_from_nut_mm,
    geometry_tolerance,
    normalized_position_for_semitones,
)


def test_normalized_position_for_octave_matches_half_scale() -> None:
    assert normalized_position_for_semitones(12.0) == pytest.approx(0.5)


def test_distance_from_nut_supports_fractional_positions() -> None:
    expected = 648.0 * (1 - 2 ** (-1.5 / 12))
    assert distance_from_nut_mm(648.0, 1.5) == pytest.approx(expected)


def test_distance_from_nut_returns_none_when_scale_length_is_unknown() -> None:
    assert distance_from_nut_mm(None, 7.0) is None


def test_geometry_rejects_negative_positions() -> None:
    with pytest.raises(ValueError, match="semitone_distance"):
        normalized_position_for_semitones(-0.1)


def test_geometry_tolerance_is_small_and_centralized() -> None:
    assert math.isclose(geometry_tolerance(), 1e-9)
