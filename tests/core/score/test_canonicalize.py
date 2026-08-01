"""Canonical ordering (DO-007A A3).

Canonical order is part of canonical identity, so these tests are really about identity:
two callers who submit the same content in a different order must land on the same
revision.
"""

from __future__ import annotations

import pytest

from conftest import make_event  # type: ignore[import-not-found]
from master_all_strings.core.score.canonicalize import (
    canonicalize_events,
    canonicalize_meter_changes,
    canonicalize_tempo_changes,
)
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.tempo import tempo_from_bpm


def meter(tick: int, numerator: int = 4) -> MeterChangeV1:
    return MeterChangeV1(
        schema_version=MeterChangeV1.SCHEMA_VERSION,
        tick=tick,
        numerator=numerator,
        denominator=4,
    )


class TestEventOrdering:
    def test_events_sort_by_start_tick(self) -> None:
        late = make_event(1, start_tick=960)
        early = make_event(0, start_tick=0)
        assert canonicalize_events((late, early)) == (early, late)

    def test_unvoiced_events_lead_within_a_tick(self) -> None:
        voiced = make_event(1, voice_id="soprano")
        unvoiced = make_event(0, voice_id=None)
        assert canonicalize_events((voiced, unvoiced)) == (unvoiced, voiced)

    def test_voices_sort_alphabetically(self) -> None:
        bass = make_event(0, voice_id="bass")
        soprano = make_event(1, voice_id="soprano")
        assert canonicalize_events((soprano, bass)) == (bass, soprano)

    def test_pitch_breaks_a_tick_and_voice_tie(self) -> None:
        high = make_event(1, midi_note=72)
        low = make_event(0, midi_note=60)
        assert canonicalize_events((high, low)) == (low, high)

    def test_duration_breaks_a_pitch_tie(self) -> None:
        long_note = make_event(1, duration_ticks=960)
        short_note = make_event(0, duration_ticks=240)
        assert canonicalize_events((long_note, short_note)) == (short_note, long_note)

    def test_event_id_is_the_final_tiebreaker(self) -> None:
        # Makes the order total: no two distinct events compare equal, so the result
        # never depends on input order.
        second = make_event(2)
        first = make_event(1)
        assert canonicalize_events((second, first)) == (first, second)

    def test_ordering_is_total_over_a_chord(self) -> None:
        chord = tuple(make_event(i, midi_note=60 + i) for i in range(4))
        assert canonicalize_events(tuple(reversed(chord))) == chord

    @pytest.mark.parametrize("seed_order", [(0, 1, 2), (2, 1, 0), (1, 0, 2), (2, 0, 1)])
    def test_every_input_order_yields_one_output(self, seed_order: tuple[int, ...]) -> None:
        events = {i: make_event(i, start_tick=i * 480) for i in range(3)}
        supplied = tuple(events[i] for i in seed_order)
        assert canonicalize_events(supplied) == (events[0], events[1], events[2])

    def test_already_ordered_input_is_unchanged(self) -> None:
        ordered = (make_event(0), make_event(1, start_tick=480))
        assert canonicalize_events(ordered) == ordered

    def test_empty_input_is_empty(self) -> None:
        assert canonicalize_events(()) == ()

    def test_canonicalization_does_not_mutate_the_input(self) -> None:
        original = (make_event(1, start_tick=960), make_event(0))
        canonicalize_events(original)
        assert original[0].start_tick == 960

    def test_duplicate_event_ids_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="event_id"):
            canonicalize_events((make_event(0), make_event(0, start_tick=480)))

    def test_non_event_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="MusicalEvent"):
            canonicalize_events(("x",))  # type: ignore[arg-type]

    def test_list_input_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must be a tuple"):
            canonicalize_events([make_event(0)])  # type: ignore[arg-type]


class TestTempoOrdering:
    def test_tempo_changes_sort_by_tick(self) -> None:
        late = tempo_from_bpm(90.0, tick=960)
        early = tempo_from_bpm(120.0, tick=0)
        assert canonicalize_tempo_changes((late, early)) == (early, late)

    def test_duplicate_tempo_ticks_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="tempo_changes tick"):
            canonicalize_tempo_changes((tempo_from_bpm(120.0), tempo_from_bpm(90.0)))

    def test_non_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="TempoChangeV1"):
            canonicalize_tempo_changes((1,))  # type: ignore[arg-type]

    def test_list_input_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must be a tuple"):
            canonicalize_tempo_changes([tempo_from_bpm(120.0)])  # type: ignore[arg-type]

    def test_empty_input_is_empty(self) -> None:
        assert canonicalize_tempo_changes(()) == ()


class TestMeterOrdering:
    def test_meter_changes_sort_by_tick(self) -> None:
        late = meter(3840, numerator=3)
        early = meter(0)
        assert canonicalize_meter_changes((late, early)) == (early, late)

    def test_duplicate_meter_ticks_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="meter_changes tick"):
            canonicalize_meter_changes((meter(0), meter(0, numerator=3)))

    def test_non_meter_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="MeterChangeV1"):
            canonicalize_meter_changes(("4/4",))  # type: ignore[arg-type]

    def test_list_input_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must be a tuple"):
            canonicalize_meter_changes([meter(0)])  # type: ignore[arg-type]

    def test_empty_input_is_empty(self) -> None:
        assert canonicalize_meter_changes(()) == ()
