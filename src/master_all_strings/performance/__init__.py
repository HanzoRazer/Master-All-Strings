"""Performance Engine — the Embedded Performance Runtime.

**Owning engine: Performance Engine** (see
``docs/architecture/FOUR_ENGINE_SYSTEM_MODEL.md``, package-to-engine table).

This package holds the runtime-neutral contracts and port ratified by ADR-0007. It
answers "what actually happened when it was played?" — capture, playback, transport,
device and runtime integration — and nothing else. It does not own canonical music,
notation, TAB, piano-roll semantics, or any coaching interpretation.

Three rules govern everything here, and each is enforced by a test rather than by
convention:

1. **No runtime-specific vocabulary crosses the port.** ``Ardour`` may appear only
   inside ``adapters/ardour/``. The contracts and ``PerformanceRuntimePort`` are
   neutral so a runtime can be replaced without touching any engine contract
   (ADR-0007 D18).
2. **Raw capture is evidence and is immutable once closed.** Derived records cite it;
   nothing rewrites it (ADR-0007 D6).
3. **Performance emits facts, never conclusions.** No field here may express mastery,
   difficulty, coaching, or curriculum — that is Educational Engine authority under
   Seam 4 (ADR-0007 D10).

Only stable public contracts are exported. Adapters are imported from their own
modules so that importing this package never pulls in a runtime implementation.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.capture import (
    SOURCE_STRING_UNRESOLVED,
    CaptureCompletionState,
    CapturedMidiEventV1,
    CaptureSourceV1,
    MidiEventType,
    PerformanceObservationV1,
    RawPerformanceCaptureV1,
)
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
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.ingestion import (
    CanonicalIngestionRequestV1,
    CanonicalIngestionResultV1,
    ProjectionType,
    SourceMidiEventKind,
    SourceMidiEventV1,
)
from master_all_strings.performance.contracts.results import (
    CaptureResultV1,
    PerformanceExportResultV1,
    RuntimeCommandResultV1,
    RuntimeDiagnosticResultV1,
)
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    PerformanceRuntimeConfigV1,
    RuntimeCapability,
    RuntimeCapabilitySetV1,
    RuntimeDiagnosticsV1,
    RuntimeFaultV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeKind,
    RuntimeReadinessV1,
    RuntimeState,
    SubsystemState,
)
from master_all_strings.performance.contracts.session import (
    LoopRegionV1,
    MeterV1,
    MetronomeConfigV1,
    PerformanceSessionConfigV1,
    PerformanceSessionStateV1,
    PerformanceTrackConfigV1,
    SessionState,
    TrackKind,
    TransportMode,
    TransportStateV1,
)
from master_all_strings.performance.ports.runtime import PerformanceRuntimePort

__all__ = [
    "ArmTrackCommandV1",
    "CanonicalIngestionRequestV1",
    "CanonicalIngestionResultV1",
    "CaptureCompletionState",
    "CaptureResultV1",
    "CaptureSourceV1",
    "CapturedMidiEventV1",
    "FaultCode",
    "LoopRegionV1",
    "MeterV1",
    "MetronomeConfigV1",
    "MidiEventType",
    "PanicCommandV1",
    "PerformanceContractError",
    "PerformanceExportResultV1",
    "PerformanceObservationV1",
    "PerformanceRuntimeConfigV1",
    "PerformanceRuntimePort",
    "PerformanceSessionConfigV1",
    "PerformanceSessionStateV1",
    "PerformanceTrackConfigV1",
    "PrepareSessionCommandV1",
    "ProjectionType",
    "RawPerformanceCaptureV1",
    "RetrieveCaptureCommandV1",
    "RuntimeCapability",
    "RuntimeCapabilitySetV1",
    "RuntimeCommandResultV1",
    "RuntimeDiagnosticResultV1",
    "RuntimeDiagnosticsV1",
    "RuntimeFaultV1",
    "RuntimeHealthV1",
    "RuntimeIdentityV1",
    "RuntimeKind",
    "RuntimeReadinessV1",
    "RuntimeState",
    "SOURCE_STRING_UNRESOLVED",
    "SelectSynthCommandV1",
    "SessionState",
    "SetLoopCommandV1",
    "SetTransportCommandV1",
    "SourceMidiEventKind",
    "SourceMidiEventV1",
    "StartCaptureCommandV1",
    "StartRuntimeCommandV1",
    "StopCaptureCommandV1",
    "StopRuntimeCommandV1",
    "SubsystemState",
    "TrackKind",
    "TransportMode",
    "TransportStateV1",
]
