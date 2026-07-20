"""Pitch-formatting and semitone helpers."""

from __future__ import annotations

from .validation import require_finite, require_midi_note

_SHARP_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_PITCH_CLASSES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def midi_note_to_pitch_label(
    midi_note: int,
    *,
    cents_offset: float = 0.0,
    prefer_sharps: bool = True,
) -> str:
    """Format a MIDI pitch label with optional cents offset."""

    require_midi_note(midi_note, "midi_note")
    require_finite(cents_offset, "cents_offset")
    pitch_classes = _SHARP_PITCH_CLASSES if prefer_sharps else _FLAT_PITCH_CLASSES
    octave = (midi_note // 12) - 1
    pitch_class = pitch_classes[midi_note % 12]
    if cents_offset == 0:
        return f"{pitch_class}{octave}"
    return f"{pitch_class}{octave} {cents_offset:+.1f}c"


def semitone_distance(start_midi_note: int, target_midi_note: int) -> int:
    """Return the signed semitone distance between two MIDI notes."""

    require_midi_note(start_midi_note, "start_midi_note")
    require_midi_note(target_midi_note, "target_midi_note")
    return target_midi_note - start_midi_note
