from __future__ import annotations

import pytest
from helpers import make_event

from master_all_strings.performance.adapters.fake_midi_input import FakeMidiInput
from master_all_strings.performance.contracts.capture import CaptureCompletionState
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.live_capture import LiveMidiCaptureService


def _start(service, runtime_identity, capture_source, meter):  # type: ignore[no-untyped-def]
    return service.start(
        device_id="fake-midi-input",
        capture_id="capture-live-1",
        performance_session_id="attempt-1",
        runtime_identity=runtime_identity,
        source_identity=capture_source,
        tempo_context=120,
        meter_context=meter,
    )


def test_live_capture_preserves_events_and_closes(
    runtime_identity, capture_source, meter  # type: ignore[no-untyped-def]
) -> None:
    adapter = FakeMidiInput((make_event(0), make_event(1)))
    times = iter(("2026-08-12T10:00:00Z", "2026-08-12T10:00:01Z"))
    service = LiveMidiCaptureService(adapter, now_utc=lambda: next(times))
    _start(service, runtime_identity, capture_source, meter)
    adapter.emit_all()
    capture = service.stop()
    assert capture.event_count == 2
    assert capture.completion_state is CaptureCompletionState.COMPLETE


def test_disconnect_interrupts_and_preserves_partial_capture(
    runtime_identity, capture_source, meter  # type: ignore[no-untyped-def]
) -> None:
    adapter = FakeMidiInput()
    times = iter(("2026-08-12T10:00:00Z", "2026-08-12T10:00:01Z"))
    service = LiveMidiCaptureService(adapter, now_utc=lambda: next(times))
    _start(service, runtime_identity, capture_source, meter)
    adapter.emit(make_event(0))
    adapter.disconnect()
    capture = service.active_capture
    assert capture is not None
    assert capture.event_count == 1
    assert capture.completion_state is CaptureCompletionState.INTERRUPTED


def test_double_start_and_stop_without_capture_fail(
    runtime_identity, capture_source, meter  # type: ignore[no-untyped-def]
) -> None:
    adapter = FakeMidiInput()
    service = LiveMidiCaptureService(adapter, now_utc=lambda: "2026-08-12T10:00:00Z")
    with pytest.raises(PerformanceContractError, match="no active"):
        service.stop()
    _start(service, runtime_identity, capture_source, meter)
    with pytest.raises(PerformanceContractError, match="already active"):
        _start(service, runtime_identity, capture_source, meter)
