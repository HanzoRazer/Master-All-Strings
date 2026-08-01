"""Tick-grid conversion (DO-007A A3).

The conversion is the one place DO-007 turns continuous performance time into discrete
canonical time, so it is the one place a musical claim could be smuggled in. These tests
pin down that it does arithmetic and nothing else.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.provenance import RoundingPolicy
from master_all_strings.core.score.tempo import tempo_from_bpm
from master_all_strings.core.score.timing import (
    DEFAULT_TICKS_PER_QUARTER,
    convert_duration,
    convert_elapsed,
    divide_round_half_away_from_zero,
    nanoseconds_to_ticks,
    require_convertible_tempo,
    ticks_to_nanoseconds,
)

# 120 BPM.
MPQ_120 = 500_000
NS_PER_QUARTER_AT_120 = 500_000_000


class TestRoundingRule:
    """Halves round away from zero, and the rule is stated rather than inherited."""

    @pytest.mark.parametrize(
        ("numerator", "denominator", "expected"),
        [
            (0, 2, 0),
            (1, 2, 1),  # 0.5 -> 1, NOT 0 as Python's round() would give
            (2, 2, 1),
            (3, 2, 2),  # 1.5 -> 2
            (5, 2, 3),  # 2.5 -> 3, NOT 2
            (4, 3, 1),
            (5, 3, 2),
            (-1, 2, -1),  # -0.5 -> -1, away from zero
            (-3, 2, -2),
            (-5, 2, -3),
        ],
    )
    def test_division_rounds_half_away_from_zero(
        self, numerator: int, denominator: int, expected: int
    ) -> None:
        assert divide_round_half_away_from_zero(numerator, denominator) == expected

    def test_the_rule_differs_from_pythons_round(self) -> None:
        # Python uses banker's rounding, so round(0.5) == 0 and round(2.5) == 2. An
        # identity built on that would be near-impossible to reimplement correctly.
        assert round(0.5) == 0
        assert divide_round_half_away_from_zero(1, 2) == 1
        assert round(2.5) == 2
        assert divide_round_half_away_from_zero(5, 2) == 3

    def test_zero_denominator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="denominator"):
            divide_round_half_away_from_zero(1, 0)

    def test_negative_denominator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="denominator"):
            divide_round_half_away_from_zero(1, -2)

    def test_non_integer_numerator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="numerator"):
            divide_round_half_away_from_zero(1.5, 2)  # type: ignore[arg-type]

    def test_bool_numerator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="numerator"):
            divide_round_half_away_from_zero(True, 2)  # type: ignore[arg-type]


class TestExactConversions:
    def test_one_quarter_at_120_bpm_is_960_ticks(self) -> None:
        assert (
            nanoseconds_to_ticks(NS_PER_QUARTER_AT_120, microseconds_per_quarter=MPQ_120) == 960
        )

    def test_zero_elapsed_is_tick_zero(self) -> None:
        assert nanoseconds_to_ticks(0, microseconds_per_quarter=MPQ_120) == 0

    @pytest.mark.parametrize(
        ("quarters", "expected_ticks"),
        [(1, 960), (2, 1920), (4, 3840), (8, 7680)],
    )
    def test_whole_quarters_convert_exactly(self, quarters: int, expected_ticks: int) -> None:
        elapsed = NS_PER_QUARTER_AT_120 * quarters
        assert nanoseconds_to_ticks(elapsed, microseconds_per_quarter=MPQ_120) == expected_ticks

    def test_eighth_note_at_120_bpm(self) -> None:
        assert (
            nanoseconds_to_ticks(NS_PER_QUARTER_AT_120 // 2, microseconds_per_quarter=MPQ_120)
            == 480
        )

    def test_round_trip_of_an_exact_tick(self) -> None:
        ns = ticks_to_nanoseconds(960, microseconds_per_quarter=MPQ_120)
        assert ns == NS_PER_QUARTER_AT_120
        assert nanoseconds_to_ticks(ns, microseconds_per_quarter=MPQ_120) == 960

    def test_tempo_change_scales_ticks(self) -> None:
        # At 60 BPM a quarter is twice as long, so the same elapsed time is half the
        # ticks.
        mpq_60 = tempo_from_bpm(60.0).microseconds_per_quarter
        assert nanoseconds_to_ticks(NS_PER_QUARTER_AT_120, microseconds_per_quarter=mpq_60) == 480

    def test_ppq_scales_ticks(self) -> None:
        assert (
            nanoseconds_to_ticks(
                NS_PER_QUARTER_AT_120, ticks_per_quarter=480, microseconds_per_quarter=MPQ_120
            )
            == 480
        )


class TestFractionalConversion:
    def test_one_tick_at_120_bpm_is_about_half_a_millisecond(self) -> None:
        # Establishes the scale of the residue: rounding is numerical, not musical.
        one_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120)
        assert one_tick_ns == 520833  # ~0.52 ms
        assert one_tick_ns < 1_000_000

    def test_just_over_half_a_tick_rounds_up(self) -> None:
        half_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120) // 2
        assert nanoseconds_to_ticks(half_tick_ns + 1000, microseconds_per_quarter=MPQ_120) == 1

    def test_just_under_half_a_tick_rounds_down(self) -> None:
        half_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120) // 2
        assert nanoseconds_to_ticks(half_tick_ns - 1000, microseconds_per_quarter=MPQ_120) == 0

    def test_conversion_reports_its_residue(self) -> None:
        conversion = convert_elapsed(NS_PER_QUARTER_AT_120 + 1000, microseconds_per_quarter=MPQ_120)
        assert conversion.ticks == 960
        assert conversion.rounding_delta_ns == 1000
        assert conversion.is_exact is False

    def test_exact_conversion_has_no_residue(self) -> None:
        conversion = convert_elapsed(NS_PER_QUARTER_AT_120, microseconds_per_quarter=MPQ_120)
        assert conversion.rounding_delta_ns == 0
        assert conversion.is_exact is True

    def test_residue_is_signed(self) -> None:
        # Rounding up means the tick sits later than the event, so the delta is
        # negative. Callers can tell which way the arithmetic went.
        one_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120)
        late = convert_elapsed(one_tick_ns - 1000, microseconds_per_quarter=MPQ_120)
        assert late.ticks == 1
        assert late.rounding_delta_ns == -1000

    def test_conversion_records_its_basis(self) -> None:
        conversion = convert_elapsed(NS_PER_QUARTER_AT_120, microseconds_per_quarter=MPQ_120)
        assert conversion.ticks_per_quarter == DEFAULT_TICKS_PER_QUARTER
        assert conversion.microseconds_per_quarter == MPQ_120
        assert conversion.rounding_policy is RoundingPolicy.ROUND_HALF_AWAY_FROM_ZERO


class TestNoMusicalQuantization:
    def test_an_off_grid_note_stays_off_grid(self) -> None:
        # 30 ms late at 120 BPM. A quantizer would snap this to 960; tick-grid rounding
        # must not.
        elapsed = NS_PER_QUARTER_AT_120 + 30_000_000
        ticks = nanoseconds_to_ticks(elapsed, microseconds_per_quarter=MPQ_120)
        assert ticks == 1018
        assert ticks != 960

    def test_nothing_snaps_to_a_beat(self) -> None:
        beat_ticks = DEFAULT_TICKS_PER_QUARTER
        for offset_ms in (5, 15, 40, 90):
            elapsed = NS_PER_QUARTER_AT_120 + offset_ms * 1_000_000
            ticks = nanoseconds_to_ticks(elapsed, microseconds_per_quarter=MPQ_120)
            assert ticks % beat_ticks != 0, offset_ms

    def test_a_slightly_early_note_stays_early(self) -> None:
        elapsed = NS_PER_QUARTER_AT_120 - 20_000_000
        assert nanoseconds_to_ticks(elapsed, microseconds_per_quarter=MPQ_120) < 960


class TestRejectedInputs:
    def test_negative_elapsed_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must not be negative"):
            nanoseconds_to_ticks(-1, microseconds_per_quarter=MPQ_120)

    def test_event_before_capture_origin_rejected(self) -> None:
        # An event earlier than the origin is a pairing or origin defect upstream; it
        # must not be absorbed as tick 0.
        with pytest.raises(ScoreContractError, match="cannot precede the capture origin"):
            nanoseconds_to_ticks(-500, microseconds_per_quarter=MPQ_120)

    def test_missing_tempo_rejected(self) -> None:
        # Silently assuming 120 BPM would put a fabricated tempo into the digest.
        with pytest.raises(ScoreContractError, match="refusing to assume a default"):
            require_convertible_tempo(None)

    def test_zero_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="microseconds_per_quarter"):
            require_convertible_tempo(0)

    def test_negative_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="microseconds_per_quarter"):
            require_convertible_tempo(-500_000)

    def test_non_finite_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="finite"):
            require_convertible_tempo(float("inf"))  # type: ignore[arg-type]

    def test_nan_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="finite"):
            require_convertible_tempo(float("nan"))  # type: ignore[arg-type]

    def test_float_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must be an integer"):
            require_convertible_tempo(500_000.5)  # type: ignore[arg-type]

    def test_bool_tempo_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must be an integer"):
            require_convertible_tempo(True)  # type: ignore[arg-type]

    def test_non_integer_elapsed_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="elapsed_ns"):
            nanoseconds_to_ticks(1.5, microseconds_per_quarter=MPQ_120)  # type: ignore[arg-type]

    def test_zero_ppq_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="ticks_per_quarter"):
            nanoseconds_to_ticks(0, ticks_per_quarter=0, microseconds_per_quarter=MPQ_120)


class TestDurationConversion:
    def test_a_quarter_note_duration(self) -> None:
        conversion = convert_duration(0, NS_PER_QUARTER_AT_120, microseconds_per_quarter=MPQ_120)
        assert conversion.ticks == 960

    def test_duration_is_measured_from_onset(self) -> None:
        # Offsetting both ends by the same amount must not change the duration.
        offset = 12_345_678
        conversion = convert_duration(
            offset, offset + NS_PER_QUARTER_AT_120, microseconds_per_quarter=MPQ_120
        )
        assert conversion.ticks == 960

    def test_release_before_onset_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="must not precede onset_ns"):
            convert_duration(1000, 500, microseconds_per_quarter=MPQ_120)

    def test_sub_tick_duration_is_rejected_not_widened(self) -> None:
        # MusicalEvent requires a positive duration, and inflating a sub-tick note
        # would invent length the performance did not contain.
        with pytest.raises(ScoreContractError, match="DURATION_BELOW_ONE_TICK"):
            convert_duration(0, 1000, microseconds_per_quarter=MPQ_120)

    def test_zero_length_note_is_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="DURATION_BELOW_ONE_TICK"):
            convert_duration(5000, 5000, microseconds_per_quarter=MPQ_120)

    def test_exactly_one_tick_is_accepted(self) -> None:
        one_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120)
        assert convert_duration(0, one_tick_ns, microseconds_per_quarter=MPQ_120).ticks == 1

    def test_duration_rounding_to_one_tick_is_accepted(self) -> None:
        one_tick_ns = ticks_to_nanoseconds(1, microseconds_per_quarter=MPQ_120)
        conversion = convert_duration(
            0, one_tick_ns - 1000, microseconds_per_quarter=MPQ_120
        )
        assert conversion.ticks == 1


class TestDeterminism:
    def test_repeated_conversion_is_identical(self) -> None:
        first = convert_elapsed(123_456_789, microseconds_per_quarter=MPQ_120)
        second = convert_elapsed(123_456_789, microseconds_per_quarter=MPQ_120)
        assert first == second

    def test_no_true_division_in_the_conversion_path(self) -> None:
        # Float arithmetic would make the conversion platform-dependent, and the
        # revision digest depends on it. Checked against the parsed tree rather than
        # the source text, so a docstring mentioning "/" cannot fail or pass this.
        import ast
        import inspect
        import textwrap

        from master_all_strings.core.score import timing

        for function in (
            timing.nanoseconds_to_ticks,
            timing.ticks_to_nanoseconds,
            timing.divide_round_half_away_from_zero,
        ):
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            divisions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
            ]
            assert divisions == [], f"{function.__name__} uses true division"

    def test_conversion_is_pure(self) -> None:
        conversion = convert_elapsed(999, microseconds_per_quarter=MPQ_120)
        assert convert_elapsed(999, microseconds_per_quarter=MPQ_120) == conversion
