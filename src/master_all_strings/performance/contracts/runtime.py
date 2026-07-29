"""Runtime identity, capability, configuration, and health contracts.

Every name here is runtime-neutral. No Ardour type, field, or vocabulary appears in
this module or may cross ``PerformanceRuntimePort`` (ADR-0007 D2, enforced by
``tests/performance/test_engine_boundaries.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_bool,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_positive_int,
    require_schema_version,
    require_tuple,
    require_unique,
    require_utc_timestamp,
)

# Sample rates a runtime is expected to honour. Constrained rather than open because
# an unsupported rate is a configuration error we can catch before a device does.
SUPPORTED_SAMPLE_RATES = (44100, 48000, 88200, 96000)

# Buffer sizes are powers of two by convention across audio backends. Small buffers
# mean lower latency and more underruns; the acceptable floor on target hardware is
# UNMEASURED, so the contract permits the full conventional range and leaves the
# product decision to measured evidence.
SUPPORTED_BUFFER_FRAMES = (16, 32, 64, 128, 256, 512, 1024, 2048)


class RuntimeKind(StrEnum):
    """Which family of runtime an adapter drives.

    ``FAKE`` is first-class, not a test artifact bolted on: it is the adapter that
    proves the architecture without hardware, and it ships in the package.
    """

    FAKE = "fake"
    ARDOUR = "ardour"
    LIGHTWEIGHT = "lightweight"


class RuntimeState(StrEnum):
    """Lifecycle state of a runtime, per the ADR-0007 readiness state machine."""

    OFF = "off"
    STARTING = "starting"
    PROBING = "probing"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"


class SubsystemState(StrEnum):
    """State of one runtime subsystem.

    Health is reported per subsystem because a single aggregate boolean cannot
    distinguish "no MIDI device" from "synth failed to load", and those need
    different responses (ADR-0007 §6.4).
    """

    UNKNOWN = "unknown"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    FAULTED = "faulted"


class RuntimeCapability(StrEnum):
    """A capability a runtime may or may not provide.

    Runtimes differ: a lightweight practice runtime will never offer multitrack or
    mixdown, and a studio runtime need not offer a tuner. Callers discover
    capabilities rather than assuming a uniform feature set.
    """

    TRANSPORT = "transport"
    MIDI_CAPTURE = "midi_capture"
    SYNTH_HOSTING = "synth_hosting"
    METRONOME = "metronome"
    LOOPING = "looping"
    PANIC = "panic"
    DIAGNOSTICS = "diagnostics"
    MULTITRACK = "multitrack"
    AUTOMATION = "automation"
    MIXDOWN = "mixdown"
    SESSION_RECOVERY = "session_recovery"


class FaultCode(StrEnum):
    """Why a runtime operation failed.

    A closed vocabulary: a caller must be able to branch on the reason, and a free
    string cannot be branched on reliably.
    """

    STARTUP_TIMEOUT = "startup_timeout"
    HEALTH_TIMEOUT = "health_timeout"
    SHUTDOWN_TIMEOUT = "shutdown_timeout"
    EXECUTABLE_MISSING = "executable_missing"
    SESSION_TEMPLATE_MISSING = "session_template_missing"
    CONTROL_ENDPOINT_UNAVAILABLE = "control_endpoint_unavailable"
    UNSUPPORTED_RUNTIME_VERSION = "unsupported_runtime_version"
    MIDI_INPUT_MISSING = "midi_input_missing"
    AUDIO_OUTPUT_MISSING = "audio_output_missing"
    SYNTH_MISSING = "synth_missing"
    SYNTH_LOAD_FAILED = "synth_load_failed"
    SYNTH_LOAD_TIMEOUT = "synth_load_timeout"
    RUNTIME_CRASHED = "runtime_crashed"
    MALFORMED_MIDI_EVENT = "malformed_midi_event"
    STUCK_NOTE = "stuck_note"
    PANIC_FAILED = "panic_failed"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    INVALID_STATE = "invalid_state"


@dataclass(frozen=True)
class RuntimeFaultV1:
    """A single runtime failure, attributable and explicit.

    Faults attach to the record they affected — a capture keeps the fault that
    interrupted it — so a failure is never inferred later from a missing value.
    """

    schema_version: str
    fault_id: str
    code: FaultCode
    subsystem: str
    detail: str
    occurred_at: str
    recoverable: bool

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.fault_id, "fault_id")
        if not isinstance(self.code, FaultCode):
            raise PerformanceContractError("code must be a FaultCode")
        require_identifier(self.subsystem, "subsystem")
        require_identifier(self.detail, "detail")
        require_utc_timestamp(self.occurred_at, "occurred_at")
        require_bool(self.recoverable, "recoverable")


@dataclass(frozen=True)
class RuntimeIdentityV1:
    """Who the runtime is, and whether we are allowed to talk to it.

    ``version_supported`` is stored rather than derived at read time so a caller
    cannot accidentally proceed against an unsupported major by forgetting to check.
    """

    schema_version: str
    runtime_id: str
    runtime_kind: RuntimeKind
    reported_version: str | None
    version_policy: str
    version_supported: bool

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        if not isinstance(self.runtime_kind, RuntimeKind):
            raise PerformanceContractError("runtime_kind must be a RuntimeKind")
        require_optional_identifier(self.reported_version, "reported_version")
        require_identifier(self.version_policy, "version_policy")
        require_bool(self.version_supported, "version_supported")
        # An unknown version cannot be a supported one. Ardour 9.7 exposes no version
        # over OSC (GAP-002), so "unknown" is a real state, and it must not read as OK.
        if self.reported_version is None and self.version_supported:
            raise PerformanceContractError(
                "version_supported cannot be true while reported_version is unresolved"
            )


@dataclass(frozen=True)
class RuntimeCapabilitySetV1:
    """What a runtime can actually do.

    Held as a sorted tuple rather than a set so serialization is deterministic.
    """

    schema_version: str
    runtime_id: str
    capabilities: tuple[RuntimeCapability, ...]

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_tuple(self.capabilities, "capabilities")
        for cap in self.capabilities:
            if not isinstance(cap, RuntimeCapability):
                raise PerformanceContractError("capabilities must contain RuntimeCapability values")
        require_unique(self.capabilities, "capabilities")

    def supports(self, capability: RuntimeCapability) -> bool:
        """Whether this runtime provides ``capability``."""
        return capability in self.capabilities


@dataclass(frozen=True)
class RuntimeHealthV1:
    """Per-subsystem runtime health.

    Seven subsystems are reported separately and deliberately (ADR-0007 §6.4). A
    single boolean would collapse "MIDI device unplugged" and "synth crashed" into
    one indistinguishable failure.
    """

    schema_version: str
    runtime_id: str
    checked_at: str
    state: RuntimeState
    process: SubsystemState
    audio_backend: SubsystemState
    audio_output: SubsystemState
    midi_input: SubsystemState
    synth: SubsystemState
    session: SubsystemState
    capture: SubsystemState
    faults: tuple[RuntimeFaultV1, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    SUBSYSTEM_FIELDS = (
        "process",
        "audio_backend",
        "audio_output",
        "midi_input",
        "synth",
        "session",
        "capture",
    )

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_utc_timestamp(self.checked_at, "checked_at")
        if not isinstance(self.state, RuntimeState):
            raise PerformanceContractError("state must be a RuntimeState")
        for name in self.SUBSYSTEM_FIELDS:
            if not isinstance(getattr(self, name), SubsystemState):
                raise PerformanceContractError(f"{name} must be a SubsystemState")
        require_tuple(self.faults, "faults")
        for fault in self.faults:
            if not isinstance(fault, RuntimeFaultV1):
                raise PerformanceContractError("faults must contain RuntimeFaultV1 values")
        # READY is a claim about every subsystem, so it cannot be asserted while one
        # of them is not ready. Without this, a caller could report READY and then
        # fail on the first command.
        if self.state is RuntimeState.READY and not self.all_subsystems_ready():
            raise PerformanceContractError(
                "state READY requires every subsystem to be READY; "
                f"blocking: {list(self.blocking_subsystems())}"
            )

    def all_subsystems_ready(self) -> bool:
        """Whether every reported subsystem is ``READY``."""
        return not self.blocking_subsystems()

    def blocking_subsystems(self) -> tuple[str, ...]:
        """Names of subsystems that are not ``READY``, in declaration order."""
        return tuple(
            name
            for name in self.SUBSYSTEM_FIELDS
            if getattr(self, name) is not SubsystemState.READY
        )


@dataclass(frozen=True)
class RuntimeReadinessV1:
    """Whether the runtime is usable, and what is stopping it if not."""

    schema_version: str
    runtime_id: str
    ready: bool
    health: RuntimeHealthV1
    blocking_subsystems: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_bool(self.ready, "ready")
        if not isinstance(self.health, RuntimeHealthV1):
            raise PerformanceContractError("health must be a RuntimeHealthV1")
        require_tuple(self.blocking_subsystems, "blocking_subsystems")
        if self.ready and self.blocking_subsystems:
            raise PerformanceContractError("ready cannot be true with blocking subsystems")
        if self.ready and not self.health.all_subsystems_ready():
            raise PerformanceContractError("ready cannot be true while health reports a gap")


@dataclass(frozen=True)
class PerformanceRuntimeConfigV1:
    """Declarative runtime configuration (ADR-0007 D14, §6.1).

    Configuration is data, never code. No field here is ever executed as a shell
    command, and loading a config performs no installation, no download, and no
    change to system audio settings.
    """

    schema_version: str
    runtime_id: str
    runtime_kind: RuntimeKind
    runtime_version_policy: str
    executable: str
    session_template: str
    audio_backend: str
    sample_rate_hz: int
    buffer_frames: int
    audio_output: str
    midi_inputs: tuple[str, ...]
    synth_id: str
    startup_timeout_ms: int
    health_timeout_ms: int
    shutdown_timeout_ms: int
    offline_required: bool
    requires_network: bool = False
    metadata: tuple[tuple[str, str], ...] = field(default=())

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        if not isinstance(self.runtime_kind, RuntimeKind):
            raise PerformanceContractError("runtime_kind must be a RuntimeKind")
        require_identifier(self.runtime_version_policy, "runtime_version_policy")
        require_identifier(self.executable, "executable")
        require_identifier(self.session_template, "session_template")
        require_identifier(self.audio_backend, "audio_backend")
        require_identifier(self.audio_output, "audio_output")
        require_identifier(self.synth_id, "synth_id")

        if self.sample_rate_hz not in SUPPORTED_SAMPLE_RATES:
            raise PerformanceContractError(
                f"sample_rate_hz must be one of {list(SUPPORTED_SAMPLE_RATES)}"
            )
        if self.buffer_frames not in SUPPORTED_BUFFER_FRAMES:
            raise PerformanceContractError(
                f"buffer_frames must be one of {list(SUPPORTED_BUFFER_FRAMES)}"
            )

        require_tuple(self.midi_inputs, "midi_inputs")
        if not self.midi_inputs:
            raise PerformanceContractError("midi_inputs must declare at least one source")
        for source in self.midi_inputs:
            require_identifier(source, "midi_inputs entry")
        require_unique(self.midi_inputs, "midi_inputs")

        for name in ("startup_timeout_ms", "health_timeout_ms", "shutdown_timeout_ms"):
            require_positive_int(getattr(self, name), name)

        require_bool(self.offline_required, "offline_required")
        require_bool(self.requires_network, "requires_network")
        # An appliance that must work offline cannot declare a network dependency.
        # Catching this in configuration is the difference between a validation error
        # on a workbench and a dead instrument on a stage.
        if self.offline_required and self.requires_network:
            raise PerformanceContractError(
                "offline_required is true, so requires_network must be false"
            )

        require_tuple(self.metadata, "metadata")
        for entry in self.metadata:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise PerformanceContractError("metadata entries must be (key, value) pairs")
            require_identifier(entry[0], "metadata key")
        require_unique([k for k, _ in self.metadata], "metadata keys")


@dataclass(frozen=True)
class RuntimeDiagnosticsV1:
    """A point-in-time diagnostic snapshot, for rendering and export."""

    schema_version: str
    runtime_id: str
    collected_at: str
    identity: RuntimeIdentityV1
    capabilities: RuntimeCapabilitySetV1
    health: RuntimeHealthV1
    notes: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.runtime_id, "runtime_id")
        require_utc_timestamp(self.collected_at, "collected_at")
        if not isinstance(self.identity, RuntimeIdentityV1):
            raise PerformanceContractError("identity must be a RuntimeIdentityV1")
        if not isinstance(self.capabilities, RuntimeCapabilitySetV1):
            raise PerformanceContractError("capabilities must be a RuntimeCapabilitySetV1")
        if not isinstance(self.health, RuntimeHealthV1):
            raise PerformanceContractError("health must be a RuntimeHealthV1")
        require_tuple(self.notes, "notes")
        require_nonnegative_int(len(self.notes), "notes length")
