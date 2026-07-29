"""A deterministic in-memory ``PerformanceRuntimePort`` implementation.

The first executable adapter, and the one that proves the architecture without
Ardour, a Raspberry Pi, an audio interface, or a MIDI device. It exists so that
product behaviour is testable now and so that the Ardour adapter has a conformance
suite to satisfy before it is written.

Determinism is the design constraint. The runtime reads no clock: timestamps come
from a caller-supplied sequence, so the same scenario produces byte-identical records
on every run. Failures are injected through ``FakeRuntimeScenario`` rather than
simulated randomly, so every conformance scenario is reproducible.

This is not a mock. It enforces the same state rules a real runtime must: capture
retrieval before a session exists is refused, a closed capture cannot reopen, and a
crash produces an ``INTERRUPTED`` capture with the fault attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from master_all_strings.performance.capture_normalization import (
    append_events,
    build_raw_capture,
    close_capture,
    mark_capture_interrupted,
)
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CapturedMidiEventV1,
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
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
from master_all_strings.performance.contracts.results import (
    CaptureResultV1,
    RuntimeCommandResultV1,
    RuntimeDiagnosticResultV1,
)
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeCapability,
    RuntimeCapabilitySetV1,
    RuntimeFaultV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeKind,
    RuntimeReadinessV1,
    RuntimeState,
    SubsystemState,
)
from master_all_strings.performance.contracts.session import (
    PerformanceSessionConfigV1,
    TransportMode,
)
from master_all_strings.performance.runtime_diagnostics import (
    check_runtime_readiness,
    collect_runtime_diagnostics,
)
from master_all_strings.performance.session_builder import build_single_track_session

FAKE_RUNTIME_ID = "fake"
FAKE_VERSION = "1.0.0"
FAKE_SYNTH_ID = "fake-synth"

# What the fake claims to support. Deliberately not everything: omitting multitrack,
# automation, mixdown, and session recovery means tests exercise the
# capability-unsupported path instead of assuming a uniform feature set.
FAKE_CAPABILITIES = (
    RuntimeCapability.TRANSPORT,
    RuntimeCapability.MIDI_CAPTURE,
    RuntimeCapability.SYNTH_HOSTING,
    RuntimeCapability.METRONOME,
    RuntimeCapability.LOOPING,
    RuntimeCapability.PANIC,
    RuntimeCapability.DIAGNOSTICS,
)


@dataclass(frozen=True)
class FakeRuntimeScenario:
    """Which failures this runtime should inject.

    Every conformance scenario in DO-006 §8.3 is reachable by setting one of these.
    """

    start_times_out: bool = False
    midi_input_missing: bool = False
    audio_output_missing: bool = False
    synth_load_fails: bool = False
    crash_during_capture: bool = False
    panic_fails: bool = False
    version_unresolved: bool = False
    stuck_notes: bool = False


class _Clock:
    """A deterministic timestamp source.

    Advances one second per call from a fixed origin. Real time never enters a test.
    """

    def __init__(self, origin_epoch_second: int = 0) -> None:
        self._tick = origin_epoch_second

    def now(self) -> str:
        value = self._tick
        self._tick += 1
        hours, remainder = divmod(value, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"2026-07-24T{10 + hours:02d}:{minutes:02d}:{seconds:02d}Z"


@dataclass
class _SessionRecord:
    config: PerformanceSessionConfigV1
    armed_tracks: set[str] = field(default_factory=set)
    synth_id: str | None = None
    transport_mode: TransportMode = TransportMode.STOPPED
    sounding_notes: list[tuple[int, int]] = field(default_factory=list)


class FakeRuntime:
    """An in-memory runtime that satisfies ``PerformanceRuntimePort``."""

    def __init__(
        self,
        scenario: FakeRuntimeScenario | None = None,
        *,
        runtime_id: str = FAKE_RUNTIME_ID,
        clock: _Clock | None = None,
    ) -> None:
        self.scenario = scenario or FakeRuntimeScenario()
        self.runtime_id = runtime_id
        self._clock = clock or _Clock()
        self._state = RuntimeState.OFF
        self._session: _SessionRecord | None = None
        self._captures: dict[str, RawPerformanceCaptureV1] = {}
        self._active_capture_id: str | None = None
        self._sequence = 0
        self._fault_counter = 0

    # --- identity and capability -----------------------------------------

    def identity(self) -> RuntimeIdentityV1:
        """Who this runtime is. Callable before ``start``."""
        unresolved = self.scenario.version_unresolved
        return RuntimeIdentityV1(
            schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
            runtime_id=self.runtime_id,
            runtime_kind=RuntimeKind.FAKE,
            reported_version=None if unresolved else FAKE_VERSION,
            version_policy=FAKE_VERSION,
            version_supported=not unresolved,
        )

    def capabilities(self) -> RuntimeCapabilitySetV1:
        """What this runtime supports."""
        return RuntimeCapabilitySetV1(
            schema_version=RuntimeCapabilitySetV1.SCHEMA_VERSION,
            runtime_id=self.runtime_id,
            capabilities=FAKE_CAPABILITIES,
        )

    # --- lifecycle --------------------------------------------------------

    def start(self, command: StartRuntimeCommandV1) -> RuntimeCommandResultV1:
        """Start and become ready, unless the scenario injects a startup timeout."""
        if self.scenario.start_times_out:
            self._state = RuntimeState.FAILED
            return self._failure(
                "start",
                FaultCode.STARTUP_TIMEOUT,
                "process",
                "runtime did not become ready before the timeout",
            )
        self._state = RuntimeState.READY
        return self._success("start")

    def stop(self, command: StopRuntimeCommandV1) -> RuntimeCommandResultV1:
        """Stop. Idempotent: stopping a stopped runtime succeeds."""
        self._state = RuntimeState.OFF
        self._session = None
        self._active_capture_id = None
        return self._success("stop")

    def readiness(self) -> RuntimeReadinessV1:
        """Whether the runtime is usable, and what blocks it."""
        return check_runtime_readiness(self.health())

    def health(self) -> RuntimeHealthV1:
        """Per-subsystem health, reflecting the injected scenario."""
        faults: list[RuntimeFaultV1] = []
        midi = SubsystemState.READY
        audio_out = SubsystemState.READY
        synth = SubsystemState.READY

        if self._state is RuntimeState.OFF:
            return self._health(
                state=RuntimeState.OFF,
                process=SubsystemState.UNAVAILABLE,
                audio_backend=SubsystemState.UNKNOWN,
                audio_output=SubsystemState.UNKNOWN,
                midi_input=SubsystemState.UNKNOWN,
                synth=SubsystemState.UNKNOWN,
                session=SubsystemState.UNKNOWN,
                capture=SubsystemState.UNKNOWN,
            )

        if self.scenario.midi_input_missing:
            midi = SubsystemState.UNAVAILABLE
            faults.append(
                self._fault(
                    FaultCode.MIDI_INPUT_MISSING,
                    "midi_input",
                    "configured MIDI input is not present",
                    recoverable=True,
                )
            )
        if self.scenario.audio_output_missing:
            audio_out = SubsystemState.UNAVAILABLE
            faults.append(
                self._fault(
                    FaultCode.AUDIO_OUTPUT_MISSING,
                    "audio_output",
                    "configured audio output is not present",
                    recoverable=True,
                )
            )
        if self.scenario.synth_load_fails:
            synth = SubsystemState.FAULTED
            faults.append(
                self._fault(
                    FaultCode.SYNTH_LOAD_FAILED, "synth", "synth failed to load", recoverable=False
                )
            )

        degraded = bool(faults) or self._state is RuntimeState.FAILED
        session_state = SubsystemState.READY if self._session else SubsystemState.UNKNOWN
        capture_state = (
            SubsystemState.READY
            if self._state is not RuntimeState.FAILED
            else SubsystemState.FAULTED
        )

        # A session that has not been prepared is not a fault, but it does mean the
        # runtime is not fully READY -- so state follows the subsystems rather than
        # being asserted independently.
        state = self._state
        if degraded:
            state = (
                RuntimeState.DEGRADED
                if self._state is not RuntimeState.FAILED
                else RuntimeState.FAILED
            )
        elif session_state is not SubsystemState.READY and state is RuntimeState.READY:
            state = RuntimeState.PROBING

        return self._health(
            state=state,
            process=SubsystemState.READY,
            audio_backend=SubsystemState.READY,
            audio_output=audio_out,
            midi_input=midi,
            synth=synth,
            session=session_state,
            capture=capture_state,
            faults=tuple(faults),
        )

    # --- session ----------------------------------------------------------

    def prepare_session(self, command: PrepareSessionCommandV1) -> RuntimeCommandResultV1:
        """Create the prepared session."""
        if self._state is not RuntimeState.READY:
            return self._failure(
                "prepare_session", FaultCode.INVALID_STATE, "session", "runtime is not ready"
            )
        if self.scenario.midi_input_missing:
            return self._failure(
                "prepare_session",
                FaultCode.MIDI_INPUT_MISSING,
                "midi_input",
                "configured MIDI input is not present",
            )
        if self.scenario.audio_output_missing:
            return self._failure(
                "prepare_session",
                FaultCode.AUDIO_OUTPUT_MISSING,
                "audio_output",
                "configured audio output is not present",
            )
        self._session = _SessionRecord(config=command.session_config)
        return self._success("prepare_session")

    def arm_track(self, command: ArmTrackCommandV1) -> RuntimeCommandResultV1:
        """Arm or disarm a track."""
        session = self._session
        if session is None:
            return self._failure(
                "arm_track", FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        known = {t.track_id for t in session.config.tracks}
        if command.track_id not in known:
            return self._failure(
                "arm_track",
                FaultCode.INVALID_STATE,
                "session",
                f"unknown track {command.track_id!r}",
            )
        if command.armed:
            session.armed_tracks.add(command.track_id)
        else:
            session.armed_tracks.discard(command.track_id)
        return self._success("arm_track")

    def set_transport(self, command: SetTransportCommandV1) -> RuntimeCommandResultV1:
        """Set transport mode."""
        session = self._session
        if session is None:
            return self._failure(
                "set_transport", FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        session.transport_mode = command.mode
        return self._success("set_transport")

    def select_synth(self, command: SelectSynthCommandV1) -> RuntimeCommandResultV1:
        """Load a synth by registry identifier."""
        session = self._session
        if session is None:
            return self._failure(
                "select_synth", FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        if self.scenario.synth_load_fails:
            return self._failure(
                "select_synth",
                FaultCode.SYNTH_LOAD_FAILED,
                "synth",
                f"synth {command.synth_id!r} failed to load",
            )
        if command.synth_id != FAKE_SYNTH_ID:
            return self._failure(
                "select_synth",
                FaultCode.SYNTH_MISSING,
                "synth",
                f"synth {command.synth_id!r} is not available in this runtime",
            )
        session.synth_id = command.synth_id
        return self._success("select_synth")

    def set_loop(self, command: SetLoopCommandV1) -> RuntimeCommandResultV1:
        """Set or clear the loop region."""
        if self._session is None:
            return self._failure(
                "set_loop", FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        return self._success("set_loop")

    def panic(self, command: PanicCommandV1) -> RuntimeCommandResultV1:
        """Silence every sounding note. Valid in any state."""
        if self.scenario.panic_fails:
            return self._failure(
                "panic", FaultCode.PANIC_FAILED, "synth", "panic did not clear sounding notes"
            )
        if self._session is not None:
            self._session.sounding_notes.clear()
        return self._success("panic")

    # --- capture ----------------------------------------------------------

    def start_capture(self, command: StartCaptureCommandV1) -> RuntimeCommandResultV1:
        """Begin capturing on an armed track."""
        session = self._session
        if session is None:
            return self._failure(
                "start_capture", FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        if command.track_id not in session.armed_tracks:
            return self._failure(
                "start_capture",
                FaultCode.INVALID_STATE,
                "capture",
                f"track {command.track_id!r} is not armed",
            )
        if self._active_capture_id is not None:
            return self._failure(
                "start_capture", FaultCode.INVALID_STATE, "capture", "a capture is already active"
            )
        self._captures[command.capture_id] = build_raw_capture(
            capture_id=command.capture_id,
            session_id=command.session_id,
            runtime_identity=self.identity(),
            source_identity=self._source_identity(),
            started_at=self._clock.now(),
            tempo_context=session.config.transport.tempo_bpm,
            meter_context=session.config.transport.meter,
            provenance=(("runtime", self.runtime_id),),
        )
        self._active_capture_id = command.capture_id
        session.transport_mode = TransportMode.RECORDING
        return self._success("start_capture")

    def feed_note_on(
        self,
        note: int,
        velocity: int,
        *,
        channel: int = 0,
        time_ns: int | None = None,
        source_string: int | None = None,
    ) -> None:
        """Test hook: deliver a note-on to the active capture."""
        self._feed(
            MidiEventType.NOTE_ON,
            channel=channel,
            time_ns=time_ns,
            note=note,
            velocity=velocity,
            source_string=source_string,
        )
        if self._session is not None:
            self._session.sounding_notes.append((channel, note))

    def feed_note_off(
        self,
        note: int,
        *,
        channel: int = 0,
        time_ns: int | None = None,
        source_string: int | None = None,
    ) -> None:
        """Test hook: deliver a note-off to the active capture."""
        self._feed(
            MidiEventType.NOTE_OFF,
            channel=channel,
            time_ns=time_ns,
            note=note,
            velocity=0,
            source_string=source_string,
        )
        if self._session is not None and (channel, note) in self._session.sounding_notes:
            self._session.sounding_notes.remove((channel, note))

    def feed_control_change(
        self, controller: int, value: int, *, channel: int = 0, time_ns: int | None = None
    ) -> None:
        """Test hook: deliver a control-change event."""
        self._feed(
            MidiEventType.CONTROL_CHANGE,
            channel=channel,
            time_ns=time_ns,
            controller=controller,
            controller_value=value,
        )

    def feed_pitch_bend(self, bend: int, *, channel: int = 0, time_ns: int | None = None) -> None:
        """Test hook: deliver a pitch-bend event."""
        self._feed(MidiEventType.PITCH_BEND, channel=channel, time_ns=time_ns, pitch_bend=bend)

    def crash(self) -> RuntimeCommandResultV1:
        """Test hook: simulate the runtime dying.

        An active capture closes as ``INTERRUPTED`` with the fault attached, keeping
        every event accepted so far. Nothing is invented and nothing is discarded.
        """
        fault = self._fault(
            FaultCode.RUNTIME_CRASHED,
            "process",
            "runtime process exited unexpectedly",
            recoverable=False,
        )
        if self._active_capture_id is not None:
            capture = self._captures[self._active_capture_id]
            sounding = len(self._session.sounding_notes) if self._session else 0
            warning = (
                f"capture ended without note-off for {sounding} sounding note(s)"
                if sounding
                else None
            )
            self._captures[self._active_capture_id] = mark_capture_interrupted(
                capture, ended_at=self._clock.now(), fault=fault, warning=warning
            )
            self._active_capture_id = None
        self._state = RuntimeState.FAILED
        return RuntimeCommandResultV1(
            schema_version=RuntimeCommandResultV1.SCHEMA_VERSION,
            command="crash",
            runtime_id=self.runtime_id,
            succeeded=False,
            completed_at=self._clock.now(),
            fault=fault,
        )

    def stop_capture(self, command: StopCaptureCommandV1) -> RuntimeCommandResultV1:
        """End the capture with an explicit terminal state."""
        if self._active_capture_id != command.capture_id:
            return self._failure(
                "stop_capture",
                FaultCode.INVALID_STATE,
                "capture",
                f"capture {command.capture_id!r} is not active",
            )
        capture = self._captures[command.capture_id]
        warnings: tuple[str, ...] = ()
        if self.scenario.stuck_notes and self._session and self._session.sounding_notes:
            warnings = (f"{len(self._session.sounding_notes)} note(s) still sounding at stop",)
        state = (
            CaptureCompletionState.CANCELLED
            if command.cancelled
            else CaptureCompletionState.COMPLETE
        )
        self._captures[command.capture_id] = close_capture(
            capture, ended_at=command.ended_at, completion_state=state, warnings=warnings
        )
        self._active_capture_id = None
        if self._session is not None:
            self._session.transport_mode = TransportMode.STOPPED
        return self._success("stop_capture")

    def retrieve_capture(self, capture_id: str) -> CaptureResultV1:
        """Return a capture record, or a fault explaining why it is not available."""
        if self._session is None and capture_id not in self._captures:
            return self._capture_failure(
                capture_id, FaultCode.INVALID_STATE, "session", "no session prepared"
            )
        if capture_id not in self._captures:
            return self._capture_failure(
                capture_id,
                FaultCode.INVALID_STATE,
                "capture",
                f"capture {capture_id!r} has not started",
            )
        return CaptureResultV1(
            schema_version=CaptureResultV1.SCHEMA_VERSION,
            capture_id=capture_id,
            succeeded=True,
            completed_at=self._clock.now(),
            capture=self._captures[capture_id],
        )

    def export_diagnostics(self) -> RuntimeDiagnosticResultV1:
        """Collect a read-only diagnostic snapshot."""
        diagnostics = collect_runtime_diagnostics(
            identity=self.identity(),
            capabilities=self.capabilities(),
            health=self.health(),
            collected_at=self._clock.now(),
        )
        return RuntimeDiagnosticResultV1(
            schema_version=RuntimeDiagnosticResultV1.SCHEMA_VERSION,
            runtime_id=self.runtime_id,
            succeeded=True,
            completed_at=self._clock.now(),
            diagnostics=diagnostics,
            health=diagnostics.health,
        )

    # --- internals --------------------------------------------------------

    def _feed(
        self, event_type: MidiEventType, *, channel: int, time_ns: int | None, **fields_: int | None
    ) -> None:
        if self._active_capture_id is None:
            raise PerformanceContractError("no active capture to receive events")
        if self.scenario.crash_during_capture:
            raise PerformanceContractError("runtime crashed; call crash() to model this explicitly")
        capture = self._captures[self._active_capture_id]
        sequence = self._sequence
        self._sequence += 1
        event = CapturedMidiEventV1(
            schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
            event_id=f"evt-{sequence:04d}",
            sequence_number=sequence,
            event_type=event_type,
            capture_time_ns=time_ns if time_ns is not None else sequence * 100_000_000,
            channel=channel,
            source_port="fake-port-0",
            source_device="fake-device",
            **fields_,  # type: ignore[arg-type]
        )
        self._captures[self._active_capture_id] = append_events(capture, (event,))

    def _source_identity(self) -> CaptureSourceV1:
        return CaptureSourceV1(
            schema_version=CaptureSourceV1.SCHEMA_VERSION,
            source_id="fake-source",
            port="fake-port-0",
            device="fake-device",
            supplies_string_identity=False,
        )

    def _health(
        self,
        *,
        state: RuntimeState,
        process: SubsystemState,
        audio_backend: SubsystemState,
        audio_output: SubsystemState,
        midi_input: SubsystemState,
        synth: SubsystemState,
        session: SubsystemState,
        capture: SubsystemState,
        faults: tuple[RuntimeFaultV1, ...] = (),
    ) -> RuntimeHealthV1:
        return RuntimeHealthV1(
            schema_version=RuntimeHealthV1.SCHEMA_VERSION,
            runtime_id=self.runtime_id,
            checked_at=self._clock.now(),
            state=state,
            process=process,
            audio_backend=audio_backend,
            audio_output=audio_output,
            midi_input=midi_input,
            synth=synth,
            session=session,
            capture=capture,
            faults=faults,
        )

    def _fault(
        self, code: FaultCode, subsystem: str, detail: str, *, recoverable: bool = True
    ) -> RuntimeFaultV1:
        self._fault_counter += 1
        return RuntimeFaultV1(
            schema_version=RuntimeFaultV1.SCHEMA_VERSION,
            fault_id=f"fault-{self._fault_counter:04d}",
            code=code,
            subsystem=subsystem,
            detail=detail,
            occurred_at=self._clock.now(),
            recoverable=recoverable,
        )

    def _success(self, command: str) -> RuntimeCommandResultV1:
        return RuntimeCommandResultV1(
            schema_version=RuntimeCommandResultV1.SCHEMA_VERSION,
            command=command,
            runtime_id=self.runtime_id,
            succeeded=True,
            completed_at=self._clock.now(),
        )

    def _failure(
        self, command: str, code: FaultCode, subsystem: str, detail: str
    ) -> RuntimeCommandResultV1:
        return RuntimeCommandResultV1(
            schema_version=RuntimeCommandResultV1.SCHEMA_VERSION,
            command=command,
            runtime_id=self.runtime_id,
            succeeded=False,
            completed_at=self._clock.now(),
            fault=self._fault(code, subsystem, detail),
        )

    def _capture_failure(
        self, capture_id: str, code: FaultCode, subsystem: str, detail: str
    ) -> CaptureResultV1:
        return CaptureResultV1(
            schema_version=CaptureResultV1.SCHEMA_VERSION,
            capture_id=capture_id,
            succeeded=False,
            completed_at=self._clock.now(),
            fault=self._fault(code, subsystem, detail),
        )


def build_fake_session(
    *, session_id: str = "session-001", runtime_id: str = FAKE_RUNTIME_ID
) -> PerformanceSessionConfigV1:
    """A prepared single-track session matching the fake runtime's expectations."""
    return build_single_track_session(
        session_id=session_id,
        runtime_id=runtime_id,
        midi_input="fake-port-0",
        synth_id=FAKE_SYNTH_ID,
    )


__all__ = [
    "FAKE_CAPABILITIES",
    "FAKE_RUNTIME_ID",
    "FAKE_SYNTH_ID",
    "FAKE_VERSION",
    "FakeRuntime",
    "FakeRuntimeScenario",
    "build_fake_session",
]
