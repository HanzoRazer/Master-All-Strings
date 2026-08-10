"""Resolve LessonAssignmentV1 into canonical Musical Core inputs.

The resolver must not run MSME, select fingering, compute renderer geometry,
interpret curriculum, or read routing metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.musical_events import MusicalEvent

from .enums import OpenStringPreference
from .errors import LessonValidationError
from .models import (
    LessonAssignmentV1,
    LessonPlaybackPolicyV1,
    LessonSpatialGuidanceV1,
    TeacherOverrideV1,
)
from .validation import validate_assignment

__all__ = [
    "LessonAssignmentResolver",
    "PlaybackRequestV1",
    "ResolvedLessonV1",
    "SpatialSelectionRequestV1",
    "resolve_lesson_assignment",
]


@dataclass(frozen=True)
class PlaybackRequestV1:
    """Transport-facing playback request derived from assignment policy."""

    tempo_bpm: float | None
    start_tick: int | None
    end_tick: int | None
    loop_enabled: bool
    count_in_bars: int | None
    ticks_per_quarter: int
    source_tempo_bpm: float | None


@dataclass(frozen=True)
class SpatialSelectionRequestV1:
    """Selection-facing spatial guidance (intent only)."""

    instrument_profile_id: str
    fingering_policy_id: str
    preferred_fret_min: int | None
    preferred_fret_max: int | None
    open_string_preference: OpenStringPreference


@dataclass(frozen=True)
class ResolvedLessonV1:
    """Canonical lesson inputs for the existing MVP pipeline."""

    assignment_id: str
    content_id: str
    title: str
    events: tuple[MusicalEvent, ...]
    playback: PlaybackRequestV1
    spatial: SpatialSelectionRequestV1
    teacher_overrides: tuple[TeacherOverrideV1, ...]
    instruction_objective: str | None
    teacher_note: str | None
    # Explicitly absent: routing. Callers must not receive routing here.


class LessonAssignmentResolver:
    """Resolve a validated assignment into Musical Core inputs."""

    def resolve(self, assignment: LessonAssignmentV1) -> ResolvedLessonV1:
        return resolve_lesson_assignment(assignment)


def resolve_lesson_assignment(assignment: LessonAssignmentV1) -> ResolvedLessonV1:
    """Produce canonical lesson inputs. Routing is never read."""

    validate_assignment(assignment, instrument_profiles=None, validate_overrides_physically=False)

    # Binding routing to a discarded name documents the neutrality invariant:
    # the musical path must not branch on it.
    _routing_ignored = assignment.routing  # noqa: F841

    events = tuple(
        MusicalEvent(
            event_id=item.event_id,
            midi_note=item.midi_note,
            start_tick=item.start_tick,
            duration_ticks=item.duration_ticks,
            velocity=item.velocity,
            cents_offset=item.cents_offset,
            voice_id=item.voice_id,
        )
        for item in assignment.musical_content.events
    )
    if not events:
        raise LessonValidationError("resolved events must not be empty", code="missing_content")

    source_tempo = _source_tempo_bpm(assignment)
    playback = _resolve_playback(assignment.playback, assignment, source_tempo)
    spatial = _resolve_spatial(assignment.spatial_guidance)

    return ResolvedLessonV1(
        assignment_id=assignment.assignment_id,
        content_id=assignment.content_id,
        title=assignment.title,
        events=events,
        playback=playback,
        spatial=spatial,
        teacher_overrides=assignment.teacher_overrides,
        instruction_objective=assignment.instruction.objective,
        teacher_note=assignment.instruction.teacher_note,
    )


def _source_tempo_bpm(assignment: LessonAssignmentV1) -> float | None:
    changes = assignment.musical_content.tempo_changes
    if not changes:
        return None
    # Prefer the tempo at tick 0; otherwise the earliest change.
    ordered = sorted(changes, key=lambda item: item.tick)
    for item in ordered:
        if item.tick == 0:
            return item.tempo_bpm
    return ordered[0].tempo_bpm


def _resolve_playback(
    policy: LessonPlaybackPolicyV1,
    assignment: LessonAssignmentV1,
    source_tempo: float | None,
) -> PlaybackRequestV1:
    tempo = policy.tempo_override if policy.tempo_override is not None else source_tempo
    return PlaybackRequestV1(
        tempo_bpm=tempo,
        start_tick=policy.start_tick,
        end_tick=policy.end_tick,
        loop_enabled=policy.loop_enabled,
        count_in_bars=policy.count_in_bars,
        ticks_per_quarter=assignment.musical_content.ticks_per_quarter,
        source_tempo_bpm=source_tempo,
    )


def _resolve_spatial(guidance: LessonSpatialGuidanceV1) -> SpatialSelectionRequestV1:
    return SpatialSelectionRequestV1(
        instrument_profile_id=guidance.instrument_profile_id,
        fingering_policy_id=guidance.fingering_policy_id,
        preferred_fret_min=guidance.preferred_fret_min,
        preferred_fret_max=guidance.preferred_fret_max,
        open_string_preference=guidance.open_string_preference,
    )
