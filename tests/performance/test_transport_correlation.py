from __future__ import annotations

import pytest

from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
)
from master_all_strings.performance.transport_correlation import (
    PracticeTransportAnchorV1,
    locate_observed_notes,
)


def _note(time_ns: int) -> ObservedMidiNoteV1:
    return ObservedMidiNoteV1(
        "1.0.0",
        "obs",
        "cap",
        "on",
        "off",
        60,
        90,
        0,
        "dev",
        time_ns,
        time_ns + 10,
        10,
        None,
        ObservedMidiNoteStatus.COMPLETE,
        0,
    )


def test_rate_mapping_calls_core_tick_authority() -> None:
    note = locate_observed_notes(
        (_note(2_000_000_000),),
        (PracticeTransportAnchorV1(1_000_000_000, 1.0, 0.5, 0, True),),
        ticks_per_quarter=480,
        tempo_changes=(TempoChangeV1("1.0.0", 0, 500_000),),
    )[0]
    assert note.practice_onset_seconds == 1.5
    assert note.estimated_start_tick == 1440


def test_seek_and_loop_use_latest_explicit_anchor() -> None:
    anchors = (
        PracticeTransportAnchorV1(0, 0, 1, 0, True),
        PracticeTransportAnchorV1(2_000_000_000, 4, 1.5, 3, True),
    )
    note = locate_observed_notes(
        (_note(3_000_000_000),),
        anchors,
        ticks_per_quarter=480,
        tempo_changes=(TempoChangeV1("1.0.0", 0, 500_000),),
    )[0]
    assert (note.practice_onset_seconds, note.repetition_index) == (5.5, 3)


def test_paused_anchor_does_not_accumulate_time() -> None:
    note = locate_observed_notes(
        (_note(9_000_000_000),),
        (PracticeTransportAnchorV1(1, 2.25, 1, 0, False),),
        ticks_per_quarter=480,
        tempo_changes=(TempoChangeV1("1.0.0", 0, 500_000),),
    )[0]
    assert note.practice_onset_seconds == 2.25


def test_anchor_and_location_fail_closed():
    with pytest.raises(PerformanceContractError):
        PracticeTransportAnchorV1(0, -1, 1, 0, True)
    with pytest.raises(PerformanceContractError):
        PracticeTransportAnchorV1(0, 0, 2, 0, True)
    tempo = (TempoChangeV1("1.0.0", 0, 500_000),)
    with pytest.raises(PerformanceContractError, match="must not be empty"):
        locate_observed_notes((_note(1),), (), ticks_per_quarter=480, tempo_changes=tempo)
    with pytest.raises(PerformanceContractError, match="precedes"):
        locate_observed_notes(
            (_note(1),),
            (PracticeTransportAnchorV1(2, 0, 1, 0, True),),
            ticks_per_quarter=480,
            tempo_changes=tempo,
        )
