from __future__ import annotations

import pytest

from master_all_strings.core.spatial_mapping import midi_note_to_pitch_label, semitone_distance


def test_midi_note_to_pitch_label_formats_pitch_names() -> None:
    assert midi_note_to_pitch_label(60) == "C4"
    assert midi_note_to_pitch_label(61, prefer_sharps=False) == "Db4"
    assert midi_note_to_pitch_label(69, cents_offset=3.2) == "A4 +3.2c"


def test_semitone_distance_is_signed() -> None:
    assert semitone_distance(40, 52) == 12
    assert semitone_distance(52, 40) == -12


@pytest.mark.parametrize("value", [-1, 128])
def test_pitch_helpers_reject_invalid_midi_notes(value: int) -> None:
    with pytest.raises(ValueError, match="midi_note|start_midi_note"):
        midi_note_to_pitch_label(value)
