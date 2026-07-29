"""``PerformanceRuntimePort`` — the runtime-neutral boundary.

This Protocol is the single line ADR-0007 D2 and D18 draw. Everything above it is
Master All Strings; everything below it is replaceable audio infrastructure.

**No implementation-specific type may appear in this file.** No ``Ardour``, no OSC,
no LV2, no process handle, no session file path. A test asserts it
(``tests/performance/test_performance_boundaries.py``), because this is exactly the file
where coupling would enter first and be hardest to remove later.

A ``Protocol`` rather than an abstract base class: adapters do not inherit from the
port, so nothing about a runtime's implementation is shaped by our class hierarchy,
and a conformance test can check any object structurally.

Operations return result contracts rather than raising on runtime failure. An adapter
raises only for contract violations — data that should never have been constructed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from master_all_strings.performance.contracts.commands import (
    ArmTrackCommandV1,
    PanicCommandV1,
    PrepareSessionCommandV1,
    RetrieveCaptureCommandV1,
    SelectSynthCommandV1,
    SetLoopCommandV1,
    SetTransportCommandV1,
    StartCaptureCommandV1,
    StartRuntimeCommandV1,
    StopCaptureCommandV1,
    StopRuntimeCommandV1,
)
from master_all_strings.performance.contracts.results import (
    CaptureResultV1,
    RuntimeCommandResultV1,
    RuntimeDiagnosticResultV1,
)
from master_all_strings.performance.contracts.runtime import (
    RuntimeCapabilitySetV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeReadinessV1,
)


@runtime_checkable
class PerformanceRuntimePort(Protocol):
    """What Master All Strings may ask of any performance runtime.

    Implementations: ``adapters.fake_runtime.FakeRuntime`` (ships, tested) and
    ``adapters.ardour`` (scaffold; not implemented until the fake adapter and contract
    suite are stable).
    """

    def identity(self) -> RuntimeIdentityV1:
        """Who this runtime is, and whether its version is supported.

        Callable before ``start``: an unsupported version must be detectable without
        first committing to running it.
        """
        ...

    def capabilities(self) -> RuntimeCapabilitySetV1:
        """What this runtime can do.

        Callers discover rather than assume. A lightweight practice runtime and a
        studio runtime legitimately differ, and asking is how the controller stays
        correct across both.
        """
        ...

    def start(self, command: StartRuntimeCommandV1) -> RuntimeCommandResultV1:
        """Start the runtime and wait for readiness or timeout."""
        ...

    def stop(self, command: StopRuntimeCommandV1) -> RuntimeCommandResultV1:
        """Stop the runtime. Idempotent: stopping a stopped runtime succeeds."""
        ...

    def readiness(self) -> RuntimeReadinessV1:
        """Whether the runtime is usable, and what blocks it if not."""
        ...

    def health(self) -> RuntimeHealthV1:
        """Per-subsystem health. Never a single aggregate boolean."""
        ...

    def prepare_session(self, command: PrepareSessionCommandV1) -> RuntimeCommandResultV1:
        """Create the prepared session described by the configuration."""
        ...

    def arm_track(self, command: ArmTrackCommandV1) -> RuntimeCommandResultV1:
        """Arm or disarm a track for recording."""
        ...

    def set_transport(self, command: SetTransportCommandV1) -> RuntimeCommandResultV1:
        """Set transport mode and optionally locate."""
        ...

    def start_capture(self, command: StartCaptureCommandV1) -> RuntimeCommandResultV1:
        """Begin capturing on an armed track."""
        ...

    def stop_capture(self, command: StopCaptureCommandV1) -> RuntimeCommandResultV1:
        """End the capture and close it with an explicit terminal state."""
        ...

    def select_synth(self, command: SelectSynthCommandV1) -> RuntimeCommandResultV1:
        """Load an approved synthesizer by registry identifier."""
        ...

    def set_loop(self, command: SetLoopCommandV1) -> RuntimeCommandResultV1:
        """Set or clear the loop region."""
        ...

    def panic(self, command: PanicCommandV1) -> RuntimeCommandResultV1:
        """Silence every sounding note. Valid in any state."""
        ...

    def retrieve_capture(self, command: RetrieveCaptureCommandV1) -> CaptureResultV1:
        """Return a capture record.

        Retrieval before a session exists, or before a capture has started, is
        rejected with a fault rather than an empty capture — an empty record and a
        never-started one must not look alike.
        """
        ...

    def export_diagnostics(self) -> RuntimeDiagnosticResultV1:
        """Collect a diagnostic snapshot. Read-only; mutates no system state."""
        ...
