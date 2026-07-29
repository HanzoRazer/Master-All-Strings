"""Command contracts — every operation a caller may ask of a runtime.

Commands are data, validated at construction. A caller builds one and hands it to the
port; the port never accepts loose arguments. That keeps the neutral vocabulary in one
place and makes an unsupported operation a value a test can assert on.

``PanicCommandV1`` is a first-class command rather than a flag on stop, because a
stuck note must be clearable without ending the session (ADR-0007 transport section).
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_bool,
    require_identifier,
    require_positive_int,
    require_schema_version,
)
from master_all_strings.performance.contracts.session import (
    LoopRegionV1,
    PerformanceSessionConfigV1,
    TransportMode,
)


@dataclass(frozen=True)
class StartRuntimeCommandV1:
    """Start the runtime process and wait for readiness."""

    schema_version: str
    runtime_id: str
    timeout_ms: int

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_positive_int(self.timeout_ms, "timeout_ms")


@dataclass(frozen=True)
class StopRuntimeCommandV1:
    """Stop the runtime.

    ``force`` skips graceful shutdown. Stopping an already-stopped runtime is safe and
    idempotent by contract — recovery paths call it without knowing the current state.
    """

    schema_version: str
    runtime_id: str
    timeout_ms: int
    force: bool = False

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_positive_int(self.timeout_ms, "timeout_ms")
        require_bool(self.force, "force")


@dataclass(frozen=True)
class PrepareSessionCommandV1:
    """Create the prepared session from a validated configuration."""

    schema_version: str
    session_config: PerformanceSessionConfigV1

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.session_config, PerformanceSessionConfigV1):
            raise PerformanceContractError(
                "session_config must be a PerformanceSessionConfigV1"
            )


@dataclass(frozen=True)
class SetTransportCommandV1:
    """Set transport mode, and optionally locate."""

    schema_version: str
    session_id: str
    mode: TransportMode
    position_tick: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        if not isinstance(self.mode, TransportMode):
            raise PerformanceContractError("mode must be a TransportMode")
        if self.position_tick is not None:
            if isinstance(self.position_tick, bool) or not isinstance(self.position_tick, int):
                raise PerformanceContractError("position_tick must be an integer")
            if self.position_tick < 0:
                raise PerformanceContractError("position_tick must be nonnegative")


@dataclass(frozen=True)
class ArmTrackCommandV1:
    """Arm or disarm a track for recording."""

    schema_version: str
    session_id: str
    track_id: str
    armed: bool

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.track_id, "track_id")
        require_bool(self.armed, "armed")


@dataclass(frozen=True)
class StartCaptureCommandV1:
    """Begin capturing on an armed track."""

    schema_version: str
    session_id: str
    capture_id: str
    track_id: str

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.track_id, "track_id")


@dataclass(frozen=True)
class StopCaptureCommandV1:
    """End a capture and close it with a terminal state.

    ``ended_at`` is supplied by the caller rather than read from a clock inside the
    contract, so capture records stay deterministic and testable.
    """

    schema_version: str
    session_id: str
    capture_id: str
    ended_at: str
    cancelled: bool = False

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.ended_at, "ended_at")
        require_bool(self.cancelled, "cancelled")


@dataclass(frozen=True)
class RetrieveCaptureCommandV1:
    """Fetch a capture record.

    A command contract rather than a bare identifier, so retrieval matches every
    other port operation and can later carry session context, a retrieval mode, or a
    provenance check without changing the port's method shape.
    """

    schema_version: str
    capture_id: str
    session_id: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.capture_id, "capture_id")
        if self.session_id is not None:
            require_identifier(self.session_id, "session_id")


@dataclass(frozen=True)
class SelectSynthCommandV1:
    """Load an approved synthesizer by registry identifier.

    Selection is by ``synth_id`` against the approved registry, never by plugin URI or
    filesystem path: unrestricted plugin loading is out of scope, and a synth that is
    not registered cannot be chosen (ADR-0007 D17).
    """

    schema_version: str
    session_id: str
    track_id: str
    synth_id: str
    preset: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.track_id, "track_id")
        require_identifier(self.synth_id, "synth_id")
        if self.preset is not None:
            require_identifier(self.preset, "preset")


@dataclass(frozen=True)
class SetLoopCommandV1:
    """Set or clear the loop region."""

    schema_version: str
    session_id: str
    loop: LoopRegionV1 | None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        if self.loop is not None and not isinstance(self.loop, LoopRegionV1):
            raise PerformanceContractError("loop must be a LoopRegionV1 or None")


@dataclass(frozen=True)
class PanicCommandV1:
    """Silence every sounding note immediately.

    Valid in any state, including with no session prepared. Panic that requires a
    healthy runtime is not panic.
    """

    schema_version: str
    runtime_id: str
    session_id: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        if self.session_id is not None:
            require_identifier(self.session_id, "session_id")
