from __future__ import annotations

from helpers import T1, make_event

from master_all_strings.performance.capture_normalization import close_capture
from master_all_strings.performance.contracts.capture import MidiEventType
from master_all_strings.performance.contracts.live_midi import ObservedMidiNoteStatus
from master_all_strings.performance.note_pairing import pair_midi_notes


def _pair(open_capture, events):  # type: ignore[no-untyped-def]
    capture = close_capture(
        open_capture.__class__(
            **{
                **open_capture.__dict__,
                "events": tuple(events),
            }
        ),
        ended_at=T1,
    )
    return pair_midi_notes(capture, observed_id_factory=lambda index: f"observed-{index}")


def test_simple_and_velocity_zero_note_off_pair(open_capture) -> None:  # type: ignore[no-untyped-def]
    result = _pair(
        open_capture,
        (
            make_event(0, MidiEventType.NOTE_ON, note=60, velocity=90),
            make_event(1, MidiEventType.NOTE_ON, note=60, velocity=0),
        ),
    )
    assert len(result.observed_notes) == 1
    assert result.observed_notes[0].status is ObservedMidiNoteStatus.COMPLETE


def test_overlapping_repeated_pitch_pairs_fifo(open_capture) -> None:  # type: ignore[no-untyped-def]
    result = _pair(
        open_capture,
        (
            make_event(0, time_ns=0, note=60),
            make_event(1, time_ns=10, note=60),
            make_event(2, MidiEventType.NOTE_OFF, time_ns=20, note=60, velocity=0),
            make_event(3, MidiEventType.NOTE_OFF, time_ns=30, note=60, velocity=0),
        ),
    )
    assert [(n.note_on_time_ns, n.note_off_time_ns) for n in result.observed_notes] == [
        (0, 20),
        (10, 30),
    ]


def test_channels_and_devices_are_independent(open_capture) -> None:  # type: ignore[no-untyped-def]
    events = (
        make_event(0, time_ns=0, note=60, channel=0),
        make_event(1, time_ns=1, note=60, channel=1),
        make_event(2, MidiEventType.NOTE_OFF, time_ns=2, note=60, velocity=0, channel=1),
        make_event(3, MidiEventType.NOTE_OFF, time_ns=3, note=60, velocity=0, channel=0),
    )
    result = _pair(open_capture, events)
    assert [(n.channel, n.duration_ns) for n in result.observed_notes] == [(0, 3), (1, 1)]


def test_unmatched_on_and_off_are_both_preserved(open_capture) -> None:  # type: ignore[no-untyped-def]
    result = _pair(
        open_capture,
        (
            make_event(0, MidiEventType.NOTE_OFF, note=61, velocity=0),
            make_event(1, MidiEventType.NOTE_ON, note=62, velocity=90),
        ),
    )
    assert result.observed_notes[0].status is ObservedMidiNoteStatus.UNMATCHED_NOTE_ON
    assert result.unmatched_note_offs[0].midi_note == 61


def test_repetition_index_is_captured_at_note_on(open_capture) -> None:  # type: ignore[no-untyped-def]
    capture = close_capture(
        open_capture.__class__(
            **{
                **open_capture.__dict__,
                "events": (
                    make_event(0, time_ns=1_000, note=60),
                    make_event(1, MidiEventType.NOTE_OFF, time_ns=2_000, note=60, velocity=0),
                ),
            }
        ),
        ended_at=T1,
    )
    result = pair_midi_notes(
        capture,
        observed_id_factory=lambda index: f"observed-{index}",
        repetition_resolver=lambda event: 3 if event.capture_time_ns >= 1_000 else 0,
    )
    assert result.observed_notes[0].repetition_index == 3
