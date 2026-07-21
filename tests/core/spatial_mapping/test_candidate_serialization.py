"""Locks the serialized SpatialPosition shape.

``to_serializable_dict`` is generic over dataclass fields, so adding
``display_order`` to the contract changed every serialized payload automatically.
That change is intended and authorized, but it was previously unguarded: nothing
asserted the emitted key set, so a future field addition or removal would silently
alter the wire shape again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import (
    generate_candidates,
    instrument_profile_from_mapping,
    to_serializable_dict,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "resources" / "instruments" / "examples"

EXPECTED_KEYS = [
    "string_id",
    "course_id",
    "display_order",
    "sounding_midi_note",
    "cents_offset",
    "relative_semitone_position",
    "physical_semitone_position_from_nut",
    "physical_fret_number",
    "reference_type",
    "normalized_position",
    "distance_from_nut_mm",
    "is_open_string",
]


def _candidate() -> Any:
    profile = instrument_profile_from_mapping(
        json.loads((EXAMPLES / "guitar-standard-6.json").read_text(encoding="utf-8"))
    )
    event = MusicalEvent(event_id="e", midi_note=64, start_tick=0, duration_ticks=480)
    return generate_candidates(event, profile)[0]


def test_serialized_key_set_and_order_are_pinned() -> None:
    assert list(to_serializable_dict(_candidate())) == EXPECTED_KEYS


def test_display_order_is_part_of_the_serialized_contract() -> None:
    payload = to_serializable_dict(_candidate())
    assert payload["display_order"] == 1
    assert isinstance(payload["display_order"], int)


def test_payload_survives_a_json_round_trip() -> None:
    """reference_type is a StrEnum, so it must degrade to a plain string in JSON."""
    payload = to_serializable_dict(_candidate())
    restored = json.loads(json.dumps(payload))
    assert restored["reference_type"] == "physical_fret"
    assert type(restored["reference_type"]) is str
    assert restored == {**payload, "reference_type": "physical_fret"}


def test_no_renderer_or_selection_fields_leak_into_the_payload() -> None:
    payload = to_serializable_dict(_candidate())
    forbidden = {"score", "rank", "selected", "x", "y", "pixel_x", "pixel_y"}
    assert not set(payload) & forbidden
