"""Practice-loop validation and authoritative tick conversion."""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.mvp.errors import PracticePolicyBuildError
from master_all_strings.mvp.practice.models import (
    PRACTICE_SESSION_POLICY_SCHEMA_VERSION,
    PracticeLoopV1,
    PracticeSessionPolicyV1,
)

__all__ = [
    "build_practice_session_policy",
    "loop_ticks_to_seconds",
    "validate_practice_loop",
]


def validate_practice_loop(loop: PracticeLoopV1, *, lesson_end_tick: int) -> None:
    """Reject persisted loop bounds rather than silently clamping them."""

    if isinstance(lesson_end_tick, bool) or not isinstance(lesson_end_tick, int):
        raise PracticePolicyBuildError("lesson_end_tick must be an integer")
    if lesson_end_tick <= 0:
        raise PracticePolicyBuildError("lesson_end_tick must be positive")
    if loop.end_tick > lesson_end_tick:
        raise PracticePolicyBuildError("loop end_tick must not exceed lesson_end_tick")


def build_practice_session_policy(
    *,
    assignment_id: str,
    content_id: str,
    lesson_end_tick: int,
    loop_enabled: bool = False,
    loop_start_tick: int | None = None,
    loop_end_tick: int | None = None,
    count_in_bars: int | None = None,
    target_repetitions: int | None = None,
) -> PracticeSessionPolicyV1:
    """Normalize lesson intent into a complete, validated runtime policy."""

    start_tick = 0 if loop_start_tick is None else loop_start_tick
    end_tick = lesson_end_tick if loop_end_tick is None else loop_end_tick
    loop = PracticeLoopV1(
        enabled=loop_enabled,
        start_tick=start_tick,
        end_tick=end_tick,
        target_repetitions=target_repetitions,
    )
    validate_practice_loop(loop, lesson_end_tick=lesson_end_tick)
    return PracticeSessionPolicyV1(
        schema_version=PRACTICE_SESSION_POLICY_SCHEMA_VERSION,
        assignment_id=assignment_id,
        content_id=content_id,
        lesson_end_tick=lesson_end_tick,
        loop=loop,
        count_in_bars=0 if count_in_bars is None else count_in_bars,
    )


def loop_ticks_to_seconds(
    loop: PracticeLoopV1,
    *,
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
) -> tuple[float, float]:
    """Convert canonical loop bounds using Musical Core's timeline authority."""

    try:
        return (
            ticks_to_seconds(
                loop.start_tick,
                ticks_per_quarter=ticks_per_quarter,
                tempo_changes=tempo_changes,
            ),
            ticks_to_seconds(
                loop.end_tick,
                ticks_per_quarter=ticks_per_quarter,
                tempo_changes=tempo_changes,
            ),
        )
    except (ScoreContractError, ValueError, TypeError) as exc:
        raise PracticePolicyBuildError(f"unable to convert loop bounds: {exc}") from exc
