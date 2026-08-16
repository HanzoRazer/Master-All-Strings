from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.performance.alignment import align_performance
from master_all_strings.performance.contracts.alignment import (
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
)


def note(i: int, pitch: int, sec: float, rep: int = 0) -> ObservedMidiNoteV1:
    return ObservedMidiNoteV1(
        "1.0.0",
        f"o{i}",
        "c",
        f"on{i}",
        f"off{i}",
        pitch,
        90,
        0,
        "d",
        i,
        i + 1,
        1,
        None,
        ObservedMidiNoteStatus.COMPLETE,
        rep,
        sec,
        round(sec * 960),
    )


def run(obs, *, reps=1, allow=True):
    expected = (MusicalEvent("e1", 60, 0, 480, 80), MusicalEvent("e2", 62, 480, 480, 80))
    return align_performance(
        assignment_id="a",
        content_id="c",
        performance_session_id="s",
        expected=expected,
        observed=tuple(obs),
        policy=PerformanceAlignmentPolicyV1(allow_pitch_mismatch=allow),
        ticks_per_quarter=480,
        tempo_changes=(TempoChangeV1("1.0.0", 0, 500000),),
        repetition_count=reps,
    )


def test_exact_wrong_missing_extra_and_determinism():
    r = run((note(1, 60, 0), note(2, 63, 0.5), note(3, 70, 2)))
    assert [x.status for x in r.aligned_events] == [
        AlignmentStatus.MATCHED_EXACT_PITCH,
        AlignmentStatus.MATCHED_PITCH_DIFFERENCE,
        AlignmentStatus.OBSERVED_NOT_EXPECTED,
    ]
    assert r == run((note(1, 60, 0), note(2, 63, 0.5), note(3, 70, 2)))


def test_policy_can_leave_pitch_difference_unmatched():
    r = run((note(1, 61, 0),), allow=False)
    assert r.unmatched_expected_ids == ("e1@0", "e2@0") and r.unmatched_observed_ids == ("o1",)


def test_loop_identity_keeps_repetitions_distinct():
    r = run(
        (note(1, 60, 0, 0), note(2, 62, 0.5, 0), note(3, 60, 0, 1), note(4, 62, 0.5, 1)), reps=2
    )
    assert len(r.aligned_events) == 4


def test_policy_and_result_reject_invalid_contract_shapes():
    with pytest.raises(PerformanceContractError):
        PerformanceAlignmentPolicyV1(schema_version="2")
    with pytest.raises(PerformanceContractError):
        PerformanceAlignmentPolicyV1(early_window_ms=-1)
    with pytest.raises(PerformanceContractError):
        PerformanceAlignmentPolicyV1(allow_pitch_mismatch=1)  # type: ignore[arg-type]
    with pytest.raises(PerformanceContractError):
        PerformanceAlignmentResultV1("2", "a", "c", "s", PerformanceAlignmentPolicyV1(), (), (), ())
