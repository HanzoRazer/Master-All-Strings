from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from master_all_strings.core.foundation import SpatialMappingError
from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.tempo import tempo_from_bpm
from master_all_strings.mvp.errors import PlaybackPlanBuildError
from master_all_strings.mvp.playback import (
    LessonPlaybackEventV1,
    build_lesson_playback_plan,
    compute_playback_plan_digest,
    serialize_lesson_playback_plan,
    verify_playback_plan_digest,
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "resources" / "mvp2" / "schema" / "lesson_playback_plan_v1.schema.json"


def event(
    event_id: str,
    midi_note: int,
    start_tick: int,
    duration_ticks: int = 480,
    *,
    velocity: int = 64,
    cents_offset: float = 0.0,
) -> MusicalEvent:
    return MusicalEvent(
        event_id=event_id,
        midi_note=midi_note,
        start_tick=start_tick,
        duration_ticks=duration_ticks,
        velocity=velocity,
        cents_offset=cents_offset,
    )


def build(*events: MusicalEvent):
    return build_lesson_playback_plan(
        assignment_id="assignment-1",
        content_id="content-1",
        events=events,
        ticks_per_quarter=480,
        tempo_changes=(tempo_from_bpm(120),),
        canonical_revision_id="revision-1",
    )


def test_single_note_preserves_pitch_velocity_and_canonical_timing() -> None:
    plan = build(event("note-1", 69, 0, velocity=101, cents_offset=12.5))

    assert plan.events[0].midi_note == 69
    assert plan.events[0].velocity == 101
    assert plan.events[0].onset_seconds == 0.0
    assert plan.events[0].release_seconds == 0.5
    assert plan.events[0].cents_offset == 12.5
    assert plan.total_seconds == 0.5


def test_melody_is_ordered_deterministically_and_serializes_stably() -> None:
    plan = build(event("later", 64, 480), event("first", 60, 0))

    assert [item.event_id for item in plan.events] == ["first", "later"]
    assert serialize_lesson_playback_plan(plan) == serialize_lesson_playback_plan(plan)
    assert compute_playback_plan_digest(plan) == plan.playback_digest


def test_simultaneous_notes_use_identity_as_stable_tie_breaker() -> None:
    plan = build(event("b", 67, 0), event("a", 60, 0))

    assert [item.event_id for item in plan.events] == ["a", "b"]


def test_tempo_change_uses_core_timeline_authority() -> None:
    plan = build_lesson_playback_plan(
        assignment_id="assignment-1",
        content_id="content-1",
        events=(event("note", 60, 0, 960),),
        ticks_per_quarter=480,
        tempo_changes=(tempo_from_bpm(120), tempo_from_bpm(60, tick=480)),
    )

    assert plan.events[0].release_seconds == 1.5
    assert plan.total_seconds == 1.5


def test_spatially_unplayable_pitch_remains_an_audible_event() -> None:
    plan = build(event("below-guitar", 20, 0))

    assert [(item.event_id, item.midi_note) for item in plan.events] == [
        ("below-guitar", 20)
    ]


def test_missing_tempo_fails_without_a_default() -> None:
    with pytest.raises(PlaybackPlanBuildError, match="tempo map is required"):
        build_lesson_playback_plan(
            assignment_id="assignment-1",
            content_id="content-1",
            events=(event("note", 60, 0),),
            ticks_per_quarter=480,
            tempo_changes=(),
        )


def test_invalid_canonical_duration_is_rejected_before_playback() -> None:
    with pytest.raises(SpatialMappingError, match="duration_ticks must be positive"):
        event("invalid", 60, 0, 0)


def test_invalid_playback_duration_is_rejected() -> None:
    with pytest.raises(PlaybackPlanBuildError, match="greater than onset"):
        LessonPlaybackEventV1(
            event_id="invalid",
            midi_note=60,
            velocity=64,
            onset_seconds=1.0,
            release_seconds=1.0,
        )


def test_serialized_plan_validates_against_published_schema() -> None:
    payload = json.loads(serialize_lesson_playback_plan(build(event("note", 60, 0))))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)


def test_digest_tampering_is_detected() -> None:
    plan = build(event("note", 60, 0))
    tampered = replace(plan, total_seconds=2.0)

    with pytest.raises(PlaybackPlanBuildError, match="does not match"):
        verify_playback_plan_digest(tampered)
