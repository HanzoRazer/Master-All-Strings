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
    PlaybackTimelineV1,
    PlaybackWarningV1,
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


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": ""}, "event_id"),
        ({"midi_note": True}, "midi_note must be an integer"),
        ({"midi_note": 128}, "between 0 and 127"),
        ({"velocity": True}, "velocity must be an integer"),
        ({"velocity": 128}, "velocity must be between"),
        ({"onset_seconds": float("nan")}, "finite number"),
        ({"onset_seconds": -1.0}, "must not be negative"),
        ({"cents_offset": float("inf")}, "cents_offset must be a finite"),
    ],
)
def test_playback_event_defensive_validation(
    changes: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "event_id": "note",
        "midi_note": 60,
        "velocity": 64,
        "onset_seconds": 0.0,
        "release_seconds": 1.0,
    }
    values.update(changes)
    with pytest.raises(PlaybackPlanBuildError, match=message):
        LessonPlaybackEventV1(**values)  # type: ignore[arg-type]


def test_timeline_and_warning_defensive_validation() -> None:
    with pytest.raises(PlaybackPlanBuildError, match="ticks_per_quarter"):
        PlaybackTimelineV1(0, 480, (tempo_from_bpm(120),))
    with pytest.raises(PlaybackPlanBuildError, match="total_ticks"):
        PlaybackTimelineV1(480, -1, (tempo_from_bpm(120),))
    with pytest.raises(PlaybackPlanBuildError, match="TempoChangeV1"):
        PlaybackTimelineV1(480, 480, ("bad",))  # type: ignore[arg-type]
    with pytest.raises(PlaybackPlanBuildError, match="strictly increase"):
        PlaybackTimelineV1(
            480,
            480,
            (tempo_from_bpm(120), tempo_from_bpm(100)),
        )
    with pytest.raises(PlaybackPlanBuildError, match="begin at tick 0"):
        PlaybackTimelineV1(480, 480, (tempo_from_bpm(120, tick=1),))
    with pytest.raises(PlaybackPlanBuildError, match="warning code"):
        PlaybackWarningV1("", "message")
    with pytest.raises(PlaybackPlanBuildError, match="warning event_id"):
        PlaybackWarningV1("code", "message", "")


def test_plan_defensive_validation() -> None:
    plan = build(event("note", 60, 0))
    with pytest.raises(PlaybackPlanBuildError, match="schema_version"):
        replace(plan, schema_version="2.0.0")
    with pytest.raises(PlaybackPlanBuildError, match="unique"):
        replace(plan, events=(plan.events[0], plan.events[0]))
    with pytest.raises(PlaybackPlanBuildError, match="cover every event"):
        replace(plan, total_seconds=0.1)
    with pytest.raises(PlaybackPlanBuildError, match="warnings must contain"):
        replace(plan, warnings=("bad",))  # type: ignore[arg-type]
    with pytest.raises(PlaybackPlanBuildError, match="unsupported_features must be unique"):
        replace(plan, unsupported_features=("feature", "feature"))


def test_builder_rejects_noncanonical_event_values() -> None:
    with pytest.raises(PlaybackPlanBuildError, match="MusicalEvent"):
        build_lesson_playback_plan(
            assignment_id="assignment-1",
            content_id="content-1",
            events=("bad",),  # type: ignore[arg-type]
            ticks_per_quarter=480,
            tempo_changes=(tempo_from_bpm(120),),
        )
