"""Adapter conformance suite (DO-006 §8.3).

Every scenario the order requires, run against the fake runtime. This suite is the
contract any future adapter must satisfy before it is considered an adapter — the
Ardour adapter will be pointed at exactly these tests, which is why they are written
against the port rather than against the fake's internals.
"""

from __future__ import annotations

import pytest

from master_all_strings.performance.adapters.fake_runtime import (
    FAKE_SYNTH_ID,
    FakeRuntime,
    FakeRuntimeScenario,
    build_fake_session,
)
from master_all_strings.performance.contracts.capture import CaptureCompletionState
from master_all_strings.performance.contracts.commands import (
    ArmTrackCommandV1,
    PanicCommandV1,
    PrepareSessionCommandV1,
    SelectSynthCommandV1,
    SetLoopCommandV1,
    SetTransportCommandV1,
    StartCaptureCommandV1,
    StartRuntimeCommandV1,
    StopCaptureCommandV1,
    StopRuntimeCommandV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeCapability,
    RuntimeKind,
    RuntimeState,
)
from master_all_strings.performance.contracts.session import TransportMode
from master_all_strings.performance.ports.runtime import PerformanceRuntimePort
from master_all_strings.performance.session_builder import build_loop_region

SESSION_ID = "session-001"
TRACK_ID = "track-1"
CAPTURE_ID = "capture-1"
END = "2026-07-24T11:00:00Z"


def start_cmd(runtime_id: str = "fake") -> StartRuntimeCommandV1:
    return StartRuntimeCommandV1(
        schema_version=StartRuntimeCommandV1.SCHEMA_VERSION,
        runtime_id=runtime_id,
        timeout_ms=5000,
    )


def stop_cmd(runtime_id: str = "fake") -> StopRuntimeCommandV1:
    return StopRuntimeCommandV1(
        schema_version=StopRuntimeCommandV1.SCHEMA_VERSION,
        runtime_id=runtime_id,
        timeout_ms=5000,
    )


def prepare_cmd() -> PrepareSessionCommandV1:
    return PrepareSessionCommandV1(
        schema_version=PrepareSessionCommandV1.SCHEMA_VERSION,
        session_config=build_fake_session(session_id=SESSION_ID),
    )


def arm_cmd(armed: bool = True, track_id: str = TRACK_ID) -> ArmTrackCommandV1:
    return ArmTrackCommandV1(
        schema_version=ArmTrackCommandV1.SCHEMA_VERSION,
        session_id=SESSION_ID,
        track_id=track_id,
        armed=armed,
    )


def synth_cmd(synth_id: str = FAKE_SYNTH_ID) -> SelectSynthCommandV1:
    return SelectSynthCommandV1(
        schema_version=SelectSynthCommandV1.SCHEMA_VERSION,
        session_id=SESSION_ID,
        track_id=TRACK_ID,
        synth_id=synth_id,
    )


def start_capture_cmd(capture_id: str = CAPTURE_ID) -> StartCaptureCommandV1:
    return StartCaptureCommandV1(
        schema_version=StartCaptureCommandV1.SCHEMA_VERSION,
        session_id=SESSION_ID,
        capture_id=capture_id,
        track_id=TRACK_ID,
    )


def stop_capture_cmd(
    capture_id: str = CAPTURE_ID, *, cancelled: bool = False
) -> StopCaptureCommandV1:
    return StopCaptureCommandV1(
        schema_version=StopCaptureCommandV1.SCHEMA_VERSION,
        session_id=SESSION_ID,
        capture_id=capture_id,
        ended_at=END,
        cancelled=cancelled,
    )


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def armed_runtime(runtime: FakeRuntime) -> FakeRuntime:
    """A runtime started, prepared, armed, and with a synth loaded."""
    runtime.start(start_cmd())
    runtime.prepare_session(prepare_cmd())
    runtime.arm_track(arm_cmd())
    runtime.select_synth(synth_cmd())
    return runtime


class TestPortConformance:
    def test_fake_runtime_satisfies_the_port(self, runtime: FakeRuntime) -> None:
        assert isinstance(runtime, PerformanceRuntimePort)

    def test_every_port_operation_exists(self, runtime: FakeRuntime) -> None:
        for name in (
            "identity",
            "capabilities",
            "start",
            "stop",
            "readiness",
            "health",
            "prepare_session",
            "arm_track",
            "set_transport",
            "start_capture",
            "stop_capture",
            "select_synth",
            "set_loop",
            "panic",
            "retrieve_capture",
            "export_diagnostics",
        ):
            assert callable(getattr(runtime, name)), name


