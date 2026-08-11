from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from master_all_strings.core.score.tempo import tempo_from_bpm
from master_all_strings.mvp.errors import PracticePolicyBuildError
from master_all_strings.mvp.practice import (
    PracticeLoopV1,
    build_practice_session_policy,
    loop_ticks_to_seconds,
    validate_practice_loop,
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "resources" / "mvp2" / "schema" / "practice_session_policy_v1.schema.json"


@pytest.mark.parametrize(
    ("start_tick", "end_tick"),
    [(0, 1920), (480, 1440), (480, 960)],
)
def test_valid_full_partial_and_one_event_loops(start_tick: int, end_tick: int) -> None:
    policy = build_practice_session_policy(
        assignment_id="assignment-1",
        content_id="content-1",
        lesson_end_tick=1920,
        loop_enabled=True,
        loop_start_tick=start_tick,
        loop_end_tick=end_tick,
        target_repetitions=3,
    )

    assert policy.loop == PracticeLoopV1(True, start_tick, end_tick, 3)


@pytest.mark.parametrize(
    ("start_tick", "end_tick", "message"),
    [
        (480, 480, "greater than"),
        (-1, 480, "non-negative"),
        (960, 480, "greater than"),
        (0, 1921, "must not exceed"),
    ],
)
def test_invalid_loop_bounds_are_rejected(
    start_tick: int, end_tick: int, message: str
) -> None:
    with pytest.raises(PracticePolicyBuildError, match=message):
        build_practice_session_policy(
            assignment_id="assignment-1",
            content_id="content-1",
            lesson_end_tick=1920,
            loop_enabled=True,
            loop_start_tick=start_tick,
            loop_end_tick=end_tick,
        )


def test_disabled_policy_defaults_to_full_lesson_and_zero_count_in() -> None:
    policy = build_practice_session_policy(
        assignment_id="assignment-1",
        content_id="content-1",
        lesson_end_tick=1920,
    )

    assert policy.loop == PracticeLoopV1(False, 0, 1920)
    assert policy.count_in_bars == 0


@pytest.mark.parametrize("count_in_bars", [0, 1, 2])
def test_count_in_policy_is_preserved(count_in_bars: int) -> None:
    policy = build_practice_session_policy(
        assignment_id="assignment-1",
        content_id="content-1",
        lesson_end_tick=1920,
        count_in_bars=count_in_bars,
    )

    assert policy.count_in_bars == count_in_bars


def test_invalid_count_in_and_repetitions_are_rejected() -> None:
    with pytest.raises(PracticePolicyBuildError, match="0, 1, or 2"):
        build_practice_session_policy(
            assignment_id="assignment-1",
            content_id="content-1",
            lesson_end_tick=1920,
            count_in_bars=3,
        )
    with pytest.raises(PracticePolicyBuildError, match="positive integer"):
        PracticeLoopV1(True, 0, 480, 0)


def test_loop_ticks_convert_through_authoritative_tempo_map() -> None:
    loop = PracticeLoopV1(True, 480, 960)

    assert loop_ticks_to_seconds(
        loop,
        ticks_per_quarter=480,
        tempo_changes=(tempo_from_bpm(120), tempo_from_bpm(60, tick=480)),
    ) == (0.5, 1.5)


def test_loop_conversion_rejects_missing_tempo() -> None:
    with pytest.raises(PracticePolicyBuildError, match="tempo map is required"):
        loop_ticks_to_seconds(
            PracticeLoopV1(True, 0, 480),
            ticks_per_quarter=480,
            tempo_changes=(),
        )


def test_policy_schema_accepts_delivery_shape() -> None:
    policy = build_practice_session_policy(
        assignment_id="assignment-1",
        content_id="content-1",
        lesson_end_tick=1920,
        loop_enabled=True,
        loop_start_tick=480,
        loop_end_tick=960,
        count_in_bars=1,
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(asdict(policy))


def test_validate_loop_rejects_invalid_lesson_end_type() -> None:
    with pytest.raises(PracticePolicyBuildError, match="must be an integer"):
        validate_practice_loop(PracticeLoopV1(True, 0, 480), lesson_end_tick=True)
