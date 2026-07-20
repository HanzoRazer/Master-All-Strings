from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent


def test_musical_event_accepts_valid_values() -> None:
    event = MusicalEvent(
        event_id="evt-1",
        midi_note=69,
        start_tick=0,
        duration_ticks=480,
        velocity=100,
        cents_offset=2.5,
        voice_id="lead",
    )

    assert event.midi_note == 69
    assert event.voice_id == "lead"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"event_id": "", "midi_note": 69, "start_tick": 0, "duration_ticks": 1}, "event_id"),
     ({"event_id": "x", "midi_note": 128, "start_tick": 0, "duration_ticks": 1}, "midi_note"),
     ({"event_id": "x", "midi_note": 69, "start_tick": -1, "duration_ticks": 1}, "start_tick"),
     ({"event_id": "x", "midi_note": 69, "start_tick": 0, "duration_ticks": 0}, "duration_ticks"),
     ({"event_id": "x", "midi_note": 69, "start_tick": 0, "duration_ticks": 1, "velocity": 200}, "velocity")],
)
def test_musical_event_rejects_invalid_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        MusicalEvent(**kwargs)