class TestLifecycle:
    def test_01_start_succeeds(self, runtime: FakeRuntime) -> None:
        result = runtime.start(start_cmd())
        assert result.succeeded is True
        assert result.fault is None

    def test_02_start_times_out(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(start_times_out=True))
        result = runtime.start(start_cmd())
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.STARTUP_TIMEOUT

    def test_03_stop_succeeds(self, runtime: FakeRuntime) -> None:
        runtime.start(start_cmd())
        assert runtime.stop(stop_cmd()).succeeded is True

    def test_04_repeated_stop_is_safe(self, runtime: FakeRuntime) -> None:
        # Recovery paths call stop without knowing the current state.
        runtime.start(start_cmd())
        assert runtime.stop(stop_cmd()).succeeded is True
        assert runtime.stop(stop_cmd()).succeeded is True
        assert runtime.stop(stop_cmd()).succeeded is True

    def test_05_identity_is_reported(self, runtime: FakeRuntime) -> None:
        identity = runtime.identity()
        assert identity.runtime_kind is RuntimeKind.FAKE
        assert identity.version_supported is True

    def test_identity_is_available_before_start(self, runtime: FakeRuntime) -> None:
        # An unsupported version must be detectable without committing to running it.
        assert runtime.identity().reported_version is not None

    def test_unresolved_version_is_reported_as_unsupported(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(version_unresolved=True))
        identity = runtime.identity()
        assert identity.reported_version is None
        assert identity.version_supported is False

    def test_06_capabilities_are_reported(self, runtime: FakeRuntime) -> None:
        capabilities = runtime.capabilities()
        assert capabilities.supports(RuntimeCapability.MIDI_CAPTURE)
        assert capabilities.supports(RuntimeCapability.PANIC)

    def test_capability_discovery_reports_absent_capabilities(
        self, runtime: FakeRuntime
    ) -> None:
        # Runtimes legitimately differ; callers must ask rather than assume.
        capabilities = runtime.capabilities()
        assert not capabilities.supports(RuntimeCapability.MULTITRACK)
        assert not capabilities.supports(RuntimeCapability.MIXDOWN)
        assert not capabilities.supports(RuntimeCapability.SESSION_RECOVERY)


class TestSession:
    def test_07_session_prepares(self, runtime: FakeRuntime) -> None:
        runtime.start(start_cmd())
        assert runtime.prepare_session(prepare_cmd()).succeeded is True

    def test_prepare_before_start_is_rejected(self, runtime: FakeRuntime) -> None:
        result = runtime.prepare_session(prepare_cmd())
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.INVALID_STATE

    def test_08_track_arms(self, runtime: FakeRuntime) -> None:
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        assert runtime.arm_track(arm_cmd()).succeeded is True

    def test_arming_an_unknown_track_is_rejected(self, armed_runtime: FakeRuntime) -> None:
        result = armed_runtime.arm_track(arm_cmd(track_id="track-99"))
        assert result.succeeded is False

    def test_disarming_a_track_succeeds(self, armed_runtime: FakeRuntime) -> None:
        assert armed_runtime.arm_track(arm_cmd(armed=False)).succeeded is True

    def test_arm_without_session_is_rejected(self, runtime: FakeRuntime) -> None:
        assert runtime.arm_track(arm_cmd()).succeeded is False

    def test_transport_can_be_set(self, armed_runtime: FakeRuntime) -> None:
        command = SetTransportCommandV1(
            schema_version=SetTransportCommandV1.SCHEMA_VERSION,
            session_id=SESSION_ID,
            mode=TransportMode.PLAYING,
            position_tick=0,
        )
        assert armed_runtime.set_transport(command).succeeded is True

    def test_transport_without_session_is_rejected(self, runtime: FakeRuntime) -> None:
        command = SetTransportCommandV1(
            schema_version=SetTransportCommandV1.SCHEMA_VERSION,
            session_id=SESSION_ID,
            mode=TransportMode.PLAYING,
        )
        assert runtime.set_transport(command).succeeded is False

    def test_loop_can_be_set_and_cleared(self, armed_runtime: FakeRuntime) -> None:
        loop = build_loop_region(0, 7680)
        set_cmd = SetLoopCommandV1(
            schema_version=SetLoopCommandV1.SCHEMA_VERSION, session_id=SESSION_ID, loop=loop
        )
        clear_cmd = SetLoopCommandV1(
            schema_version=SetLoopCommandV1.SCHEMA_VERSION, session_id=SESSION_ID, loop=None
        )
        assert armed_runtime.set_loop(set_cmd).succeeded is True
        assert armed_runtime.set_loop(clear_cmd).succeeded is True

    def test_loop_without_session_is_rejected(self, runtime: FakeRuntime) -> None:
        command = SetLoopCommandV1(
            schema_version=SetLoopCommandV1.SCHEMA_VERSION, session_id=SESSION_ID, loop=None
        )
        assert runtime.set_loop(command).succeeded is False


