"""Deterministic serialization, validation, and digests for playback plans."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from typing import Any

from master_all_strings.mvp.errors import PlaybackPlanBuildError
from master_all_strings.mvp.playback.models import LessonPlaybackPlanV1

__all__ = [
    "compute_playback_plan_digest",
    "serialize_lesson_playback_plan",
    "to_dict",
    "validate_playback_plan",
    "verify_playback_plan_digest",
]


def _encode(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def to_dict(plan: LessonPlaybackPlanV1) -> dict[str, Any]:
    if not isinstance(plan, LessonPlaybackPlanV1):
        raise PlaybackPlanBuildError("expected LessonPlaybackPlanV1")
    encoded = _encode(plan)
    if not isinstance(encoded, dict):
        raise PlaybackPlanBuildError("playback plan encoding failed")
    return encoded


def serialize_lesson_playback_plan(plan: LessonPlaybackPlanV1) -> str:
    validate_playback_plan(plan)
    verify_playback_plan_digest(plan)
    return json.dumps(to_dict(plan), indent=2, ensure_ascii=False) + "\n"


def compute_playback_plan_digest(plan: LessonPlaybackPlanV1) -> str:
    data = to_dict(plan)
    data.pop("playback_digest", None)
    payload = json.dumps(
        data,
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verify_playback_plan_digest(plan: LessonPlaybackPlanV1) -> None:
    expected = compute_playback_plan_digest(plan)
    if plan.playback_digest != expected:
        raise PlaybackPlanBuildError(
            "playback_digest does not match playback content "
            f"(expected {expected}, got {plan.playback_digest})"
        )


def validate_playback_plan(plan: LessonPlaybackPlanV1) -> None:
    """Recheck relational invariants relied on by the browser scheduler."""

    if plan.timeline.total_ticks == 0:
        raise PlaybackPlanBuildError("playback timeline must contain positive duration")
    if plan.total_seconds <= 0:
        raise PlaybackPlanBuildError("playback plan total_seconds must be positive")
    previous = (-1.0, -1.0, "")
    for event in plan.events:
        current = (event.onset_seconds, event.release_seconds, event.event_id)
        if current < previous:
            raise PlaybackPlanBuildError("playback events are not deterministically ordered")
        previous = current
