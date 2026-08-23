"""Drift measurement and correction policy for media followers (DO-012).

Pure policy. Nothing here touches a media element; it decides *what should be
done* and something else does it. Keeping the thresholds and the classification
in Python means they are declared constants with tests, rather than magic
numbers buried in browser code that nobody can regression-test.

The correction ladder exists because the naive approach -- continuously
assigning ``currentTime`` every frame to keep video glued to the transport --
produces visible stutter and audible artifacts. Small drift is tolerated, medium
drift is absorbed by playback-rate nudging, and only large drift earns a hard
seek.
"""

from __future__ import annotations

from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    SyncCorrection,
    SynchronizationHealthV1,
    SynchronizationStatus,
)
from master_all_strings.presentation.errors import (
    PresentationContractError,
    require_finite_number,
    require_identifier,
    require_nonnegative_int,
)

__all__ = [
    "DRIFT_HARD_SEEK_THRESHOLD_MS",
    "DRIFT_SYNCED_THRESHOLD_MS",
    "build_synchronization_health",
    "calculate_drift_ms",
    "choose_sync_correction",
    "classify_sync_health",
]

# Below this the follower is considered in sync and is left alone. Roughly one
# frame at 24fps: tightening it further would cause corrections a learner cannot
# perceive but can definitely see the side effects of.
DRIFT_SYNCED_THRESHOLD_MS = 40.0

# Above this a hard seek is cheaper than trying to catch up gradually. Between
# the two thresholds the follower is nudged rather than jumped.
DRIFT_HARD_SEEK_THRESHOLD_MS = 150.0


def calculate_drift_ms(*, expected_time_seconds: float, actual_time_seconds: float) -> float:
    """Signed drift in milliseconds: positive means the follower is ahead.

    Sign is preserved because "the video is running early" and "the video is
    running late" call for opposite corrections, and an absolute value would
    throw that away.
    """

    require_finite_number(expected_time_seconds, "expected_time_seconds")
    require_finite_number(actual_time_seconds, "actual_time_seconds")
    return (float(actual_time_seconds) - float(expected_time_seconds)) * 1000.0


def classify_sync_health(drift_ms: float) -> SynchronizationStatus:
    """Map a measured drift onto a status.

    Only ever returns a measured status. Unmeasurable conditions -- detached,
    unavailable, stalled, outside the binding range -- are decided by the caller
    that knows about them, not inferred from a number that does not exist.
    """

    require_finite_number(drift_ms, "drift_ms")
    magnitude = abs(float(drift_ms))
    if magnitude <= DRIFT_SYNCED_THRESHOLD_MS:
        return SynchronizationStatus.SYNCED
    if magnitude <= DRIFT_HARD_SEEK_THRESHOLD_MS:
        return SynchronizationStatus.DRIFTING
    return SynchronizationStatus.CORRECTING


def choose_sync_correction(drift_ms: float) -> SyncCorrection:
    """Decide what to do about a measured drift.

    The bands match :func:`classify_sync_health` exactly, so a follower can
    never be told it is ``SYNCED`` while being handed a ``HARD_SEEK``.
    """

    require_finite_number(drift_ms, "drift_ms")
    magnitude = abs(float(drift_ms))
    if magnitude <= DRIFT_SYNCED_THRESHOLD_MS:
        return SyncCorrection.NONE
    if magnitude <= DRIFT_HARD_SEEK_THRESHOLD_MS:
        return SyncCorrection.RESAMPLE
    return SyncCorrection.HARD_SEEK


def build_synchronization_health(
    *,
    follower_id: str,
    sequence: int,
    expected_time_seconds: float | None,
    actual_time_seconds: float | None,
    status: SynchronizationStatus | None = None,
) -> SynchronizationHealthV1:
    """Assemble a health record, measuring drift only when it is measurable.

    Passing an explicit ``status`` declares an unmeasurable condition (detached,
    unavailable, degraded, out of binding range); the record then carries no
    drift rather than a fabricated zero. Omitting it means "measure this", which
    requires both times.
    """

    require_identifier(follower_id, "follower_id")
    require_nonnegative_int(sequence, "sequence")

    if status is not None and status not in (
        SynchronizationStatus.SYNCED,
        SynchronizationStatus.DRIFTING,
        SynchronizationStatus.CORRECTING,
    ):
        return SynchronizationHealthV1(
            schema_version=PRESENTATION_SCHEMA_VERSION,
            follower_id=follower_id,
            sequence=sequence,
            status=status,
            expected_time_seconds=(
                float(expected_time_seconds) if expected_time_seconds is not None else None
            ),
            actual_time_seconds=(
                float(actual_time_seconds) if actual_time_seconds is not None else None
            ),
            drift_ms=None,
            last_correction=None,
        )

    if expected_time_seconds is None or actual_time_seconds is None:
        raise PresentationContractError(
            "a measured status requires both expected_time_seconds and actual_time_seconds"
        )

    drift_ms = calculate_drift_ms(
        expected_time_seconds=expected_time_seconds,
        actual_time_seconds=actual_time_seconds,
    )
    return SynchronizationHealthV1(
        schema_version=PRESENTATION_SCHEMA_VERSION,
        follower_id=follower_id,
        sequence=sequence,
        status=status or classify_sync_health(drift_ms),
        expected_time_seconds=float(expected_time_seconds),
        actual_time_seconds=float(actual_time_seconds),
        drift_ms=drift_ms,
        last_correction=choose_sync_correction(drift_ms),
    )