class TestSynthSelection:
    def test_12_synth_selection_succeeds(self, runtime: FakeRuntime) -> None:
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        assert runtime.select_synth(synth_cmd()).succeeded is True

    def test_13_synth_selection_fails_on_load_error(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(synth_load_fails=True))
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        result = runtime.select_synth(synth_cmd())
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.SYNTH_LOAD_FAILED

    def test_unavailable_synth_is_rejected(self, armed_runtime: FakeRuntime) -> None:
        result = armed_runtime.select_synth(synth_cmd(synth_id="some-other-synth"))
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.SYNTH_MISSING

    def test_synth_selection_without_session_is_rejected(self, runtime: FakeRuntime) -> None:
        assert runtime.select_synth(synth_cmd()).succeeded is False


class TestCapture:
    def test_09_capture_starts(self, armed_runtime: FakeRuntime) -> None:
        assert armed_runtime.start_capture(start_capture_cmd()).succeeded is True

    def test_10_capture_stops(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        assert armed_runtime.stop_capture(stop_capture_cmd()).succeeded is True

    def test_11_events_are_retrieved(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        armed_runtime.feed_note_off(64)
        armed_runtime.stop_capture(stop_capture_cmd())
        result = armed_runtime.retrieve_capture(CAPTURE_ID)
        assert result.succeeded is True
        assert result.capture is not None
        assert result.capture.event_count == 2
        assert result.capture.completion_state is CaptureCompletionState.COMPLETE

    def test_capture_on_unarmed_track_is_rejected(self, runtime: FakeRuntime) -> None:
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        result = runtime.start_capture(start_capture_cmd())
        assert result.succeeded is False

    def test_second_concurrent_capture_is_rejected(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        assert armed_runtime.start_capture(start_capture_cmd("capture-2")).succeeded is False

    def test_capture_without_session_is_rejected(self, runtime: FakeRuntime) -> None:
        assert runtime.start_capture(start_capture_cmd()).succeeded is False

    def test_stopping_an_inactive_capture_is_rejected(self, armed_runtime: FakeRuntime) -> None:
        assert armed_runtime.stop_capture(stop_capture_cmd()).succeeded is False

    def test_cancelled_capture_records_cancellation(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.stop_capture(stop_capture_cmd(cancelled=True))
        result = armed_runtime.retrieve_capture(CAPTURE_ID)
        assert result.capture is not None
        assert result.capture.completion_state is CaptureCompletionState.CANCELLED

    def test_19_retrieval_before_session_is_rejected(self, runtime: FakeRuntime) -> None:
        result = runtime.retrieve_capture(CAPTURE_ID)
        assert result.succeeded is False
        assert result.capture is None

    def test_20_retrieval_before_capture_is_rejected(self, armed_runtime: FakeRuntime) -> None:
        # An empty record and a never-started one must not look alike.
        result = armed_runtime.retrieve_capture("never-started")
        assert result.succeeded is False
        assert result.capture is None

    def test_feeding_without_active_capture_raises(self, armed_runtime: FakeRuntime) -> None:
        with pytest.raises(PerformanceContractError, match="no active capture"):
            armed_runtime.feed_note_on(64, 100)

    def test_controller_and_pitch_bend_events_are_captured(
        self, armed_runtime: FakeRuntime
    ) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_control_change(64, 127)
        armed_runtime.feed_pitch_bend(2048)
        armed_runtime.stop_capture(stop_capture_cmd())
        capture = armed_runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert capture.event_count == 2


class TestDeviceLoss:
    def test_14_midi_source_disappears(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(midi_input_missing=True))
        runtime.start(start_cmd())
        result = runtime.prepare_session(prepare_cmd())
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.MIDI_INPUT_MISSING

    def test_missing_midi_blocks_readiness(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(midi_input_missing=True))
        runtime.start(start_cmd())
        readiness = runtime.readiness()
        assert readiness.ready is False
        assert "midi_input" in readiness.blocking_subsystems

    def test_15_audio_output_disappears(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(audio_output_missing=True))
        runtime.start(start_cmd())
        result = runtime.prepare_session(prepare_cmd())
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.AUDIO_OUTPUT_MISSING

    def test_missing_audio_output_blocks_readiness(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(audio_output_missing=True))
        runtime.start(start_cmd())
        assert "audio_output" in runtime.readiness().blocking_subsystems

    def test_synth_failure_faults_the_synth_subsystem(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(synth_load_fails=True))
        runtime.start(start_cmd())
        assert "synth" in runtime.readiness().blocking_subsystems


class TestCrashAndInterruption:
    def test_16_runtime_crashes_during_capture(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        result = armed_runtime.crash()
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.RUNTIME_CRASHED

    def test_17_capture_becomes_interrupted(self, armed_runtime: FakeRuntime) -> None:
        # A crash is never represented as an ordinary stop.
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        armed_runtime.crash()
        capture = armed_runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert capture.completion_state is CaptureCompletionState.INTERRUPTED

    def test_interrupted_capture_keeps_accepted_events(
        self, armed_runtime: FakeRuntime
    ) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        armed_runtime.feed_note_on(67, 90)
        armed_runtime.crash()
        capture = armed_runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert capture.event_count == 2

    def test_interrupted_capture_carries_the_fault(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        armed_runtime.crash()
        capture = armed_runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert capture.faults[0].code is FaultCode.RUNTIME_CRASHED

    def test_interrupted_capture_warns_about_sounding_notes(
        self, armed_runtime: FakeRuntime
    ) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        armed_runtime.crash()
        capture = armed_runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert any("without note-off" in w for w in capture.warnings)

    def test_crash_without_an_active_capture_is_safe(self, armed_runtime: FakeRuntime) -> None:
        result = armed_runtime.crash()
        assert result.succeeded is False

    def test_crash_moves_the_runtime_to_failed(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.crash()
        assert armed_runtime.health().state is RuntimeState.FAILED

    def test_feeding_after_injected_crash_scenario_raises(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(crash_during_capture=True))
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        runtime.arm_track(arm_cmd())
        runtime.start_capture(start_capture_cmd())
        with pytest.raises(PerformanceContractError, match="crashed"):
            runtime.feed_note_on(64, 100)


class TestPanic:
    def test_18_panic_terminates_active_notes(self, armed_runtime: FakeRuntime) -> None:
        armed_runtime.start_capture(start_capture_cmd())
        armed_runtime.feed_note_on(64, 100)
        result = armed_runtime.panic(
            PanicCommandV1(
                schema_version=PanicCommandV1.SCHEMA_VERSION,
                runtime_id="fake",
                session_id=SESSION_ID,
            )
        )
        assert result.succeeded is True

    def test_panic_is_valid_with_no_session(self, runtime: FakeRuntime) -> None:
        # Panic that requires a healthy runtime is not panic.
        result = runtime.panic(
            PanicCommandV1(schema_version=PanicCommandV1.SCHEMA_VERSION, runtime_id="fake")
        )
        assert result.succeeded is True

    def test_failed_panic_is_reported(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(panic_fails=True))
        result = runtime.panic(
            PanicCommandV1(schema_version=PanicCommandV1.SCHEMA_VERSION, runtime_id="fake")
        )
        assert result.succeeded is False
        assert result.fault is not None
        assert result.fault.code is FaultCode.PANIC_FAILED


class TestHealthAndDiagnostics:
    def test_stopped_runtime_reports_unavailable_process(self, runtime: FakeRuntime) -> None:
        health = runtime.health()
        assert health.state is RuntimeState.OFF
        assert health.all_subsystems_ready() is False

    def test_ready_runtime_reports_every_subsystem_ready(
        self, armed_runtime: FakeRuntime
    ) -> None:
        assert armed_runtime.health().all_subsystems_ready() is True

    def test_started_but_unprepared_runtime_is_not_ready(self, runtime: FakeRuntime) -> None:
        # Healthy subsystems while still probing must not read as ready.
        runtime.start(start_cmd())
        assert runtime.readiness().ready is False

    def test_diagnostics_export_succeeds(self, armed_runtime: FakeRuntime) -> None:
        result = armed_runtime.export_diagnostics()
        assert result.succeeded is True
        assert result.diagnostics is not None

    def test_diagnostics_note_an_unresolved_version(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(version_unresolved=True))
        runtime.start(start_cmd())
        result = runtime.export_diagnostics()
        assert result.diagnostics is not None
        assert any("version is unresolved" in note for note in result.diagnostics.notes)

    def test_stuck_note_scenario_warns_at_stop(self) -> None:
        runtime = FakeRuntime(FakeRuntimeScenario(stuck_notes=True))
        runtime.start(start_cmd())
        runtime.prepare_session(prepare_cmd())
        runtime.arm_track(arm_cmd())
        runtime.start_capture(start_capture_cmd())
        runtime.feed_note_on(64, 100)
        runtime.stop_capture(stop_capture_cmd())
        capture = runtime.retrieve_capture(CAPTURE_ID).capture
        assert capture is not None
        assert any("still sounding" in w for w in capture.warnings)
