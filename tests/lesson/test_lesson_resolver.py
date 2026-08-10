"""Resolver tests: assignment → canonical MusicalEvent."""

from __future__ import annotations

from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    LessonPlaybackPolicyV1,
    LessonRoutingV1,
)
from master_all_strings.lesson.resolver import resolve_lesson_assignment


def test_resolves_expected_events(minimal_assignment: LessonAssignmentV1) -> None:
    resolved = resolve_lesson_assignment(minimal_assignment)
    assert len(resolved.events) == 1
    event = resolved.events[0]
    assert event.event_id == "ev-1"
    assert event.midi_note == 64
    assert event.start_tick == 0
    assert event.duration_ticks == 480
    assert event.velocity == 80
    assert event.cents_offset == 0.0
    assert event.voice_id is None


def test_playback_and_spatial_resolved_separately(populated_assignment: LessonAssignmentV1) -> None:
    resolved = resolve_lesson_assignment(populated_assignment)
    assert resolved.playback.tempo_bpm == 110.0
    assert resolved.playback.loop_enabled is True
    assert resolved.spatial.instrument_profile_id == "guitar-standard-6"
    assert resolved.spatial.preferred_fret_max == 5


def test_tempo_override_precedence(minimal_assignment: LessonAssignmentV1) -> None:
    overridden = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=LessonPlaybackPolicyV1(tempo_override=90.0),
        spatial_guidance=minimal_assignment.spatial_guidance,
        provenance=minimal_assignment.provenance,
    )
    resolved = resolve_lesson_assignment(overridden)
    assert resolved.playback.tempo_bpm == 90.0
    assert resolved.playback.source_tempo_bpm == 120.0


def test_routing_not_present_on_resolved(populated_assignment: LessonAssignmentV1) -> None:
    resolved = resolve_lesson_assignment(populated_assignment)
    assert not hasattr(resolved, "routing")
    assert populated_assignment.routing == LessonRoutingV1(
        "guitar-teacher-01", "guitar-student-42", "room-a"
    )
