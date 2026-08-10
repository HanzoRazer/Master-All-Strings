"""MIDI import adapter tests."""

from __future__ import annotations

from pathlib import Path

from master_all_strings.lesson.importers.midi import MidiLessonImporter, build_assignment_from_midi
from master_all_strings.lesson.serialization import (
    compute_lesson_behavior_digest,
    serialize_lesson_assignment,
)


def test_local_midi_imports_successfully(midi_basic_bytes: bytes) -> None:
    result = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="midi-assign-1",
        source_name="basic_two_notes.mid",
    )
    assert len(result.assignment.musical_content.events) == 2
    assert result.assignment.musical_content.ticks_per_quarter == 480


def test_midi_notes_become_canonical_shaped_events(midi_basic_bytes: bytes) -> None:
    assignment = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="a",
        source_name="basic_two_notes.mid",
    ).assignment
    first = assignment.musical_content.events[0]
    assert first.event_id == "ev-1"
    assert first.midi_note == 60
    assert first.start_tick == 0
    assert first.duration_ticks == 480
    assert first.velocity == 80


def test_tempo_preserved(midi_basic_bytes: bytes) -> None:
    assignment = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="a",
    ).assignment
    assert assignment.musical_content.tempo_changes
    assert abs(assignment.musical_content.tempo_changes[0].tempo_bpm - 120.0) < 0.01


def test_source_filename_preserved_not_absolute_path(
    tmp_path: Path,
    midi_basic_bytes: bytes,
) -> None:
    target = tmp_path / "nested" / "exercise.mid"
    target.parent.mkdir(parents=True)
    target.write_bytes(midi_basic_bytes)
    result = MidiLessonImporter().import_path(target, assignment_id="a")
    assert result.assignment.provenance.source_name == "exercise.mid"
    assert "\\" not in (result.assignment.provenance.source_name or "")
    assert not str(result.assignment.provenance.source_name).startswith("/")


def test_repeated_import_equivalent_musical_content(midi_basic_bytes: bytes) -> None:
    a = build_assignment_from_midi(midi_basic_bytes, assignment_id="a1").assignment
    b = build_assignment_from_midi(midi_basic_bytes, assignment_id="a2").assignment
    assert a.musical_content == b.musical_content
    # Behavior digests differ only by identity; content equal is the gate.
    assert serialize_lesson_assignment(a) != serialize_lesson_assignment(b)
    assert a.content_id == b.content_id


def test_import_then_behavior_digest_stable(midi_basic_bytes: bytes) -> None:
    assignment = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="stable",
        content_id="fixed-content",
        source_name="basic_two_notes.mid",
    ).assignment
    assert compute_lesson_behavior_digest(assignment) == compute_lesson_behavior_digest(assignment)
