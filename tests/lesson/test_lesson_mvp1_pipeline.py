"""MVP-1E vertical proof and migration-equivalence gates."""

from __future__ import annotations

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.lesson.importers.midi import build_assignment_from_midi
from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    LessonPlaybackPolicyV1,
    LessonRoutingV1,
)
from master_all_strings.lesson.pipeline import run_mvp_lesson_pipeline
from master_all_strings.lesson.renderer import render_scrolling_fretboard_view
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.lesson.serialization import (
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)


def test_midi_through_assignment_matches_direct_canonical_msme(
    instrument_catalog: dict,
    guitar_profile,
    midi_basic_bytes: bytes,
) -> None:
    """Migration-equivalence: MIDI→assignment→events equals direct MusicalEvents for MSME."""

    imported = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="eq-1",
        source_name="basic_two_notes.mid",
    ).assignment
    resolved = resolve_lesson_assignment(imported)

    # Direct construction matching importer output (legacy conceptual path).
    direct = tuple(
        MusicalEvent(
            event_id=e.event_id,
            midi_note=e.midi_note,
            start_tick=e.start_tick,
            duration_ticks=e.duration_ticks,
            velocity=e.velocity,
            cents_offset=e.cents_offset,
            voice_id=e.voice_id,
        )
        for e in imported.musical_content.events
    )
    assert resolved.events == direct
    for event in resolved.events:
        assert generate_candidates(event, guitar_profile) == generate_candidates(
            event, guitar_profile
        )


def test_full_vertical_proof_serialize_reload_routing(
    instrument_catalog: dict,
    midi_basic_bytes: bytes,
) -> None:
    imported = build_assignment_from_midi(
        midi_basic_bytes,
        assignment_id="vertical-1",
        content_id="vertical-content",
        source_name="basic_two_notes.mid",
        title="Vertical Proof",
    ).assignment
    text = serialize_lesson_assignment(imported)
    reloaded = deserialize_lesson_assignment(text)
    assert compute_lesson_behavior_digest(imported) == compute_lesson_behavior_digest(reloaded)

    base = run_mvp_lesson_pipeline(reloaded, instrument_profiles=instrument_catalog)
    routed = LessonAssignmentV1(
        schema_id=reloaded.schema_id,
        schema_version=reloaded.schema_version,
        identity=reloaded.identity,
        musical_content=reloaded.musical_content,
        playback=reloaded.playback,
        spatial_guidance=reloaded.spatial_guidance,
        teacher_overrides=reloaded.teacher_overrides,
        instruction=reloaded.instruction,
        assessment=reloaded.assessment,
        provenance=reloaded.provenance,
        routing=LessonRoutingV1("sender", "recipient", "class-1"),
    )
    routed_result = run_mvp_lesson_pipeline(routed, instrument_profiles=instrument_catalog)
    assert base.projection_digest == routed_result.projection_digest
    assert tuple(e.position for e in base.selected_events) == tuple(
        e.position for e in routed_result.selected_events
    )

    view = render_scrolling_fretboard_view(base.projection)
    assert view.title == "Vertical Proof"
    assert "routing" not in view.__dataclass_fields__


def test_tempo_change_does_not_alter_fingering(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    slow = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=LessonPlaybackPolicyV1(tempo_override=60.0),
        spatial_guidance=minimal_assignment.spatial_guidance,
        provenance=minimal_assignment.provenance,
    )
    fast = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=LessonPlaybackPolicyV1(tempo_override=180.0),
        spatial_guidance=minimal_assignment.spatial_guidance,
        provenance=minimal_assignment.provenance,
    )
    rs = run_mvp_lesson_pipeline(slow, instrument_profiles=instrument_catalog)
    rf = run_mvp_lesson_pipeline(fast, instrument_profiles=instrument_catalog)
    assert rs.resolved.events == rf.resolved.events
    assert tuple(e.candidates for e in rs.selected_events) == tuple(
        e.candidates for e in rf.selected_events
    )
    assert tuple(e.position for e in rs.selected_events) == tuple(
        e.position for e in rf.selected_events
    )
    assert rs.resolved.playback.tempo_bpm != rf.resolved.playback.tempo_bpm


def test_renderer_metadata_display_only(
    populated_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    result = run_mvp_lesson_pipeline(populated_assignment, instrument_profiles=instrument_catalog)
    view = render_scrolling_fretboard_view(result.projection)
    assert view.title == populated_assignment.title
    assert view.objective == populated_assignment.instruction.objective
    assert view.teacher_note == populated_assignment.instruction.teacher_note
    # Note positions come solely from projection payload.
    assert view.notes[0]["string_id"] == result.projection.notes[0].string_id
