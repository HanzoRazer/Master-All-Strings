"""Failure modes, diagnostics, serialization, and the read-only CLIs.

Covers DO-006 §8.7 plus the supporting utilities. The theme is that nothing fails
silently: every failure mode produces an explicit, inspectable value rather than a
default that looks like success.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import EXAMPLE_DIR, T0, T1, make_event

from master_all_strings.performance import cli
from master_all_strings.performance.adapters.ardour import adapter as ardour_adapter
from master_all_strings.performance.adapters.ardour import models as ardour_models
from master_all_strings.performance.adapters.ardour.osc_client import (
    OSC_PATHS,
    UNSUPPORTED_OPERATIONS,
    BoundedOscClient,
    OscOperation,
)
from master_all_strings.performance.adapters.ardour.process import (
    ProcessStatus,
    StaticProcessInspector,
)
from master_all_strings.performance.adapters.fake_runtime import (
    FakeRuntime,
    FakeRuntimeScenario,
    build_fake_session,
)
from master_all_strings.performance.capture_normalization import close_capture
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.results import (
    CaptureResultV1,
    PerformanceExportResultV1,
    RuntimeCommandResultV1,
    RuntimeDiagnosticResultV1,
)
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeCapabilitySetV1,
    RuntimeFaultV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeKind,
    RuntimeState,
    SubsystemState,
)
from master_all_strings.performance.contracts.session import (
    MetronomeConfigV1,
    PerformanceSessionConfigV1,
    PerformanceSessionStateV1,
    SessionState,
    TrackKind,
    TransportMode,
)
from master_all_strings.performance.export import (
    capture_digest,
    serialize_performance_observation,
    serialize_raw_capture,
    serialize_runtime_health,
    to_dict,
    to_json,
)
from master_all_strings.performance.observations import derive_performance_observation
from master_all_strings.performance.runtime_diagnostics import (
    check_runtime_readiness,
    collect_runtime_diagnostics,
    render_diagnostic_report,
)
from master_all_strings.performance.session_builder import (
    build_loop_region,
    build_meter,
    build_metronome_config,
    build_single_track_session,
    build_transport_state,
)


def _fault(code: FaultCode = FaultCode.RUNTIME_CRASHED) -> RuntimeFaultV1:
    return RuntimeFaultV1(
        schema_version=RuntimeFaultV1.SCHEMA_VERSION,
        fault_id="fault-0001",
        code=code,
        subsystem="process",
        detail="detail",
        occurred_at=T0,
        recoverable=False,
    )


def _health(
    state: RuntimeState = RuntimeState.READY, **overrides: SubsystemState
) -> RuntimeHealthV1:
    subsystems = dict.fromkeys(RuntimeHealthV1.SUBSYSTEM_FIELDS, SubsystemState.READY)
    subsystems.update(overrides)
    return RuntimeHealthV1(
        schema_version=RuntimeHealthV1.SCHEMA_VERSION,
        runtime_id="fake",
        checked_at=T0,
        state=state,
        faults=(),
        **subsystems,  # type: ignore[arg-type]
    )


class TestHealthRefusesToOverstate:
    def test_ready_state_requires_every_infrastructure_subsystem(self) -> None:
        with pytest.raises(PerformanceContractError, match="every infrastructure subsystem"):
            _health(RuntimeState.READY, midi_input=SubsystemState.UNAVAILABLE)

    def test_ready_state_does_not_require_a_prepared_session(self) -> None:
        # Session-scoped subsystems are UNKNOWN before prepare_session. Requiring
        # them here would make start -> readiness -> prepare_session unreachable.
        health = _health(
            RuntimeState.READY,
            session=SubsystemState.UNKNOWN,
            capture=SubsystemState.UNKNOWN,
        )
        assert health.infrastructure_blocking() == ()
        assert health.session_blocking() == ("session", "capture")

    def test_readiness_is_true_before_a_session_exists(self) -> None:
        readiness = check_runtime_readiness(
            _health(
                RuntimeState.READY,
                session=SubsystemState.UNKNOWN,
                capture=SubsystemState.UNKNOWN,
            )
        )
        assert readiness.ready is True
        assert readiness.capture_ready is False
        assert readiness.capture_blocking_subsystems == ("session", "capture")

    def test_capture_ready_requires_ready(self) -> None:
        from master_all_strings.performance.contracts.runtime import RuntimeReadinessV1

        with pytest.raises(PerformanceContractError, match="capture_ready requires ready"):
            RuntimeReadinessV1(
                schema_version=RuntimeReadinessV1.SCHEMA_VERSION,
                runtime_id="fake",
                ready=False,
                health=_health(RuntimeState.READY),
                capture_ready=True,
            )

    def test_blocking_subsystems_are_listed_in_declaration_order(self) -> None:
        health = _health(
            RuntimeState.DEGRADED,
            audio_output=SubsystemState.UNAVAILABLE,
            midi_input=SubsystemState.FAULTED,
        )
        assert health.blocking_subsystems() == ("audio_output", "midi_input")

    def test_readiness_requires_the_runtime_state_to_agree(self) -> None:
        # Healthy subsystems while still probing must not read as ready.
        assert check_runtime_readiness(_health(RuntimeState.PROBING)).ready is False

    def test_readiness_is_true_only_when_everything_agrees(self) -> None:
        readiness = check_runtime_readiness(_health(RuntimeState.READY))
        assert readiness.ready is True
        assert readiness.capture_ready is True

    def test_readiness_cannot_claim_ready_with_blockers(self) -> None:
        from master_all_strings.performance.contracts.runtime import RuntimeReadinessV1

        with pytest.raises(PerformanceContractError, match="blocking subsystems"):
            RuntimeReadinessV1(
                schema_version=RuntimeReadinessV1.SCHEMA_VERSION,
                runtime_id="fake",
                ready=True,
                health=_health(RuntimeState.READY),
                blocking_subsystems=("midi_input",),
            )


class TestResultsRefuseContradictions:
    def test_failed_command_must_carry_a_fault(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry a fault"):
            RuntimeCommandResultV1(
                schema_version=RuntimeCommandResultV1.SCHEMA_VERSION,
                command="start",
                runtime_id="fake",
                succeeded=False,
                completed_at=T0,
            )

    def test_successful_command_must_not_carry_a_fault(self) -> None:
        with pytest.raises(PerformanceContractError, match="must not carry a fault"):
            RuntimeCommandResultV1(
                schema_version=RuntimeCommandResultV1.SCHEMA_VERSION,
                command="start",
                runtime_id="fake",
                succeeded=True,
                completed_at=T0,
                fault=_fault(),
            )

    def test_successful_capture_result_must_carry_a_capture(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry a capture"):
            CaptureResultV1(
                schema_version=CaptureResultV1.SCHEMA_VERSION,
                capture_id="capture-1",
                succeeded=True,
                completed_at=T0,
            )

    def test_capture_result_id_must_match_the_capture(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="must match"):
            CaptureResultV1(
                schema_version=CaptureResultV1.SCHEMA_VERSION,
                capture_id="a-different-id",
                succeeded=True,
                completed_at=T0,
                capture=closed_capture,
            )

    def test_failed_capture_result_must_carry_a_fault(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry a fault"):
            CaptureResultV1(
                schema_version=CaptureResultV1.SCHEMA_VERSION,
                capture_id="capture-1",
                succeeded=False,
                completed_at=T0,
            )

    def test_failed_export_result_must_carry_a_fault(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry a fault"):
            PerformanceExportResultV1(
                schema_version=PerformanceExportResultV1.SCHEMA_VERSION,
                export_id="exp-1",
                capture_id="capture-1",
                succeeded=False,
                completed_at=T0,
            )

    def test_successful_export_result_is_valid(self) -> None:
        result = PerformanceExportResultV1(
            schema_version=PerformanceExportResultV1.SCHEMA_VERSION,
            export_id="exp-1",
            capture_id="capture-1",
            succeeded=True,
            completed_at=T0,
            byte_count=128,
        )
        assert result.byte_count == 128

    def test_successful_diagnostic_result_must_carry_diagnostics(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry diagnostics"):
            RuntimeDiagnosticResultV1(
                schema_version=RuntimeDiagnosticResultV1.SCHEMA_VERSION,
                runtime_id="fake",
                succeeded=True,
                completed_at=T0,
            )

    def test_failed_diagnostic_result_must_carry_a_fault(self) -> None:
        with pytest.raises(PerformanceContractError, match="must carry a fault"):
            RuntimeDiagnosticResultV1(
                schema_version=RuntimeDiagnosticResultV1.SCHEMA_VERSION,
                runtime_id="fake",
                succeeded=False,
                completed_at=T0,
            )


class TestFailureScenarios:
    @pytest.mark.parametrize(
        ("scenario", "expected"),
        [
            (FakeRuntimeScenario(start_times_out=True), FaultCode.STARTUP_TIMEOUT),
            (FakeRuntimeScenario(midi_input_missing=True), FaultCode.MIDI_INPUT_MISSING),
            (FakeRuntimeScenario(audio_output_missing=True), FaultCode.AUDIO_OUTPUT_MISSING),
            (FakeRuntimeScenario(synth_load_fails=True), FaultCode.SYNTH_LOAD_FAILED),
        ],
    )
    def test_each_failure_reports_its_own_code(
        self, scenario: FakeRuntimeScenario, expected: FaultCode
    ) -> None:
        # A single generic failure code would make these indistinguishable.
        runtime = FakeRuntime(scenario)
        from master_all_strings.performance.contracts.commands import (
            PrepareSessionCommandV1,
            SelectSynthCommandV1,
            StartRuntimeCommandV1,
        )

        result = runtime.start(
            StartRuntimeCommandV1(
                schema_version=StartRuntimeCommandV1.SCHEMA_VERSION,
                runtime_id="fake",
                timeout_ms=1000,
            )
        )
        if not result.succeeded:
            assert result.fault is not None
            assert result.fault.code is expected
            return
        result = runtime.prepare_session(
            PrepareSessionCommandV1(
                schema_version=PrepareSessionCommandV1.SCHEMA_VERSION,
                session_config=build_fake_session(),
            )
        )
        if not result.succeeded:
            assert result.fault is not None
            assert result.fault.code is expected
            return
        result = runtime.select_synth(
            SelectSynthCommandV1(
                schema_version=SelectSynthCommandV1.SCHEMA_VERSION,
                session_id="session-001",
                track_id="track-1",
                synth_id="fake-synth",
            )
        )
        assert result.fault is not None
        assert result.fault.code is expected

    def test_export_before_closure_is_refused(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="closed capture"):
            derive_performance_observation(
                open_capture,
                observation_id="obs-1",
                observed_at=T1,
                runtime_state=RuntimeState.READY,
            )

    def test_unsupported_version_is_detectable_without_running(self) -> None:
        assert ardour_models.is_supported_version(None) is False
        assert ardour_models.is_supported_version("9.7") is True
        assert ardour_models.is_supported_version("10.0") is False
        assert ardour_models.is_supported_version("9.6") is False
        assert ardour_models.is_supported_version("nonsense") is False

    def test_version_parsing_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="unparseable"):
            ardour_models.parse_version("x")

    def test_process_status_reports_version_support(self) -> None:
        inspector = StaticProcessInspector(
            ProcessStatus(running=True, pid=42, reported_version="9.7")
        )
        assert inspector.status().version_supported is True

    def test_unresolved_process_version_is_unsupported(self) -> None:
        # GAP-002: Ardour 9.7 exposes no version over OSC, so this is a real state.
        inspector = StaticProcessInspector(
            ProcessStatus(running=True, pid=42, reported_version=None)
        )
        assert inspector.status().version_supported is False


class TestArdourScaffoldRefusesToPretend:
    def test_building_the_adapter_raises(self) -> None:
        with pytest.raises(ardour_adapter.ArdourRuntimeNotImplementedError):
            ardour_adapter.build_ardour_runtime()

    def test_the_reason_points_at_the_gap_audit(self) -> None:
        assert "ARDOUR_GAP_AUDIT" in ardour_adapter.NOT_IMPLEMENTED_REASON

    def test_no_runtime_version_is_claimed_verified(self) -> None:
        assert ardour_models.VERIFIED_RUNTIME_VERSIONS == ()
        assert ardour_models.VERIFIED_SOURCE_VERSION == "9.7"


class TestBoundedOscSurface:
    def test_permitted_operations_send(self) -> None:
        sent: list[tuple[str, tuple[object, ...]]] = []

        class Transport:
            def send(self, path: str, args: tuple[object, ...]) -> None:
                sent.append((path, args))

        client = BoundedOscClient(Transport())
        assert client.send(OscOperation.PANIC) == "/midi_panic"
        assert sent == [("/midi_panic", ())]

    def test_arbitrary_paths_cannot_be_sent(self) -> None:
        # An open bridge would make the adapter boundary decorative.
        class Transport:
            def send(self, path: str, args: tuple[object, ...]) -> None:
                raise AssertionError("must not be reached")

        with pytest.raises(ValueError, match="bounded"):
            BoundedOscClient(Transport()).send("/anything")  # type: ignore[arg-type]

    def test_every_operation_has_a_path(self) -> None:
        assert set(OSC_PATHS) == set(OscOperation)

    def test_absent_operations_explain_themselves(self) -> None:
        assert "GAP-001" in (BoundedOscClient.why_unsupported("set_tempo") or "")
        assert "GAP-002" in (BoundedOscClient.why_unsupported("runtime_version") or "")
        assert BoundedOscClient.why_unsupported("play") is None

    def test_tempo_and_version_are_recorded_as_unsupported(self) -> None:
        assert set(UNSUPPORTED_OPERATIONS) == {"set_tempo", "set_meter", "runtime_version"}


class TestSessionBuilders:
    def test_single_track_session_is_within_the_first_target(self) -> None:
        session = build_single_track_session(
            session_id="s", runtime_id="r", midi_input="in", synth_id="fake-synth"
        )
        assert len(session.tracks) == 1
        assert session.tracks[0].kind is TrackKind.MIDI

    def test_no_multitrack_builder_exists(self) -> None:
        # The absence of a builder is the cheapest place to say multitrack is out of
        # scope.
        import master_all_strings.performance.session_builder as builder

        assert not any("multitrack" in name.lower() for name in dir(builder))

    def test_two_tracks_are_rejected(self) -> None:
        session = build_single_track_session(
            session_id="s", runtime_id="r", midi_input="in", synth_id="fake-synth"
        )
        import dataclasses

        second = dataclasses.replace(session.tracks[0], track_id="track-2")
        with pytest.raises(PerformanceContractError, match="at most 1 track"):
            dataclasses.replace(session, tracks=(session.tracks[0], second))

    def test_audio_track_is_rejected(self) -> None:
        import dataclasses

        session = build_single_track_session(
            session_id="s", runtime_id="r", midi_input="in", synth_id="fake-synth"
        )
        with pytest.raises(PerformanceContractError, match="audio tracks are out of scope"):
            dataclasses.replace(session.tracks[0], kind=TrackKind.AUDIO)

    def test_armed_track_without_input_is_rejected(self) -> None:
        import dataclasses

        session = build_single_track_session(
            session_id="s", runtime_id="r", midi_input="in", synth_id="fake-synth"
        )
        with pytest.raises(PerformanceContractError, match="must declare a midi_input"):
            dataclasses.replace(session.tracks[0], midi_input=None)

    def test_loop_region_requires_a_positive_span(self) -> None:
        with pytest.raises(PerformanceContractError, match="greater than start_tick"):
            build_loop_region(100, 100)

    def test_metronome_level_is_bounded(self) -> None:
        with pytest.raises(PerformanceContractError, match="between 0.0 and 1.0"):
            build_metronome_config(level=2.0)

    def test_tempo_is_bounded(self) -> None:
        with pytest.raises(PerformanceContractError, match="tempo_bpm"):
            build_transport_state(tempo_bpm=1000.0)

    def test_meter_beat_unit_is_a_note_value(self) -> None:
        with pytest.raises(PerformanceContractError, match="beat_unit"):
            build_meter(4, 5)

    def test_transport_accepts_a_loop(self) -> None:
        state = build_transport_state(loop=build_loop_region(0, 960))
        assert state.loop is not None

    def test_metronome_config_defaults_are_valid(self) -> None:
        assert build_metronome_config().enabled is False

    def test_session_config_rejects_a_non_meter(self) -> None:
        with pytest.raises(PerformanceContractError, match="MetronomeConfigV1"):
            build_single_track_session(
                session_id="s",
                runtime_id="r",
                midi_input="in",
                synth_id="fake-synth",
                metronome="not-a-metronome",  # type: ignore[arg-type]
            )


class TestSessionState:
    def test_recording_requires_an_active_capture(self) -> None:
        # Recording with nowhere for events to land is not representable.
        with pytest.raises(PerformanceContractError, match="active_capture_id"):
            PerformanceSessionStateV1(
                schema_version=PerformanceSessionStateV1.SCHEMA_VERSION,
                session_id="s",
                runtime_id="r",
                state=SessionState.ACTIVE,
                transport=build_transport_state(mode=TransportMode.RECORDING),
            )

    def test_recording_with_a_capture_is_valid(self) -> None:
        state = PerformanceSessionStateV1(
            schema_version=PerformanceSessionStateV1.SCHEMA_VERSION,
            session_id="s",
            runtime_id="r",
            state=SessionState.ACTIVE,
            transport=build_transport_state(mode=TransportMode.RECORDING),
            active_capture_id="capture-1",
        )
        assert state.active_capture_id == "capture-1"

    def test_duplicate_armed_tracks_are_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="duplicates"):
            PerformanceSessionStateV1(
                schema_version=PerformanceSessionStateV1.SCHEMA_VERSION,
                session_id="s",
                runtime_id="r",
                state=SessionState.PREPARED,
                transport=build_transport_state(),
                armed_track_ids=("t", "t"),
            )


class TestSerialization:
    def test_capture_serializes_deterministically(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        assert serialize_raw_capture(closed_capture) == serialize_raw_capture(closed_capture)

    def test_digest_changes_when_content_changes(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        import dataclasses

        other = dataclasses.replace(closed_capture, capture_id="capture-2")
        assert capture_digest(closed_capture) != capture_digest(other)

    def test_health_serializes(self) -> None:
        payload = json.loads(serialize_runtime_health(_health()))
        assert payload["state"] == "ready"

    def test_observation_serializes(self, closed_capture: RawPerformanceCaptureV1) -> None:
        observation = derive_performance_observation(
            closed_capture,
            observation_id="obs-1",
            observed_at=T1,
            runtime_state=RuntimeState.READY,
        )
        payload = json.loads(serialize_performance_observation(observation))
        assert payload["capture_id"] == closed_capture.capture_id

    def test_mapping_fields_serialize_as_objects(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        payload = json.loads(serialize_raw_capture(closed_capture))
        assert payload["provenance"] == {"fixture": "open_capture"}

    def test_serializers_reject_the_wrong_type(self) -> None:
        with pytest.raises(PerformanceContractError, match="RawPerformanceCaptureV1"):
            serialize_raw_capture(_health())  # type: ignore[arg-type]
        with pytest.raises(PerformanceContractError, match="RuntimeHealthV1"):
            serialize_runtime_health("x")  # type: ignore[arg-type]
        with pytest.raises(PerformanceContractError, match="PerformanceObservationV1"):
            serialize_performance_observation("x")  # type: ignore[arg-type]

    def test_to_dict_requires_a_contract(self) -> None:
        with pytest.raises(PerformanceContractError, match="contract dataclass"):
            to_dict("not a contract")

    def test_to_json_ends_with_a_newline(self) -> None:
        assert to_json(_health()).endswith("\n")

    def test_deserializer_rejects_missing_keys(self) -> None:
        from master_all_strings.performance.export import deserialize_meter

        with pytest.raises(PerformanceContractError, match="missing required keys"):
            deserialize_meter({"schema_version": "1.0.0"})

    def test_deserializer_rejects_unexpected_keys(self) -> None:
        from master_all_strings.performance.export import deserialize_meter

        with pytest.raises(PerformanceContractError, match="unexpected keys"):
            deserialize_meter(
                {
                    "schema_version": "1.0.0",
                    "beats_per_bar": 4,
                    "beat_unit": 4,
                    "extra": 1,
                }
            )

    def test_deserializer_rejects_a_non_object_mapping(self) -> None:
        from master_all_strings.performance.export import _mapping_to_pairs

        with pytest.raises(PerformanceContractError, match="must be an object"):
            _mapping_to_pairs([], "provenance")


class TestObservationsFromRealCaptures:
    def test_observation_summarises_a_complete_take(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        observation = derive_performance_observation(
            closed_capture,
            observation_id="obs-1",
            observed_at=T1,
            runtime_state=RuntimeState.READY,
        )
        assert observation.event_count == 2
        assert observation.note_on_count == 1
        assert observation.note_off_count == 1
        assert observation.completion_state is CaptureCompletionState.COMPLETE

    def test_observation_reports_velocity_bounds(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        observation = derive_performance_observation(
            closed_capture,
            observation_id="obs-1",
            observed_at=T1,
            runtime_state=RuntimeState.READY,
        )
        assert observation.velocity_min == 96
        assert observation.velocity_max == 96

    def test_observation_of_an_empty_capture_has_no_bounds(
        self,
        runtime_identity: RuntimeIdentityV1,
        capture_source: object,
        meter: object,
    ) -> None:
        from master_all_strings.performance.capture_normalization import build_raw_capture

        capture = close_capture(
            build_raw_capture(
                capture_id="capture-empty",
                session_id="session-001",
                runtime_identity=runtime_identity,
                source_identity=capture_source,  # type: ignore[arg-type]
                started_at=T0,
                tempo_context=120.0,
                meter_context=meter,  # type: ignore[arg-type]
            ),
            ended_at=T1,
        )
        observation = derive_performance_observation(
            capture, observation_id="obs-1", observed_at=T1, runtime_state=RuntimeState.READY
        )
        assert observation.first_event_time_ns is None
        assert observation.velocity_min is None

    def test_observation_carries_fault_codes(
        self, open_capture: RawPerformanceCaptureV1, crash_fault: RuntimeFaultV1
    ) -> None:
        from master_all_strings.performance.capture_normalization import (
            mark_capture_interrupted,
        )

        interrupted = mark_capture_interrupted(open_capture, ended_at=T1, fault=crash_fault)
        observation = derive_performance_observation(
            interrupted, observation_id="obs-1", observed_at=T1, runtime_state=RuntimeState.FAILED
        )
        assert observation.fault_codes == ("runtime_crashed",)
        assert observation.completion_state is CaptureCompletionState.INTERRUPTED


class TestDiagnosticRendering:
    def test_report_is_deterministic(self) -> None:
        diagnostics = collect_runtime_diagnostics(
            identity=RuntimeIdentityV1(
                schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
                runtime_id="fake",
                runtime_kind=RuntimeKind.FAKE,
                reported_version="1.0.0",
                version_policy="1.0.0",
                version_supported=True,
            ),
            capabilities=RuntimeCapabilitySetV1(
                schema_version=RuntimeCapabilitySetV1.SCHEMA_VERSION,
                runtime_id="fake",
                capabilities=(),
            ),
            health=_health(),
            collected_at=T0,
        )
        assert render_diagnostic_report(diagnostics) == render_diagnostic_report(diagnostics)

    def test_report_names_every_subsystem(self) -> None:
        runtime = FakeRuntime()
        result = runtime.export_diagnostics()
        assert result.diagnostics is not None
        report = render_diagnostic_report(result.diagnostics)
        for name in RuntimeHealthV1.SUBSYSTEM_FIELDS:
            assert name in report

    def test_report_shows_faults(self) -> None:
        health = RuntimeHealthV1(
            schema_version=RuntimeHealthV1.SCHEMA_VERSION,
            runtime_id="fake",
            checked_at=T0,
            state=RuntimeState.DEGRADED,
            process=SubsystemState.READY,
            audio_backend=SubsystemState.READY,
            audio_output=SubsystemState.READY,
            midi_input=SubsystemState.UNAVAILABLE,
            synth=SubsystemState.READY,
            session=SubsystemState.READY,
            capture=SubsystemState.READY,
            faults=(_fault(FaultCode.MIDI_INPUT_MISSING),),
        )
        diagnostics = collect_runtime_diagnostics(
            identity=RuntimeIdentityV1(
                schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
                runtime_id="fake",
                runtime_kind=RuntimeKind.FAKE,
                reported_version=None,
                version_policy="1.0.0",
                version_supported=False,
            ),
            capabilities=RuntimeCapabilitySetV1(
                schema_version=RuntimeCapabilitySetV1.SCHEMA_VERSION,
                runtime_id="fake",
                capabilities=(),
            ),
            health=health,
            collected_at=T0,
            notes=("supplied note",),
        )
        report = render_diagnostic_report(diagnostics)
        assert "midi_input_missing" in report
        assert "unresolved" in report
        assert "supplied note" in report
        assert "does not report the panic capability" in report

    def test_capability_set_rejects_duplicates(self) -> None:
        from master_all_strings.performance.contracts.runtime import RuntimeCapability

        with pytest.raises(PerformanceContractError, match="duplicates"):
            RuntimeCapabilitySetV1(
                schema_version=RuntimeCapabilitySetV1.SCHEMA_VERSION,
                runtime_id="fake",
                capabilities=(RuntimeCapability.PANIC, RuntimeCapability.PANIC),
            )


class TestReadOnlyClis:
    def test_validate_reports_placeholders_on_the_reference_config(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.validate_main([]) == 1
        assert "placeholder" in capsys.readouterr().out

    def test_validate_accepts_a_deployable_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = json.loads((EXAMPLE_DIR / "pi_ardour_reference_v1.json").read_text(encoding="utf-8"))
        raw.update(
            executable="/usr/bin/ardour9",
            session_template="/opt/mas/template",
            audio_output="hw:0,0",
            midi_inputs=["hw:1,0,0"],
        )
        path = tmp_path / "deployable.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert cli.validate_main([str(path)]) == 0
        assert "OK" in capsys.readouterr().out

    def test_validate_reports_an_unreadable_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.validate_main([str(tmp_path / "missing.json")]) == 1
        assert "invalid" in capsys.readouterr().out

    def test_inspect_renders_the_full_report(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli.inspect_main([])
        out = capsys.readouterr().out
        assert code == 1  # the reference config still carries placeholders
        assert "synth registry" in out
        assert "fake runtime readiness" in out
        assert "NOT distributable" in out

    def test_inspect_reports_an_unreadable_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.inspect_main([str(tmp_path / "missing.json")]) == 1
        assert "invalid" in capsys.readouterr().out

    def test_inspect_reports_no_findings_for_a_deployable_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        raw = json.loads((EXAMPLE_DIR / "pi_ardour_reference_v1.json").read_text(encoding="utf-8"))
        raw.update(
            executable="/usr/bin/ardour9",
            session_template="/opt/mas/template",
            audio_output="hw:0,0",
            midi_inputs=["hw:1,0,0"],
        )
        path = tmp_path / "deployable.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert cli.inspect_main([str(path)]) == 0
        assert "findings         none" in capsys.readouterr().out


class TestConfigContractGuards:
    def test_metadata_entries_must_be_pairs(self) -> None:
        from master_all_strings.performance.configuration import parse_runtime_config

        raw = json.loads((EXAMPLE_DIR / "pi_ardour_reference_v1.json").read_text(encoding="utf-8"))
        config = parse_runtime_config(raw)
        import dataclasses

        with pytest.raises(PerformanceContractError, match="\\(key, value\\) pairs"):
            dataclasses.replace(config, metadata=(("only-one",),))  # type: ignore[arg-type]

    def test_session_config_requires_at_least_one_track(self) -> None:
        import dataclasses

        session: PerformanceSessionConfigV1 = build_single_track_session(
            session_id="s", runtime_id="r", midi_input="in", synth_id="fake-synth"
        )
        with pytest.raises(PerformanceContractError, match="at least one track"):
            dataclasses.replace(session, tracks=())

    def test_metronome_requires_a_numeric_level(self) -> None:
        with pytest.raises(PerformanceContractError, match="level must be a number"):
            MetronomeConfigV1(
                schema_version=MetronomeConfigV1.SCHEMA_VERSION,
                enabled=True,
                count_in_bars=0,
                level="loud",  # type: ignore[arg-type]
            )

    def test_event_channel_bounds_are_enforced(self) -> None:
        with pytest.raises(PerformanceContractError, match="channel"):
            make_event(0, channel=16)


class TestDeterministicClock:
    """Time enters the Performance package here and nowhere else."""

    def test_ticks_advance_one_second(self) -> None:
        from master_all_strings.performance.adapters.clock import DeterministicClock

        clock = DeterministicClock()
        assert clock.now() == "2026-07-24T10:00:00Z"
        assert clock.now() == "2026-07-24T10:00:01Z"

    def test_minutes_and_hours_roll_over(self) -> None:
        from master_all_strings.performance.adapters.clock import DeterministicClock

        clock = DeterministicClock(origin_second=3661)
        assert clock.now() == "2026-07-24T11:01:01Z"

    def test_running_past_midnight_is_refused(self) -> None:
        from master_all_strings.performance.adapters.clock import DeterministicClock

        # Better to fail loudly than to emit an hour-24 timestamp the contract would
        # then reject with a confusing message far from the cause.
        clock = DeterministicClock(origin_second=14 * 3600)
        with pytest.raises(ValueError, match="past midnight"):
            clock.now()

    def test_an_explicit_date_is_honoured(self) -> None:
        from master_all_strings.performance.adapters.clock import DeterministicClock

        assert DeterministicClock(date="2026-01-01").now().startswith("2026-01-01T")


class TestArdourVersionParsing:
    """`ardour --version` and revision.cc do not agree on format."""

    @pytest.mark.parametrize(
        ("reported", "expected"),
        [
            ("9.7", (9, 7)),
            ("9.7.0", (9, 7)),
            ("Ardour 9.7.0", (9, 7)),
            ("ardour 9.7", (9, 7)),
            ("v9.7", (9, 7)),
            ("9.7-rc1", (9, 7)),
            ("9.7.0~ppa1", (9, 7)),
            ("9.7.0+build2", (9, 7)),
            ("  9.7  ", (9, 7)),
        ],
    )
    def test_real_world_forms_parse(self, reported: str, expected: tuple[int, int]) -> None:
        assert ardour_models.parse_version(reported) == expected

    @pytest.mark.parametrize("reported", ["", "nonsense", "9", "9.x", "x.7"])
    def test_unparseable_forms_are_rejected(self, reported: str) -> None:
        with pytest.raises(ValueError, match="unparseable"):
            ardour_models.parse_version(reported)

    @pytest.mark.parametrize("reported", ["9.7", "9.7.0", "Ardour 9.7.0", "9.8", "9.99"])
    def test_supported_versions(self, reported: str) -> None:
        assert ardour_models.is_supported_version(reported) is True

    @pytest.mark.parametrize("reported", ["9.6", "10.0", "8.12", "nonsense"])
    def test_unsupported_versions(self, reported: str) -> None:
        assert ardour_models.is_supported_version(reported) is False


class TestRetrieveCaptureCommand:
    def test_command_requires_a_capture_id(self) -> None:
        from master_all_strings.performance.contracts.commands import RetrieveCaptureCommandV1

        with pytest.raises(PerformanceContractError, match="capture_id"):
            RetrieveCaptureCommandV1(
                schema_version=RetrieveCaptureCommandV1.SCHEMA_VERSION, capture_id=""
            )

    def test_session_id_is_optional(self) -> None:
        from master_all_strings.performance.contracts.commands import RetrieveCaptureCommandV1

        command = RetrieveCaptureCommandV1(
            schema_version=RetrieveCaptureCommandV1.SCHEMA_VERSION, capture_id="capture-1"
        )
        assert command.session_id is None

    def test_blank_session_id_is_rejected(self) -> None:
        from master_all_strings.performance.contracts.commands import RetrieveCaptureCommandV1

        with pytest.raises(PerformanceContractError, match="session_id"):
            RetrieveCaptureCommandV1(
                schema_version=RetrieveCaptureCommandV1.SCHEMA_VERSION,
                capture_id="capture-1",
                session_id="  ",
            )


class TestResourceDiscovery:
    def test_resource_directory_resolves(self) -> None:
        from master_all_strings.performance.configuration import EXAMPLE_DIR, SCHEMA_DIR

        assert SCHEMA_DIR.is_dir()
        assert EXAMPLE_DIR.is_dir()

    def test_discovery_walks_up_rather_than_counting_parents(self) -> None:
        # A fixed parents[N] hop encodes the current layout and breaks silently if
        # the package moves; walking up fails loudly instead.
        import inspect

        from master_all_strings.performance import configuration

        source = inspect.getsource(configuration._find_resource_dir)
        assert "parents" in source
        assert "is_dir()" in source


class TestDiagnosticsNotesValidation:
    def test_blank_note_is_rejected(self) -> None:
        from master_all_strings.performance.contracts.runtime import (
            RuntimeCapabilitySetV1,
            RuntimeDiagnosticsV1,
        )

        with pytest.raises(PerformanceContractError, match="notes entry"):
            RuntimeDiagnosticsV1(
                schema_version=RuntimeDiagnosticsV1.SCHEMA_VERSION,
                runtime_id="fake",
                collected_at=T0,
                identity=RuntimeIdentityV1(
                    schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
                    runtime_id="fake",
                    runtime_kind=RuntimeKind.FAKE,
                    reported_version="1.0.0",
                    version_policy="1.0.0",
                    version_supported=True,
                ),
                capabilities=RuntimeCapabilitySetV1(
                    schema_version=RuntimeCapabilitySetV1.SCHEMA_VERSION,
                    runtime_id="fake",
                    capabilities=(),
                ),
                health=_health(),
                notes=("  ",),
            )
