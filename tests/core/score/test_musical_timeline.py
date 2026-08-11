"""Tests for Core musical timeline tick ↔ seconds conversion."""

from __future__ import annotations

import pytest

from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.musical_timeline import (
    normalize_tempo_map,
    seconds_to_ticks,
    ticks_to_microseconds,
    ticks_to_seconds,
)
from master_all_strings.core.score.tempo import TempoChangeV1, tempo_from_bpm


def _tempo(tick: int, bpm: float) -> TempoChangeV1:
    return tempo_from_bpm(bpm, tick=tick)


def test_constant_tempo_one_quarter_at_120bpm() -> None:
    tempo = (_tempo(0, 120.0),)
    # 480 ticks at 480 PPQ = one quarter = 0.5 s at 120 BPM
    assert ticks_to_seconds(480, ticks_per_quarter=480, tempo_changes=tempo) == pytest.approx(0.5)
    assert ticks_to_microseconds(480, ticks_per_quarter=480, tempo_changes=tempo) == 500_000


def test_piecewise_tempo_map() -> None:
    tempo = (_tempo(0, 120.0), _tempo(480, 60.0))
    # First quarter at 120 BPM = 0.5 s; next quarter at 60 BPM = 1.0 s; total 1.5 s
    assert ticks_to_seconds(960, ticks_per_quarter=480, tempo_changes=tempo) == pytest.approx(1.5)


def test_missing_tempo_map_rejected() -> None:
    with pytest.raises(ScoreContractError, match="tempo map is required"):
        ticks_to_seconds(0, ticks_per_quarter=480, tempo_changes=())


def test_tempo_not_covering_tick_zero_rejected() -> None:
    with pytest.raises(ScoreContractError, match="tick 0"):
        normalize_tempo_map((_tempo(480, 120.0),))


def test_no_silent_120_bpm_default() -> None:
    with pytest.raises(ScoreContractError, match="refusing to assume"):
        ticks_to_seconds(100, ticks_per_quarter=480, tempo_changes=())


def test_seconds_to_ticks_round_trip_constant() -> None:
    tempo = (_tempo(0, 100.0),)
    for tick in (0, 240, 480, 960, 1920):
        seconds = ticks_to_seconds(tick, ticks_per_quarter=480, tempo_changes=tempo)
        assert seconds_to_ticks(seconds, ticks_per_quarter=480, tempo_changes=tempo) == tick


def test_seconds_to_ticks_piecewise() -> None:
    tempo = (_tempo(0, 120.0), _tempo(480, 60.0))
    seconds = ticks_to_seconds(960, ticks_per_quarter=480, tempo_changes=tempo)
    assert seconds_to_ticks(seconds, ticks_per_quarter=480, tempo_changes=tempo) == 960


def test_negative_seconds_rejected() -> None:
    with pytest.raises(ScoreContractError, match="negative"):
        seconds_to_ticks(-0.1, ticks_per_quarter=480, tempo_changes=(_tempo(0, 120.0),))


def test_normalize_rejects_non_tempo_change() -> None:
    with pytest.raises(ScoreContractError, match="TempoChangeV1"):
        normalize_tempo_map([object()])  # type: ignore[list-item]


def test_seconds_to_ticks_rejects_non_finite() -> None:
    tempo = (_tempo(0, 120.0),)
    with pytest.raises(ScoreContractError, match="finite"):
        seconds_to_ticks(float("nan"), ticks_per_quarter=480, tempo_changes=tempo)
    with pytest.raises(ScoreContractError, match="finite"):
        seconds_to_ticks(True, ticks_per_quarter=480, tempo_changes=tempo)  # type: ignore[arg-type]
