"""Build audible playback plans directly from canonical musical events."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.musical_timeline import normalize_tempo_map, ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.mvp.errors import PlaybackPlanBuildError
from master_all_strings.mvp.playback.models import (
    LESSON_PLAYBACK_PLAN_SCHEMA_VERSION,
    LessonPlaybackEventV1,
    LessonPlaybackPlanV1,
    PlaybackTimelineV1,
    PlaybackWarningV1,
)
from master_all_strings.mvp.playback.serialization import compute_playback_plan_digest

__all__ = ["build_lesson_playback_plan"]

_PENDING_DIGEST = "sha256:" + ("0" * 64)


def build_lesson_playback_plan(
    *,
    assignment_id: str,
    content_id: str,
    events: Sequence[MusicalEvent],
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
    canonical_revision_id: str | None = None,
    warnings: Sequence[PlaybackWarningV1] = (),
    unsupported_features: Sequence[str] = (),
) -> LessonPlaybackPlanV1:
    """Derive browser-ready pitch/timing without spatial projection input."""

    if not events:
        raise PlaybackPlanBuildError("playback plan requires canonical musical events")
    if any(not isinstance(event, MusicalEvent) for event in events):
        raise PlaybackPlanBuildError("events must contain MusicalEvent values")
    try:
        tempo_map = normalize_tempo_map(tempo_changes)
        total_ticks = max(event.start_tick + event.duration_ticks for event in events)
        playback_events = tuple(
            sorted(
                (
                    LessonPlaybackEventV1(
                        event_id=event.event_id,
                        midi_note=event.midi_note,
                        velocity=event.velocity,
                        onset_seconds=ticks_to_seconds(
                            event.start_tick,
                            ticks_per_quarter=ticks_per_quarter,
                            tempo_changes=tempo_map,
                        ),
                        release_seconds=ticks_to_seconds(
                            event.start_tick + event.duration_ticks,
                            ticks_per_quarter=ticks_per_quarter,
                            tempo_changes=tempo_map,
                        ),
                        cents_offset=event.cents_offset if event.cents_offset != 0.0 else None,
                    )
                    for event in events
                ),
                key=lambda item: (item.onset_seconds, item.release_seconds, item.event_id),
            )
        )
        total_seconds = ticks_to_seconds(
            total_ticks,
            ticks_per_quarter=ticks_per_quarter,
            tempo_changes=tempo_map,
        )
    except (ScoreContractError, ValueError, TypeError) as exc:
        raise PlaybackPlanBuildError(f"invalid authoritative musical timeline: {exc}") from exc

    draft = LessonPlaybackPlanV1(
        schema_version=LESSON_PLAYBACK_PLAN_SCHEMA_VERSION,
        assignment_id=assignment_id,
        content_id=content_id,
        canonical_revision_id=canonical_revision_id,
        timeline=PlaybackTimelineV1(
            ticks_per_quarter=ticks_per_quarter,
            total_ticks=total_ticks,
            tempo_changes=tempo_map,
        ),
        events=playback_events,
        total_seconds=total_seconds,
        warnings=tuple(warnings),
        unsupported_features=tuple(dict.fromkeys(unsupported_features)),
        playback_digest=_PENDING_DIGEST,
    )
    return replace(draft, playback_digest=compute_playback_plan_digest(draft))
