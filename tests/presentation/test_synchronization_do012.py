"""DO-012 drift measurement and correction policy.

The thresholds live in Python rather than in browser code precisely so they can
be regression-tested. The important properties are that the bands are
contiguous, that classification and correction never disagree, and that an
unmeasurable follower reports no measurement rather than a comfortable zero.
"""

from __future__ import annotations

import pytest

from master_all_strings.presentation.contracts import (
    SyncCorrection,
    SynchronizationStatus,
)
from master_all_strings.presentation.errors import PresentationContractError
from master_all_strings.presentation.synchronization import (
    DRIFT_HARD_SEEK_THRESHOLD_MS,
    DRIFT_SYNCED_THRESHOLD_MS,
    build_synchronization_health,
    calculate_drift_ms,
    choose_sync_correction,
    classify_sync_health,
)


def test_thresholds_are_ordered() -> None:
    assert 0 < DRIFT_SYNCED_THRESHOLD_MS < DRIFT_HARD_SEEK_THRESHOLD_MS


# --- drift measurement -------------------------------------------------------


def test_drift_is_positive_when_the_follower_runs_ahead() -> None:
    assert calculate_drift_ms(expected_time_seconds=1.0, actual_time_seconds=1.05) == pytest.approx(
        50.0
    )


def test_drift_is_negative_when_the_follower_runs_behind() -> None:
    """Sign matters: ahead and behind call for opposite corrections."""

    assert calculate_drift_ms(expected_time_seconds=1.0, actual_time_seconds=0.95) == pytest.approx(
        -50.0
    )


def test_drift_is_zero_when_aligned() -> None:
    assert calculate_drift_ms(expected_time_seconds=2.0, actual_time_seconds=2.0) == 0.0


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_times_are_refused(value: float) -> None:
    with pytest.raises(PresentationContractError):
        calculate_drift_ms(expected_time_seconds=value, actual_time_seconds=1.0)


# --- classification ----------------------------------------------------------


@pytest.mark.parametrize(
    ("drift_ms", "status"),
    [
        (0.0, SynchronizationStatus.SYNCED),
        (20.0, SynchronizationStatus.SYNCED),
        (-20.0, SynchronizationStatus.SYNCED),
        (40.0, SynchronizationStatus.SYNCED),
        (40.1, SynchronizationStatus.DRIFTING),
        (75.0, SynchronizationStatus.DRIFTING),
        (-75.0, SynchronizationStatus.DRIFTING),
        (150.0, SynchronizationStatus.DRIFTING),
        (150.1, SynchronizationStatus.CORRECTING),
        (250.0, SynchronizationStatus.CORRECTING),
        (-250.0, SynchronizationStatus.CORRECTING),
    ],
)
def test_classification_bands(drift_ms: float, status: SynchronizationStatus) -> None:
    assert classify_sync_health(drift_ms) is status


@pytest.mark.parametrize(
    ("drift_ms", "correction"),
    [
        (20.0, SyncCorrection.NONE),
        (40.0, SyncCorrection.NONE),
        (75.0, SyncCorrection.RESAMPLE),
        (150.0, SyncCorrection.RESAMPLE),
        (250.0, SyncCorrection.HARD_SEEK),
        (-250.0, SyncCorrection.HARD_SEEK),
    ],
)
def test_correction_bands(drift_ms: float, correction: SyncCorrection) -> None:
    assert choose_sync_correction(drift_ms) is correction


@pytest.mark.parametrize("drift_ms", [0.0, 39.9, 40.0, 40.1, 149.9, 150.0, 150.1, 5_000.0])
def test_status_and_correction_never_disagree(drift_ms: float) -> None:
    """SYNCED must never be paired with a hard seek, in either direction."""

    pairs = {
        SynchronizationStatus.SYNCED: SyncCorrection.NONE,
        SynchronizationStatus.DRIFTING: SyncCorrection.RESAMPLE,
        SynchronizationStatus.CORRECTING: SyncCorrection.HARD_SEEK,
    }
    assert pairs[classify_sync_health(drift_ms)] is choose_sync_correction(drift_ms)


def test_classification_only_returns_measured_statuses() -> None:
    measured = {
        SynchronizationStatus.SYNCED,
        SynchronizationStatus.DRIFTING,
        SynchronizationStatus.CORRECTING,
    }
    for drift_ms in (0.0, 100.0, 10_000.0, -10_000.0):
        assert classify_sync_health(drift_ms) in measured


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_drift_is_refused(value: float) -> None:
    with pytest.raises(PresentationContractError):
        classify_sync_health(value)
    with pytest.raises(PresentationContractError):
        choose_sync_correction(value)


# --- health assembly ---------------------------------------------------------


def test_measured_health_carries_status_drift_and_correction() -> None:
    health = build_synchronization_health(
        follower_id="media:demo",
        sequence=3,
        expected_time_seconds=1.5,
        actual_time_seconds=1.575,
    )
    assert health.status is SynchronizationStatus.DRIFTING
    assert health.drift_ms == pytest.approx(75.0)
    assert health.last_correction is SyncCorrection.RESAMPLE


@pytest.mark.parametrize(
    "status",
    [
        SynchronizationStatus.DEGRADED,
        SynchronizationStatus.DETACHED,
        SynchronizationStatus.UNAVAILABLE,
        SynchronizationStatus.OUT_OF_BINDING_RANGE,
    ],
)
def test_unmeasurable_health_reports_no_drift(status: SynchronizationStatus) -> None:
    """A stalled or out-of-range follower has no measurement, not a zero one."""

    health = build_synchronization_health(
        follower_id="media:demo",
        sequence=4,
        expected_time_seconds=2.0,
        actual_time_seconds=None,
        status=status,
    )
    assert health.status is status
    assert health.drift_ms is None
    assert health.last_correction is None


def test_unmeasurable_health_keeps_whatever_times_it_does_know() -> None:
    health = build_synchronization_health(
        follower_id="media:demo",
        sequence=5,
        expected_time_seconds=3.25,
        actual_time_seconds=None,
        status=SynchronizationStatus.OUT_OF_BINDING_RANGE,
    )
    assert health.expected_time_seconds == 3.25
    assert health.actual_time_seconds is None


def test_measuring_without_both_times_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="requires both"):
        build_synchronization_health(
            follower_id="media:demo",
            sequence=6,
            expected_time_seconds=1.0,
            actual_time_seconds=None,
        )


def test_explicit_measured_status_is_honored() -> None:
    """Callers may assert CORRECTING while a seek is in flight."""

    health = build_synchronization_health(
        follower_id="media:demo",
        sequence=7,
        expected_time_seconds=1.0,
        actual_time_seconds=1.001,
        status=SynchronizationStatus.CORRECTING,
    )
    assert health.status is SynchronizationStatus.CORRECTING
    assert health.drift_ms == pytest.approx(1.0)


def test_blank_follower_id_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="follower_id"):
        build_synchronization_health(
            follower_id=" ",
            sequence=1,
            expected_time_seconds=1.0,
            actual_time_seconds=1.0,
        )


def test_negative_sequence_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="sequence"):
        build_synchronization_health(
            follower_id="media:demo",
            sequence=-1,
            expected_time_seconds=1.0,
            actual_time_seconds=1.0,
        )
