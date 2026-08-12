"""Live capture lifecycle over the transport-neutral MIDI input port."""

from __future__ import annotations

from collections.abc import Callable

from master_all_strings.performance.capture_normalization import (
    append_events,
    build_raw_capture,
    close_capture,
)
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CapturedMidiEventV1,
    CaptureSourceV1,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import RuntimeIdentityV1
from master_all_strings.performance.contracts.session import MeterV1
from master_all_strings.performance.ports.midi_input import PerformanceMidiInputPort


class LiveMidiCaptureService:
    def __init__(
        self,
        midi_input: PerformanceMidiInputPort,
        *,
        now_utc: Callable[[], str],
    ) -> None:
        self._input = midi_input
        self._now_utc = now_utc
        self._capture: RawPerformanceCaptureV1 | None = None
        self._unsubscribe: Callable[[], None] | None = None

    @property
    def active_capture(self) -> RawPerformanceCaptureV1 | None:
        return self._capture

    def start(
        self,
        *,
        device_id: str,
        capture_id: str,
        performance_session_id: str,
        runtime_identity: RuntimeIdentityV1,
        source_identity: CaptureSourceV1,
        tempo_context: float,
        meter_context: MeterV1,
        provenance: tuple[tuple[str, str], ...] = (),
    ) -> RawPerformanceCaptureV1:
        if self._capture is not None and not self._capture.is_closed:
            raise PerformanceContractError("capture is already active")
        self._input.connect(device_id)
        self._unsubscribe = self._input.subscribe(self._accept, self._interrupted)
        self._capture = build_raw_capture(
            capture_id=capture_id,
            session_id=performance_session_id,
            runtime_identity=runtime_identity,
            source_identity=source_identity,
            started_at=self._now_utc(),
            tempo_context=tempo_context,
            meter_context=meter_context,
            provenance=provenance,
        )
        return self._capture

    def stop(self) -> RawPerformanceCaptureV1:
        capture = self._require_open()
        self._capture = close_capture(capture, ended_at=self._now_utc())
        self._release_input()
        return self._capture

    def _accept(self, event: CapturedMidiEventV1) -> None:
        self._capture = append_events(self._require_open(), (event,))

    def _interrupted(self, device_id: str) -> None:
        capture = self._require_open()
        self._capture = close_capture(
            capture,
            ended_at=self._now_utc(),
            completion_state=CaptureCompletionState.INTERRUPTED,
            warnings=(f"MIDI input disconnected: {device_id}",),
        )
        self._release_input(disconnect=False)

    def _require_open(self) -> RawPerformanceCaptureV1:
        if self._capture is None or self._capture.is_closed:
            raise PerformanceContractError("no active capture")
        return self._capture

    def _release_input(self, *, disconnect: bool = True) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if disconnect:
            self._input.disconnect()
