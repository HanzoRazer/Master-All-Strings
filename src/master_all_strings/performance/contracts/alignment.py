"""Deterministic structural alignment evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
    require_nonnegative_int,
    require_tuple,
    require_unique,
)


class AlignmentStatus(StrEnum):
    MATCHED_EXACT_PITCH = "matched_exact_pitch"
    MATCHED_PITCH_DIFFERENCE = "matched_pitch_difference"
    EXPECTED_NOT_OBSERVED = "expected_not_observed"
    OBSERVED_NOT_EXPECTED = "observed_not_expected"
    UNRESOLVED_CAPTURE = "unresolved_capture"


@dataclass(frozen=True)
class PerformanceAlignmentPolicyV1:
    schema_version: str = "1.0.0"
    early_window_ms: int = 250
    late_window_ms: int = 250
    allow_pitch_mismatch: bool = True
    maximum_pitch_distance_semitones: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != "1.0.0":
            raise PerformanceContractError("unsupported alignment policy")
        require_nonnegative_int(self.early_window_ms, "early_window_ms")
        require_nonnegative_int(self.late_window_ms, "late_window_ms")
        require_nonnegative_int(
            self.maximum_pitch_distance_semitones, "maximum_pitch_distance_semitones"
        )
        if not isinstance(self.allow_pitch_mismatch, bool):
            raise PerformanceContractError("allow_pitch_mismatch must be boolean")


@dataclass(frozen=True)
class AlignedPerformanceEventV1:
    status: AlignmentStatus
    expected_event_id: str | None
    observed_event_id: str | None
    repetition_index: int
    timing_delta_ms: int | None = None
    pitch_delta_semitones: int | None = None
    duration_delta_ms: int | None = None
    velocity_delta: int | None = None
    expected_start_tick: int | None = None
    observed_estimated_tick: int | None = None

    def __post_init__(self) -> None:
        require_nonnegative_int(self.repetition_index, "repetition_index")
        if self.expected_event_id is not None:
            require_identifier(self.expected_event_id, "expected_event_id")
        if self.observed_event_id is not None:
            require_identifier(self.observed_event_id, "observed_event_id")
        if self.expected_event_id is None and self.observed_event_id is None:
            raise PerformanceContractError("alignment outcome must cite evidence")


@dataclass(frozen=True)
class PerformanceAlignmentResultV1:
    schema_version: str
    assignment_id: str
    content_id: str
    performance_session_id: str
    alignment_policy: PerformanceAlignmentPolicyV1
    aligned_events: tuple[AlignedPerformanceEventV1, ...]
    unmatched_expected_ids: tuple[str, ...]
    unmatched_observed_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "1.0.0":
            raise PerformanceContractError("unsupported alignment result")
        for n in ("assignment_id", "content_id", "performance_session_id"):
            require_identifier(getattr(self, n), n)
        require_tuple(self.aligned_events, "aligned_events")
        require_tuple(self.unmatched_expected_ids, "unmatched_expected_ids")
        require_tuple(self.unmatched_observed_ids, "unmatched_observed_ids")
        require_unique(self.unmatched_expected_ids, "unmatched_expected_ids")
        require_unique(self.unmatched_observed_ids, "unmatched_observed_ids")
