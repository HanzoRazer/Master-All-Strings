"""MVP automatic selection scaffold coverage."""

from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.lesson.auto_select import select_automatic_position
from master_all_strings.lesson.enums import OpenStringPreference
from master_all_strings.lesson.errors import LessonValidationError
from master_all_strings.lesson.resolver import SpatialSelectionRequestV1


def _spatial(
    *,
    open_pref: OpenStringPreference = OpenStringPreference.ALLOW,
    fret_min: int | None = None,
    fret_max: int | None = None,
) -> SpatialSelectionRequestV1:
    return SpatialSelectionRequestV1(
        instrument_profile_id="guitar-standard-6",
        fingering_policy_id="enumeration_v1",
        preferred_fret_min=fret_min,
        preferred_fret_max=fret_max,
        open_string_preference=open_pref,
    )


def test_empty_candidates_rejected() -> None:
    with pytest.raises(LessonValidationError, match="unplayable"):
        select_automatic_position((), spatial=_spatial())


def test_prefer_open_string(guitar_profile) -> None:
    event = MusicalEvent("e", 64, 0, 120)  # E4 — open on string-1
    candidates = generate_candidates(event, guitar_profile)
    selected = select_automatic_position(
        candidates,
        spatial=_spatial(open_pref=OpenStringPreference.PREFER),
    )
    assert selected.is_open_string is True


def test_avoid_and_exclude_open_string(guitar_profile) -> None:
    event = MusicalEvent("e", 64, 0, 120)
    candidates = generate_candidates(event, guitar_profile)
    avoided = select_automatic_position(
        candidates,
        spatial=_spatial(open_pref=OpenStringPreference.AVOID),
    )
    assert avoided.is_open_string is False
    excluded = select_automatic_position(
        candidates,
        spatial=_spatial(open_pref=OpenStringPreference.EXCLUDE),
    )
    assert excluded.is_open_string is False


def test_preferred_fret_region(guitar_profile) -> None:
    event = MusicalEvent("e", 64, 0, 120)
    candidates = generate_candidates(event, guitar_profile)
    selected = select_automatic_position(
        candidates,
        spatial=_spatial(fret_min=4, fret_max=7),
    )
    assert selected.physical_fret_number is not None
    assert 4 <= selected.physical_fret_number <= 7
