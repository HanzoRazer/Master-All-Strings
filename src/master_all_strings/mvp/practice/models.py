"""Delivery models for practice-loop behavior."""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.mvp.errors import PracticePolicyBuildError

__all__ = [
    "PRACTICE_SESSION_POLICY_SCHEMA_VERSION",
    "PracticeLoopV1",
    "PracticeSessionPolicyV1",
]

PRACTICE_SESSION_POLICY_SCHEMA_VERSION = "1.0.0"


def _require_tick(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PracticePolicyBuildError(f"{field} must be a non-negative integer")


@dataclass(frozen=True)
class PracticeLoopV1:
    enabled: bool
    start_tick: int
    end_tick: int
    target_repetitions: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise PracticePolicyBuildError("loop enabled must be a boolean")
        _require_tick(self.start_tick, "loop start_tick")
        _require_tick(self.end_tick, "loop end_tick")
        if self.end_tick <= self.start_tick:
            raise PracticePolicyBuildError("loop end_tick must be greater than start_tick")
        if self.target_repetitions is not None and (
            isinstance(self.target_repetitions, bool)
            or not isinstance(self.target_repetitions, int)
            or self.target_repetitions <= 0
        ):
            raise PracticePolicyBuildError(
                "target_repetitions must be a positive integer when provided"
            )


@dataclass(frozen=True)
class PracticeSessionPolicyV1:
    schema_version: str
    assignment_id: str
    content_id: str
    lesson_end_tick: int
    loop: PracticeLoopV1
    count_in_bars: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != PRACTICE_SESSION_POLICY_SCHEMA_VERSION:
            raise PracticePolicyBuildError(
                f"schema_version must be {PRACTICE_SESSION_POLICY_SCHEMA_VERSION!r}"
            )
        for field, value in (
            ("assignment_id", self.assignment_id),
            ("content_id", self.content_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise PracticePolicyBuildError(f"{field} must be a non-empty string")
        _require_tick(self.lesson_end_tick, "lesson_end_tick")
        if self.lesson_end_tick == 0:
            raise PracticePolicyBuildError("lesson_end_tick must be positive")
        if not isinstance(self.loop, PracticeLoopV1):
            raise PracticePolicyBuildError("loop must be PracticeLoopV1")
        if self.loop.end_tick > self.lesson_end_tick:
            raise PracticePolicyBuildError("loop end_tick must not exceed lesson_end_tick")
        if self.count_in_bars not in (0, 1, 2):
            raise PracticePolicyBuildError("count_in_bars must be 0, 1, or 2")
