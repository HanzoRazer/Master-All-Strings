"""Presentation synchronization (DO-012 / MVP 2B).

Derived state only. ``web/mvp1/transport.js`` remains the sole musical transport
authority; this package describes what it is doing so several teaching surfaces
can follow one clock. See ``docs/architecture/SYNCHRONIZED_TEACHING_TIMELINE.md``.
"""

from __future__ import annotations

from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
    SyncCorrection,
    SynchronizationHealthV1,
    SynchronizationStatus,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError
from master_all_strings.presentation.timeline import (
    anchors_to_payload,
    binding_contains_lesson_time,
    binding_contains_media_time,
    build_teaching_playhead_state,
    build_teaching_timeline_state,
    build_timeline_anchors,
    lesson_time_to_media_time,
    media_time_to_lesson_time,
    resolve_focus_range_seconds,
    seconds_at_tick,
    tick_at_seconds,
    validate_media_timeline_binding,
)

__all__ = [
    "PRESENTATION_SCHEMA_VERSION",
    "MediaSyncMode",
    "MediaTimelineBindingV1",
    "PresentationContractError",
    "SyncCorrection",
    "SynchronizationHealthV1",
    "SynchronizationStatus",
    "TeachingPlayheadStateV1",
    "TeachingTimelineStateV1",
    "TimelineAnchorV1",
    "anchors_to_payload",
    "binding_contains_lesson_time",
    "binding_contains_media_time",
    "build_teaching_playhead_state",
    "build_teaching_timeline_state",
    "build_timeline_anchors",
    "lesson_time_to_media_time",
    "media_time_to_lesson_time",
    "resolve_focus_range_seconds",
    "seconds_at_tick",
    "tick_at_seconds",
    "validate_media_timeline_binding",
]
