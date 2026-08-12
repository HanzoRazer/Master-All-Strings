"""Portable manifest for a completed performance-evidence session."""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.performance.contracts.capture import CaptureCompletionState
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
)


@dataclass(frozen=True)
class PerformanceProvenanceV1:
    producer: str
    producer_version: str
    created_at: str
    latency_compensation_ns: int | None = None

    def __post_init__(self) -> None:
        require_identifier(self.producer, "producer")
        require_identifier(self.producer_version, "producer_version")
        require_identifier(self.created_at, "created_at")
        if self.latency_compensation_ns is not None:
            raise PerformanceContractError("DO-009 does not authorize latency compensation")


@dataclass(frozen=True)
class PerformanceSessionEvidenceV1:
    schema_version: str
    assignment_id: str
    content_id: str
    performance_session_id: str
    capture_id: str
    capture_status: CaptureCompletionState
    raw_capture_ref: str
    observed_events_ref: str
    alignment_ref: str
    input_device_id: str
    provenance: PerformanceProvenanceV1
    evidence_digest: str

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise PerformanceContractError("unsupported session evidence version")
        for name in (
            "assignment_id",
            "content_id",
            "performance_session_id",
            "capture_id",
            "raw_capture_ref",
            "observed_events_ref",
            "alignment_ref",
            "input_device_id",
            "evidence_digest",
        ):
            require_identifier(getattr(self, name), name)
        if not isinstance(self.capture_status, CaptureCompletionState):
            raise PerformanceContractError("capture_status must be a CaptureCompletionState")
        if not self.evidence_digest.startswith("sha256:"):
            raise PerformanceContractError("evidence_digest must be a sha256 digest")
