"""Versioned delivery models for audible lesson playback."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.mvp.errors import PlaybackPlanBuildError

__all__ = [
    "LESSON_PLAYBACK_PLAN_SCHEMA_VERSION",
    "LessonPlaybackEventV1",
    "LessonPlaybackPlanV1",
    "PlaybackTimelineV1",
    "PlaybackWarningV1",
]

LESSON_PLAYBACK_PLAN_SCHEMA_VERSION = "1.0.0"


def _require_non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PlaybackPlanBuildError(f"{field} must be a non-empty string")


def _require_nonnegative_number(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise PlaybackPlanBuildError(f"{field} must be a finite number")
    if value < 0:
        raise PlaybackPlanBuildError(f"{field} must not be negative")


@dataclass(frozen=True)
class LessonPlaybackEventV1:
    event_id: str
    midi_note: int
    velocity: int
    onset_seconds: float
    release_seconds: float
    cents_offset: float | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.event_id, "event_id")
        if isinstance(self.midi_note, bool) or not isinstance(self.midi_note, int):
            raise PlaybackPlanBuildError("midi_note must be an integer")
        if not 0 <= self.midi_note <= 127:
            raise PlaybackPlanBuildError("midi_note must be between 0 and 127")
        if isinstance(self.velocity, bool) or not isinstance(self.velocity, int):
            raise PlaybackPlanBuildError("velocity must be an integer")
        if not 0 <= self.velocity <= 127:
            raise PlaybackPlanBuildError("velocity must be between 0 and 127")
        _require_nonnegative_number(self.onset_seconds, "onset_seconds")
        _require_nonnegative_number(self.release_seconds, "release_seconds")
        if self.release_seconds <= self.onset_seconds:
            raise PlaybackPlanBuildError("release_seconds must be greater than onset_seconds")
        if self.cents_offset is not None:
            if (
                isinstance(self.cents_offset, bool)
                or not isinstance(self.cents_offset, (int, float))
                or not isfinite(self.cents_offset)
            ):
                raise PlaybackPlanBuildError("cents_offset must be a finite number")


@dataclass(frozen=True)
class PlaybackTimelineV1:
    ticks_per_quarter: int
    total_ticks: int
    tempo_changes: tuple[TempoChangeV1, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.ticks_per_quarter, bool)
            or not isinstance(self.ticks_per_quarter, int)
            or self.ticks_per_quarter <= 0
        ):
            raise PlaybackPlanBuildError("ticks_per_quarter must be a positive integer")
        if (
            isinstance(self.total_ticks, bool)
            or not isinstance(self.total_ticks, int)
            or self.total_ticks < 0
        ):
            raise PlaybackPlanBuildError("total_ticks must be a non-negative integer")
        if not isinstance(self.tempo_changes, tuple) or not self.tempo_changes:
            raise PlaybackPlanBuildError("timeline requires an authoritative tempo map")
        previous = -1
        for change in self.tempo_changes:
            if not isinstance(change, TempoChangeV1):
                raise PlaybackPlanBuildError("tempo_changes must contain TempoChangeV1 values")
            if change.tick <= previous:
                raise PlaybackPlanBuildError("tempo change ticks must strictly increase")
            previous = change.tick
        if self.tempo_changes[0].tick != 0:
            raise PlaybackPlanBuildError("tempo map must begin at tick 0")


@dataclass(frozen=True)
class PlaybackWarningV1:
    code: str
    message: str
    event_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "warning code")
        _require_non_empty(self.message, "warning message")
        if self.event_id is not None:
            _require_non_empty(self.event_id, "warning event_id")


@dataclass(frozen=True)
class LessonPlaybackPlanV1:
    schema_version: str
    assignment_id: str
    content_id: str
    timeline: PlaybackTimelineV1
    events: tuple[LessonPlaybackEventV1, ...]
    total_seconds: float
    warnings: tuple[PlaybackWarningV1, ...]
    unsupported_features: tuple[str, ...]
    playback_digest: str
    canonical_revision_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != LESSON_PLAYBACK_PLAN_SCHEMA_VERSION:
            raise PlaybackPlanBuildError(
                f"schema_version must be {LESSON_PLAYBACK_PLAN_SCHEMA_VERSION!r}"
            )
        _require_non_empty(self.assignment_id, "assignment_id")
        _require_non_empty(self.content_id, "content_id")
        if self.canonical_revision_id is not None:
            _require_non_empty(self.canonical_revision_id, "canonical_revision_id")
        if not isinstance(self.timeline, PlaybackTimelineV1):
            raise PlaybackPlanBuildError("timeline must be PlaybackTimelineV1")
        if not isinstance(self.events, tuple) or not self.events:
            raise PlaybackPlanBuildError("playback plan requires at least one event")
        if any(not isinstance(event, LessonPlaybackEventV1) for event in self.events):
            raise PlaybackPlanBuildError("events must contain LessonPlaybackEventV1 values")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise PlaybackPlanBuildError("playback event_id values must be unique")
        ordering = [
            (event.onset_seconds, event.release_seconds, event.event_id)
            for event in self.events
        ]
        if ordering != sorted(ordering):
            raise PlaybackPlanBuildError("playback events must be deterministically ordered")
        _require_nonnegative_number(self.total_seconds, "total_seconds")
        if self.total_seconds < max(event.release_seconds for event in self.events):
            raise PlaybackPlanBuildError("total_seconds must cover every event release")
        if not isinstance(self.warnings, tuple) or any(
            not isinstance(warning, PlaybackWarningV1) for warning in self.warnings
        ):
            raise PlaybackPlanBuildError("warnings must contain PlaybackWarningV1 values")
        if not isinstance(self.unsupported_features, tuple):
            raise PlaybackPlanBuildError("unsupported_features must be a tuple")
        for feature in self.unsupported_features:
            _require_non_empty(feature, "unsupported feature")
        if len(self.unsupported_features) != len(set(self.unsupported_features)):
            raise PlaybackPlanBuildError("unsupported_features must be unique")
        _require_non_empty(self.playback_digest, "playback_digest")
