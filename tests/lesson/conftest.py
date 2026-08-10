"""Deterministic fixtures for lesson-assignment tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.core.spatial_mapping.serialization import instrument_profile_from_mapping
from master_all_strings.instruments import InstrumentProfile
from master_all_strings.lesson.enums import (
    LessonContentFormat,
    LessonSourceType,
    OpenStringPreference,
)
from master_all_strings.lesson.models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LESSON_ASSIGNMENT_SCHEMA_VERSION,
    LessonAssessmentV1,
    LessonAssignmentV1,
    LessonIdentityV1,
    LessonInstructionV1,
    LessonMusicalContentV1,
    LessonPlaybackPolicyV1,
    LessonProvenanceV1,
    LessonRoutingV1,
    LessonSpatialGuidanceV1,
    SerializedCanonicalEventV1,
    SerializedTempoChangeV1,
    TeacherOverrideV1,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LESSON_EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
LESSON_SCHEMA = REPO_ROOT / "resources" / "lesson" / "schema" / "lesson_assignment_v1.schema.json"
GUITAR_PROFILE_PATH = (
    REPO_ROOT / "resources" / "instruments" / "examples" / "guitar-standard-6.json"
)
MIDI_BASIC = REPO_ROOT / "resources" / "lesson" / "midi" / "basic_two_notes.mid"


@pytest.fixture(scope="session")
def midi_basic_bytes() -> bytes:
    return MIDI_BASIC.read_bytes()


@pytest.fixture(scope="session")
def guitar_profile() -> InstrumentProfile:
    data = json.loads(GUITAR_PROFILE_PATH.read_text(encoding="utf-8"))
    return instrument_profile_from_mapping(data)


@pytest.fixture(scope="session")
def instrument_catalog(guitar_profile: InstrumentProfile) -> dict[str, InstrumentProfile]:
    return {guitar_profile.instrument_id: guitar_profile}


@pytest.fixture
def minimal_assignment() -> LessonAssignmentV1:
    return LessonAssignmentV1(
        schema_id=LESSON_ASSIGNMENT_SCHEMA_ID,
        schema_version=LESSON_ASSIGNMENT_SCHEMA_VERSION,
        identity=LessonIdentityV1(
            assignment_id="assign-1",
            content_id="content-1",
            title="Minimal",
        ),
        musical_content=LessonMusicalContentV1(
            format=LessonContentFormat.CANONICAL_EVENTS,
            ticks_per_quarter=480,
            events=(
                SerializedCanonicalEventV1(
                    event_id="ev-1",
                    midi_note=64,
                    start_tick=0,
                    duration_ticks=480,
                    velocity=80,
                ),
            ),
            tempo_changes=(SerializedTempoChangeV1(tick=0, tempo_bpm=120.0),),
        ),
        playback=LessonPlaybackPolicyV1(),
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id="guitar-standard-6",
            fingering_policy_id="enumeration_v1",
            open_string_preference=OpenStringPreference.ALLOW,
        ),
        provenance=LessonProvenanceV1(
            created_by="test",
            created_at_utc="2026-08-10T00:00:00Z",
            source_type=LessonSourceType.MANUAL,
            source_name="minimal.json",
        ),
    )


@pytest.fixture
def populated_assignment(minimal_assignment: LessonAssignmentV1) -> LessonAssignmentV1:
    return LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=LessonIdentityV1(
            assignment_id="teacher_smith_student_42_2026_08_10",
            content_id="blues_turnaround_01",
            title="Blues Turnaround",
            description="Practice the turnaround",
        ),
        musical_content=LessonMusicalContentV1(
            format=LessonContentFormat.CANONICAL_EVENTS,
            ticks_per_quarter=480,
            events=(
                SerializedCanonicalEventV1("ev-1", 64, 0, 480, 80),
                SerializedCanonicalEventV1("ev-2", 67, 480, 480, 80),
                SerializedCanonicalEventV1("ev-3", 69, 960, 480, 80),
            ),
            tempo_changes=(SerializedTempoChangeV1(0, 100.0),),
        ),
        playback=LessonPlaybackPolicyV1(
            tempo_override=110.0,
            start_tick=0,
            end_tick=1920,
            loop_enabled=True,
            count_in_bars=1,
        ),
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id="guitar-standard-6",
            fingering_policy_id="enumeration_v1",
            preferred_fret_min=0,
            preferred_fret_max=5,
            open_string_preference=OpenStringPreference.PREFER,
        ),
        teacher_overrides=(
            TeacherOverrideV1(
                event_id="ev-1",
                string_id="string-2",
                physical_fret_number=5,
                reason="position V",
            ),
        ),
        instruction=LessonInstructionV1(
            objective="Clean turnaround",
            repetitions=4,
            difficulty="intermediate",
            curriculum_ref="curriculum/blues/unit-2",
            teacher_note="Watch the third",
        ),
        assessment=LessonAssessmentV1(
            enabled=True,
            mode="enabled",
            note_accuracy_required=0.9,
            timing_tolerance_ms=40,
            required_successful_repetitions=3,
        ),
        provenance=LessonProvenanceV1(
            created_by="teacher",
            created_at_utc="2026-08-10T12:00:00Z",
            source_type=LessonSourceType.TEACHER,
            source_name="exercise.mid",
        ),
        routing=LessonRoutingV1(
            sender_device_id="guitar-teacher-01",
            recipient_device_id="guitar-student-42",
            classroom_id="room-a",
        ),
    )
