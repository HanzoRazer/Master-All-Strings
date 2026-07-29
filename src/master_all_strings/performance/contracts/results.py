"""Result contracts — what a runtime returns.

Results are values, not exceptions. A command that fails returns a result carrying a
fault, so a caller can inspect *why* without unwinding, and so an adapter conformance
test can assert on the reason rather than on an exception type. Exceptions remain for
contract violations — data that should never have been constructed.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.performance.contracts.capture import RawPerformanceCaptureV1
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_bool,
    require_identifier,
    require_nonnegative_int,
    require_schema_version,
    require_tuple,
    require_utc_timestamp,
)
from master_all_strings.performance.contracts.runtime import (
    RuntimeDiagnosticsV1,
    RuntimeFaultV1,
    RuntimeHealthV1,
)


@dataclass(frozen=True)
class RuntimeCommandResultV1:
    """The outcome of a single runtime command."""

    schema_version: str
    command: str
    runtime_id: str
    succeeded: bool
    completed_at: str
    fault: RuntimeFaultV1 | None = None
    detail: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.command, "command")
        require_identifier(self.runtime_id, "runtime_id")
        require_bool(self.succeeded, "succeeded")
        require_utc_timestamp(self.completed_at, "completed_at")
        if self.fault is not None and not isinstance(self.fault, RuntimeFaultV1):
            raise PerformanceContractError("fault must be a RuntimeFaultV1 or None")
        if self.detail is not None:
            require_identifier(self.detail, "detail")
        # A failure without a reason is not actionable, and a success carrying a fault
        # is a contradiction. Both are refused so callers can trust the pair.
        if not self.succeeded and self.fault is None:
            raise PerformanceContractError("a failed command result must carry a fault")
        if self.succeeded and self.fault is not None:
            raise PerformanceContractError("a successful command result must not carry a fault")


@dataclass(frozen=True)
class CaptureResultV1:
    """The outcome of retrieving a capture."""

    schema_version: str
    capture_id: str
    succeeded: bool
    completed_at: str
    capture: RawPerformanceCaptureV1 | None = None
    fault: RuntimeFaultV1 | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.capture_id, "capture_id")
        require_bool(self.succeeded, "succeeded")
        require_utc_timestamp(self.completed_at, "completed_at")
        if self.capture is not None and not isinstance(self.capture, RawPerformanceCaptureV1):
            raise PerformanceContractError("capture must be a RawPerformanceCaptureV1 or None")
        if self.fault is not None and not isinstance(self.fault, RuntimeFaultV1):
            raise PerformanceContractError("fault must be a RuntimeFaultV1 or None")
        if self.succeeded and self.capture is None:
            raise PerformanceContractError("a successful capture result must carry a capture")
        if not self.succeeded and self.fault is None:
            raise PerformanceContractError("a failed capture result must carry a fault")
        if self.capture is not None and self.capture.capture_id != self.capture_id:
            raise PerformanceContractError("capture_id must match the returned capture")


@dataclass(frozen=True)
class PerformanceExportResultV1:
    """The outcome of serializing a performance record."""

    schema_version: str
    export_id: str
    capture_id: str
    succeeded: bool
    completed_at: str
    byte_count: int = 0
    fault: RuntimeFaultV1 | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.export_id, "export_id")
        require_identifier(self.capture_id, "capture_id")
        require_bool(self.succeeded, "succeeded")
        require_utc_timestamp(self.completed_at, "completed_at")
        require_nonnegative_int(self.byte_count, "byte_count")
        if self.fault is not None and not isinstance(self.fault, RuntimeFaultV1):
            raise PerformanceContractError("fault must be a RuntimeFaultV1 or None")
        if not self.succeeded and self.fault is None:
            raise PerformanceContractError("a failed export result must carry a fault")


@dataclass(frozen=True)
class RuntimeDiagnosticResultV1:
    """The outcome of collecting diagnostics."""

    schema_version: str
    runtime_id: str
    succeeded: bool
    completed_at: str
    diagnostics: RuntimeDiagnosticsV1 | None = None
    health: RuntimeHealthV1 | None = None
    fault: RuntimeFaultV1 | None = None
    notes: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_bool(self.succeeded, "succeeded")
        require_utc_timestamp(self.completed_at, "completed_at")
        if self.diagnostics is not None and not isinstance(self.diagnostics, RuntimeDiagnosticsV1):
            raise PerformanceContractError("diagnostics must be a RuntimeDiagnosticsV1 or None")
        if self.health is not None and not isinstance(self.health, RuntimeHealthV1):
            raise PerformanceContractError("health must be a RuntimeHealthV1 or None")
        if self.fault is not None and not isinstance(self.fault, RuntimeFaultV1):
            raise PerformanceContractError("fault must be a RuntimeFaultV1 or None")
        require_tuple(self.notes, "notes")
        for note in self.notes:
            require_identifier(note, "notes entry")
        if self.succeeded and self.diagnostics is None:
            raise PerformanceContractError(
                "a successful diagnostic result must carry diagnostics"
            )
        if not self.succeeded and self.fault is None:
            raise PerformanceContractError("a failed diagnostic result must carry a fault")
