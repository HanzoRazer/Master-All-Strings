"""Versioned presentation-synchronization contracts (DO-012).

Every record here is *derived* state. None of it owns musical content, mints
canonical identity, or advances time. ``Transport`` remains the sole musical
transport authority; these contracts describe what it is doing so that several
teaching surfaces can follow one clock instead of inventing several.

``canonical_revision_id`` is deliberately absent. Durable score projections
(DO-013) need real revision provenance, and manufacturing a placeholder here
would let a presentation record imply an authority it does not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.presentation.errors import (
    PresentationContractError,
    require_finite_number,
    require_identifier,
    require_nonnegative_int,
    require_nonnegative_number,
    require_schema_version,
    require_tuple,
    require_unique,
)

__all__ = [
    "MEASURED_STATUSES",
    "PRESENTATION_SCHEMA_VERSION",
    "MediaSyncMode",
    "MediaTimelineBindingV1",
    "SyncCorrection",
    "SynchronizationHealthV1",
    "SynchronizationStatus",
    "TeachingPlayheadStateV1",
    "TeachingTimelineStateV1",
    "TimelineAnchorV1",
]

PRESENTATION_SCHEMA_VERSION = "1.0.0"


class MediaSyncMode(StrEnum):
    """Whether a media follower is bound to the shared transport.

    ``DETACHED`` is the MVP 2A behavior and remains fully supported: media
    plays, pauses, seeks, and rates independently. Synchronization is never
    implied by the mere presence of media.
    """

    DETACHED = "detached"
    SYNCHRONIZED = "synchronized"


class SynchronizationStatus(StrEnum):
    """Measured health of one follower relative to the shared transport."""

    SYNCED = "synced"
    DRIFTING = "drifting"
    CORRECTING = "correcting"
    DEGRADED = "degraded"
    DETACHED = "detached"
    UNAVAILABLE = "unavailable"
    OUT_OF_BINDING_RANGE = "out_of_binding_range"


class SyncCorrection(StrEnum):
    """What was done about measured drift."""

    NONE = "none"
    RESAMPLE = "resample"
    HARD_SEEK = "hard_seek"


# Statuses for which a real drift measurement exists. Every other status means
# the follower could not be measured, and fabricating a number for it would turn
# "we do not know" into evidence.
MEASURED_STATUSES: frozenset[SynchronizationStatus] = frozenset(
    {
        SynchronizationStatus.SYNCED,
        SynchronizationStatus.DRIFTING,
        SynchronizationStatus.CORRECTING,
    }
)

# Equal-span tolerance for the affine 1:1 binding check, in seconds.
_SPAN_EQUALITY_TOLERANCE_SECONDS = 1e-9
# Tolerance for re-deriving drift_ms from the reported times, in milliseconds.
_DRIFT_CONSISTENCY_TOLERANCE_MS = 1e-6


def _coerce_enum(enum_cls: type[StrEnum], value: object, field_name: str) -> StrEnum:
    if isinstance(value, enum_cls):
        return value
    if not isinstance(value, str):
        raise PresentationContractError(f"invalid {field_name}: {value!r}")
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise PresentationContractError(f"invalid {field_name}: {value!r}") from exc


@dataclass(frozen=True)
class TimelineAnchorV1:
    """One (tick, seconds) pair authored by Musical Core timing.

    Anchors exist so the browser can report ``position_tick`` without owning a
    second implementation of canonical tick conversion. Between two consecutive
    anchors the tempo is constant by construction, so linear interpolation
    reproduces the Core mapping exactly rather than approximating it.
    """

    schema_version: str
    tick: int
    seconds: float

    SCHEMA_VERSION = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_nonnegative_int(self.tick, "tick")
        require_nonnegative_number(self.seconds, "seconds")


@dataclass(frozen=True)
class TeachingTimelineStateV1:
    """A snapshot of the shared transport, as observed by the coordinator.

    This describes transport state. It does not own it. ``sequence`` increments
    per emitted snapshot so a consumer can detect gaps and order snapshots
    without depending on wall-clock time.
    """

    schema_version: str
    lesson_id: str
    sequence: int
    position_tick: int
    position_seconds: float
    playing: bool
    playback_rate: float
    loop_enabled: bool
    repetition_index: int
    loop_start_tick: int | None = None
    loop_end_tick: int | None = None
    loop_start_seconds: float | None = None
    loop_end_seconds: float | None = None

    SCHEMA_VERSION = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.lesson_id, "lesson_id")
        require_nonnegative_int(self.sequence, "sequence")
        require_nonnegative_int(self.position_tick, "position_tick")
        require_nonnegative_number(self.position_seconds, "position_seconds")
        if not isinstance(self.playing, bool):
            raise PresentationContractError("playing must be a boolean")
        require_finite_number(self.playback_rate, "playback_rate")
        if float(self.playback_rate) <= 0.0:
            raise PresentationContractError("playback_rate must be positive")
        if not isinstance(self.loop_enabled, bool):
            raise PresentationContractError("loop_enabled must be a boolean")
        require_nonnegative_int(self.repetition_index, "repetition_index")
        self._validate_loop_bounds()

    def _validate_loop_bounds(self) -> None:
        loop_fields = (
            self.loop_start_tick,
            self.loop_end_tick,
            self.loop_start_seconds,
            self.loop_end_seconds,
        )
        if not self.loop_enabled:
            if any(value is not None for value in loop_fields):
                raise PresentationContractError(
                    "loop bounds must be absent when loop_enabled is false"
                )
            return
        # An enabled loop without bounds would let a follower silently decide
        # its own repeat range.
        if any(value is None for value in loop_fields):
            raise PresentationContractError(
                "loop_enabled requires loop_start_tick, loop_end_tick, "
                "loop_start_seconds, and loop_end_seconds"
            )
        start_tick = self.loop_start_tick
        end_tick = self.loop_end_tick
        start_seconds = self.loop_start_seconds
        end_seconds = self.loop_end_seconds
        assert start_tick is not None and end_tick is not None
        assert start_seconds is not None and end_seconds is not None
        require_nonnegative_int(start_tick, "loop_start_tick")
        require_nonnegative_int(end_tick, "loop_end_tick")
        require_nonnegative_number(start_seconds, "loop_start_seconds")
        require_nonnegative_number(end_seconds, "loop_end_seconds")
        if end_tick <= start_tick:
            raise PresentationContractError("loop_end_tick must exceed loop_start_tick")
        if float(end_seconds) <= float(start_seconds):
            raise PresentationContractError("loop_end_seconds must exceed loop_start_seconds")


@dataclass(frozen=True)
class TeachingPlayheadStateV1:
    """Score-agnostic playhead: where we are, and which events are sounding.

    Deliberately says nothing about fretboards, TAB, or notation. DO-013 adds
    score projections as further followers of exactly this record.

    ``active_event_ids`` are event IDs that already exist in the lesson
    projection. This layer never creates event identity.
    """

    schema_version: str
    lesson_id: str
    sequence: int
    position_tick: int
    position_seconds: float
    active_event_ids: tuple[str, ...]
    repetition_index: int

    SCHEMA_VERSION = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.lesson_id, "lesson_id")
        require_nonnegative_int(self.sequence, "sequence")
        require_nonnegative_int(self.position_tick, "position_tick")
        require_nonnegative_number(self.position_seconds, "position_seconds")
        require_tuple(self.active_event_ids, "active_event_ids")
        for event_id in self.active_event_ids:
            require_identifier(event_id, "active_event_ids entry")
        require_unique(self.active_event_ids, "active_event_ids")
        require_nonnegative_int(self.repetition_index, "repetition_index")


@dataclass(frozen=True)
class MediaTimelineBindingV1:
    """The explicit lesson-to-media time relationship for one media asset.

    Synchronization is opt-in and declared. There is no inference from titles,
    durations, or filenames: media without a binding cannot be synchronized and
    reports that rather than guessing.

    V1 is affine and 1:1 --
    ``media_time = media_anchor_seconds + (lesson_time - lesson_anchor_seconds)``.

    ``lesson_end_seconds`` / ``media_end_seconds`` bound the region where the
    mapping is claimed to hold. Outside it the follower reports
    ``OUT_OF_BINDING_RANGE`` instead of extrapolating.
    """

    schema_version: str
    binding_id: str
    lesson_id: str
    media_id: str
    sync_mode: MediaSyncMode
    lesson_anchor_seconds: float
    media_anchor_seconds: float
    lesson_end_seconds: float | None = None
    media_end_seconds: float | None = None

    SCHEMA_VERSION = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.binding_id, "binding_id")
        require_identifier(self.lesson_id, "lesson_id")
        require_identifier(self.media_id, "media_id")
        object.__setattr__(
            self, "sync_mode", _coerce_enum(MediaSyncMode, self.sync_mode, "sync_mode")
        )
        require_nonnegative_number(self.lesson_anchor_seconds, "lesson_anchor_seconds")
        require_nonnegative_number(self.media_anchor_seconds, "media_anchor_seconds")
        if self.lesson_end_seconds is not None:
            require_nonnegative_number(self.lesson_end_seconds, "lesson_end_seconds")
            if float(self.lesson_end_seconds) <= float(self.lesson_anchor_seconds):
                raise PresentationContractError(
                    "lesson_end_seconds must exceed lesson_anchor_seconds"
                )
        if self.media_end_seconds is not None:
            require_nonnegative_number(self.media_end_seconds, "media_end_seconds")
            if float(self.media_end_seconds) <= float(self.media_anchor_seconds):
                raise PresentationContractError(
                    "media_end_seconds must exceed media_anchor_seconds"
                )
        # A 1:1 mapping means equal spans. Unequal ends would silently imply the
        # rate warping V1 explicitly does not implement.
        if self.lesson_end_seconds is not None and self.media_end_seconds is not None:
            lesson_span = float(self.lesson_end_seconds) - float(self.lesson_anchor_seconds)
            media_span = float(self.media_end_seconds) - float(self.media_anchor_seconds)
            if abs(lesson_span - media_span) > _SPAN_EQUALITY_TOLERANCE_SECONDS:
                raise PresentationContractError(
                    "lesson and media spans must match under the affine 1:1 V1 mapping; "
                    "time warping is not supported"
                )


@dataclass(frozen=True)
class SynchronizationHealthV1:
    """Measured synchronization health for one follower.

    Drift is reported, not hidden. When a follower cannot be measured -- it is
    detached, unavailable, stalled, or outside its binding range -- ``drift_ms``
    is ``None`` rather than zero, because "no measurement" and "perfectly in
    sync" are different claims.
    """

    schema_version: str
    follower_id: str
    sequence: int
    status: SynchronizationStatus
    expected_time_seconds: float | None = None
    actual_time_seconds: float | None = None
    drift_ms: float | None = None
    last_correction: SyncCorrection | None = None

    SCHEMA_VERSION = PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.follower_id, "follower_id")
        require_nonnegative_int(self.sequence, "sequence")
        object.__setattr__(
            self, "status", _coerce_enum(SynchronizationStatus, self.status, "status")
        )
        if self.last_correction is not None:
            object.__setattr__(
                self,
                "last_correction",
                _coerce_enum(SyncCorrection, self.last_correction, "last_correction"),
            )
        for name in ("expected_time_seconds", "actual_time_seconds"):
            value = getattr(self, name)
            if value is not None:
                require_finite_number(value, name)
        if self.drift_ms is not None:
            require_finite_number(self.drift_ms, "drift_ms")
        self._validate_measurement()

    def _validate_measurement(self) -> None:
        if self.status not in MEASURED_STATUSES:
            if self.drift_ms is not None:
                raise PresentationContractError(
                    f"status {self.status.value} is not a measured status; "
                    "drift_ms must be absent"
                )
            return
        expected = self.expected_time_seconds
        actual = self.actual_time_seconds
        drift = self.drift_ms
        if expected is None or actual is None or drift is None:
            raise PresentationContractError(
                f"status {self.status.value} requires expected_time_seconds, "
                "actual_time_seconds, and drift_ms"
            )
        # The reported drift must be the reported measurement, so a health
        # record cannot claim a status its own numbers contradict.
        implied_ms = (float(actual) - float(expected)) * 1000.0
        if abs(implied_ms - float(drift)) > _DRIFT_CONSISTENCY_TOLERANCE_MS:
            raise PresentationContractError(
                "drift_ms must equal (actual_time_seconds - expected_time_seconds) * 1000"
            )
