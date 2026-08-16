"""Deterministic FIFO pairing of immutable raw MIDI lifecycle messages."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from master_all_strings.performance.contracts.capture import (
    CapturedMidiEventV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
    UnmatchedMidiNoteOffV1,
)

RepetitionResolver = Callable[[CapturedMidiEventV1], int]
ObservedIdFactory = Callable[[int], str]


@dataclass(frozen=True)
class MidiNotePairingResultV1:
    observed_notes: tuple[ObservedMidiNoteV1, ...]
    unmatched_note_offs: tuple[UnmatchedMidiNoteOffV1, ...]


def pair_midi_notes(
    capture: RawPerformanceCaptureV1,
    *,
    observed_id_factory: ObservedIdFactory,
    repetition_resolver: RepetitionResolver = lambda _: 0,
) -> MidiNotePairingResultV1:
    """Pair note messages FIFO by device, channel, and pitch."""
    queues: dict[tuple[str, int, int], deque[CapturedMidiEventV1]] = defaultdict(deque)
    completed: list[ObservedMidiNoteV1] = []
    unmatched_offs: list[UnmatchedMidiNoteOffV1] = []
    next_id = 0

    for event in capture.events:
        if event.event_type not in (MidiEventType.NOTE_ON, MidiEventType.NOTE_OFF):
            continue
        assert event.note is not None
        assert event.velocity is not None
        key = (event.source_device, event.channel, event.note)
        is_note_off = event.event_type is MidiEventType.NOTE_OFF or event.velocity == 0
        if not is_note_off:
            queues[key].append(event)
            continue
        if not queues[key]:
            unmatched_offs.append(
                UnmatchedMidiNoteOffV1(
                    schema_version="1.0.0",
                    raw_event_id=event.event_id,
                    capture_id=capture.capture_id,
                    midi_note=event.note,
                    channel=event.channel,
                    source_device=event.source_device,
                    capture_time_ns=event.capture_time_ns,
                    source_string=event.source_string,
                    repetition_index=repetition_resolver(event),
                )
            )
            continue
        note_on = queues[key].popleft()
        completed.append(
            _build_note(
                capture.capture_id,
                observed_id_factory(next_id),
                note_on,
                event,
                repetition_resolver(note_on),
            )
        )
        next_id += 1

    open_notes = sorted(
        (event for queue in queues.values() for event in queue),
        key=lambda event: event.sequence_number,
    )
    for note_on in open_notes:
        completed.append(
            _build_note(
                capture.capture_id,
                observed_id_factory(next_id),
                note_on,
                None,
                repetition_resolver(note_on),
            )
        )
        next_id += 1
    completed.sort(key=lambda note: (note.note_on_time_ns, note.note_on_event_id))
    return MidiNotePairingResultV1(tuple(completed), tuple(unmatched_offs))


def _build_note(
    capture_id: str,
    observed_event_id: str,
    note_on: CapturedMidiEventV1,
    note_off: CapturedMidiEventV1 | None,
    repetition_index: int,
) -> ObservedMidiNoteV1:
    assert note_on.note is not None
    assert note_on.velocity is not None
    return ObservedMidiNoteV1(
        schema_version="1.0.0",
        observed_event_id=observed_event_id,
        capture_id=capture_id,
        note_on_event_id=note_on.event_id,
        note_off_event_id=None if note_off is None else note_off.event_id,
        midi_note=note_on.note,
        velocity=note_on.velocity,
        channel=note_on.channel,
        source_device=note_on.source_device,
        note_on_time_ns=note_on.capture_time_ns,
        note_off_time_ns=None if note_off is None else note_off.capture_time_ns,
        duration_ns=(
            None if note_off is None else note_off.capture_time_ns - note_on.capture_time_ns
        ),
        source_string=note_on.source_string,
        status=(
            ObservedMidiNoteStatus.UNMATCHED_NOTE_ON
            if note_off is None
            else ObservedMidiNoteStatus.COMPLETE
        ),
        repetition_index=repetition_index,
    )
