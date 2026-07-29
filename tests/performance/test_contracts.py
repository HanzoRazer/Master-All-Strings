"""Contract-level invariants (DO-006 §8.1).

These assert the properties every versioned Performance contract must hold, rather
than exercising any one contract's happy path. A regression here means a contract has
stopped being trustworthy as a record.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from helpers import T0, make_event

from master_all_strings.core.foundation import SpatialMappingError
from master_all_strings.performance.contracts import capture as capture_mod
from master_all_strings.performance.contracts import commands as commands_mod
from master_all_strings.performance.contracts import ingestion as ingestion_mod
from master_all_strings.performance.contracts import results as results_mod
from master_all_strings.performance.contracts import runtime as runtime_mod
from master_all_strings.performance.contracts import session as session_mod
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CapturedMidiEventV1,
    MidiEventType,
    PerformanceObservationV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import (
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeKind,
    RuntimeState,
    SubsystemState,
)

CONTRACT_MODULES = (
    runtime_mod,
    session_mod,
    capture_mod,
    commands_mod,
    results_mod,
    ingestion_mod,
)


def _contract_classes() -> list[type]:
    seen: dict[str, type] = {}
    for module in CONTRACT_MODULES:
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and dataclasses.is_dataclass(obj)
                and obj.__module__ == module.__name__
            ):
                seen[f"{module.__name__}.{name}"] = obj
    return list(seen.values())


ALL_CONTRACTS = _contract_classes()


class TestVersionedContracts:
    def test_every_contract_declares_a_schema_version_field(self) -> None:
        for contract in ALL_CONTRACTS:
            names = {f.name for f in dataclasses.fields(contract)}
            assert "schema_version" in names, contract.__name__

    def test_every_contract_declares_a_schema_version_constant(self) -> None:
        for contract in ALL_CONTRACTS:
            assert hasattr(contract, "SCHEMA_VERSION"), contract.__name__

    def test_schema_versions_are_fixed_not_ranges(self) -> None:
        # A record claiming a version we do not implement must fail loudly rather
        # than be read with the wrong field meanings.
        for contract in ALL_CONTRACTS:
            version = contract.SCHEMA_VERSION  # type: ignore[attr-defined]
            assert version.count(".") == 2, contract.__name__

    def test_every_contract_is_frozen(self) -> None:
        for contract in ALL_CONTRACTS:
            params = contract.__dataclass_params__  # type: ignore[attr-defined]
            assert params.frozen, f"{contract.__name__} must be frozen"

    def test_no_contract_declares_a_mutable_collection_field(self) -> None:
        # A list field would let a caller mutate an "immutable" record in place,
        # which is precisely the guarantee raw capture depends on.
        for contract in ALL_CONTRACTS:
            for field in dataclasses.fields(contract):
                annotation = str(field.type)
                assert "list[" not in annotation, f"{contract.__name__}.{field.name}"
                assert "dict[" not in annotation, f"{contract.__name__}.{field.name}"
                assert "set[" not in annotation, f"{contract.__name__}.{field.name}"


class TestTimestampRepresentation:
    """Wall-clock uses ISO-8601 UTC 'Z'; event timing uses integer nanoseconds."""

    def test_wallclock_fields_reject_non_utc(self) -> None:
        with pytest.raises(PerformanceContractError, match="ISO-8601 UTC"):
            RuntimeHealthV1(
                schema_version=RuntimeHealthV1.SCHEMA_VERSION,
                runtime_id="fake",
                checked_at="2026-07-24T10:00:00+02:00",
                state=RuntimeState.OFF,
                process=SubsystemState.UNKNOWN,
                audio_backend=SubsystemState.UNKNOWN,
                audio_output=SubsystemState.UNKNOWN,
                midi_input=SubsystemState.UNKNOWN,
                synth=SubsystemState.UNKNOWN,
                session=SubsystemState.UNKNOWN,
                capture=SubsystemState.UNKNOWN,
            )

    def test_wallclock_fields_reject_unparseable_values(self) -> None:
        with pytest.raises(PerformanceContractError, match="not a valid ISO-8601"):
            RuntimeHealthV1(
                schema_version=RuntimeHealthV1.SCHEMA_VERSION,
                runtime_id="fake",
                checked_at="not-a-timestampZ",
                state=RuntimeState.OFF,
                process=SubsystemState.UNKNOWN,
                audio_backend=SubsystemState.UNKNOWN,
                audio_output=SubsystemState.UNKNOWN,
                midi_input=SubsystemState.UNKNOWN,
                synth=SubsystemState.UNKNOWN,
                session=SubsystemState.UNKNOWN,
                capture=SubsystemState.UNKNOWN,
            )

    def test_event_timing_fields_are_integer_nanoseconds(self) -> None:
        for field in dataclasses.fields(CapturedMidiEventV1):
            if field.name.endswith("_ns"):
                assert "int" in str(field.type)

    def test_negative_event_time_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="capture_time_ns"):
            make_event(0, time_ns=-1)


class TestIdentifiers:
    def test_blank_identifier_rejected_at_construction(self) -> None:
        with pytest.raises(PerformanceContractError, match="non-blank"):
            CapturedMidiEventV1(
                schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
                event_id="   ",
                sequence_number=0,
                event_type=MidiEventType.NOTE_ON,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=60,
                velocity=90,
            )

    def test_identifier_with_surrounding_whitespace_is_rejected(self) -> None:
        # " take-1 " and "take-1" must not be able to denote the same record.
        with pytest.raises(PerformanceContractError, match="whitespace"):
            CapturedMidiEventV1(
                schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
                event_id=" evt-1 ",
                sequence_number=0,
                event_type=MidiEventType.NOTE_ON,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=60,
                velocity=90,
            )

    def test_wrong_schema_version_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="schema_version"):
            CapturedMidiEventV1(
                schema_version="2.0.0",
                event_id="evt-1",
                sequence_number=0,
                event_type=MidiEventType.NOTE_ON,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=60,
                velocity=90,
            )


class TestPerformanceContractErrorHierarchy:
    def test_performance_errors_are_catchable_as_the_repository_base(self) -> None:
        # One except clause still catches every domain-contract failure in the
        # codebase, while a caller who cares can tell a Performance failure apart.
        with pytest.raises(SpatialMappingError):
            make_event(0, time_ns=-1)
        assert issubclass(PerformanceContractError, SpatialMappingError)


class TestConditionalEventFields:
    def test_note_event_requires_note(self) -> None:
        with pytest.raises(PerformanceContractError, match="requires note"):
            CapturedMidiEventV1(
                schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
                event_id="evt-1",
                sequence_number=0,
                event_type=MidiEventType.NOTE_ON,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=None,
                velocity=90,
            )

    def test_note_event_requires_velocity(self) -> None:
        with pytest.raises(PerformanceContractError, match="requires velocity"):
            CapturedMidiEventV1(
                schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
                event_id="evt-1",
                sequence_number=0,
                event_type=MidiEventType.NOTE_ON,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=60,
                velocity=None,
            )

    def test_non_note_event_must_not_carry_note(self) -> None:
        with pytest.raises(PerformanceContractError, match="must not carry note"):
            CapturedMidiEventV1(
                schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
                event_id="evt-1",
                sequence_number=0,
                event_type=MidiEventType.CONTROL_CHANGE,
                capture_time_ns=0,
                channel=0,
                source_port="p",
                source_device="d",
                note=60,
                velocity=90,
                controller=64,
                controller_value=127,
            )

    def test_controller_event_requires_controller(self) -> None:
        with pytest.raises(PerformanceContractError, match="requires controller"):
            make_event(0, MidiEventType.CONTROL_CHANGE, controller=None, controller_value=1)

    def test_controller_event_requires_controller_value(self) -> None:
        with pytest.raises(PerformanceContractError, match="requires controller_value"):
            make_event(0, MidiEventType.CONTROL_CHANGE, controller=64, controller_value=None)

    def test_non_controller_event_must_not_carry_controller(self) -> None:
        with pytest.raises(PerformanceContractError, match="must not carry controller"):
            make_event(0, MidiEventType.PITCH_BEND, controller=64, pitch_bend=0)

    def test_pitch_bend_event_requires_pitch_bend(self) -> None:
        with pytest.raises(PerformanceContractError, match="requires pitch_bend"):
            make_event(0, MidiEventType.PITCH_BEND, pitch_bend=None)

    def test_non_pitch_bend_event_must_not_carry_pitch_bend(self) -> None:
        with pytest.raises(PerformanceContractError, match="must not carry pitch_bend"):
            make_event(0, MidiEventType.PROGRAM_CHANGE, pitch_bend=100)

    def test_pitch_bend_range_is_enforced(self) -> None:
        with pytest.raises(PerformanceContractError, match="pitch_bend"):
            make_event(0, MidiEventType.PITCH_BEND, pitch_bend=9000)

    def test_valid_controller_and_pitch_bend_events_construct(self) -> None:
        cc = make_event(0, MidiEventType.CONTROL_CHANGE, controller=64, controller_value=127)
        bend = make_event(1, MidiEventType.PITCH_BEND, pitch_bend=-2048)
        assert cc.controller == 64
        assert bend.pitch_bend == -2048


class TestSourceStringIsOptionalAndNeverInvented:
    def test_source_string_defaults_to_unresolved(self) -> None:
        assert make_event(0).source_string is None
        assert capture_mod.SOURCE_STRING_UNRESOLVED is None

    def test_absent_source_string_reports_unresolved(self) -> None:
        assert make_event(0).string_identity_resolved is False

    def test_supplied_source_string_is_preserved(self) -> None:
        assert make_event(0, source_string=3).source_string == 3
        assert make_event(0, source_string=3).string_identity_resolved is True

    def test_source_string_zero_is_a_real_string_not_absence(self) -> None:
        # None means "the source did not tell us"; 0 means string 0.
        assert make_event(0, source_string=0).string_identity_resolved is True

    def test_out_of_range_source_string_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="source_string"):
            make_event(0, source_string=99)


class TestRawPayloadIsBounded:
    def test_payload_within_bound_is_accepted(self) -> None:
        event = dataclasses.replace(make_event(0), raw_payload=(0x90, 0x40, 0x60))
        assert event.raw_payload == (0x90, 0x40, 0x60)

    def test_payload_above_bound_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="at most 64 bytes"):
            dataclasses.replace(make_event(0), raw_payload=tuple(range(65)))

    def test_payload_must_contain_byte_values(self) -> None:
        with pytest.raises(PerformanceContractError, match="byte values"):
            dataclasses.replace(make_event(0), raw_payload=(300,))

    def test_payload_must_be_a_tuple(self) -> None:
        with pytest.raises(PerformanceContractError, match="must be a tuple"):
            dataclasses.replace(make_event(0), raw_payload=[1, 2])  # type: ignore[arg-type]


class TestRuntimeIdentity:
    def test_unresolved_version_cannot_be_supported(self) -> None:
        # Ardour 9.7 exposes no version over OSC (GAP-002), so this is a real state
        # and it must not read as acceptable.
        with pytest.raises(PerformanceContractError, match="version_supported"):
            RuntimeIdentityV1(
                schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
                runtime_id="ardour",
                runtime_kind=RuntimeKind.ARDOUR,
                reported_version=None,
                version_policy=">=9.7,<10",
                version_supported=True,
            )

    def test_unresolved_version_with_unsupported_flag_is_valid(self) -> None:
        identity = RuntimeIdentityV1(
            schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
            runtime_id="ardour",
            runtime_kind=RuntimeKind.ARDOUR,
            reported_version=None,
            version_policy=">=9.7,<10",
            version_supported=False,
        )
        assert identity.reported_version is None


class TestObservationCitesItsCapture:
    def _observation(self, **overrides: Any) -> PerformanceObservationV1:
        base: dict[str, Any] = {
            "schema_version": PerformanceObservationV1.SCHEMA_VERSION,
            "observation_id": "obs-1",
            "capture_id": "capture-1",
            "session_id": "session-001",
            "observed_at": T0,
            "event_count": 2,
            "note_on_count": 1,
            "note_off_count": 1,
            "completion_state": CaptureCompletionState.COMPLETE,
            "runtime_state": RuntimeState.READY,
        }
        base.update(overrides)
        return PerformanceObservationV1(**base)

    def test_observation_requires_a_capture_id(self) -> None:
        # An observation without its source is an assertion without evidence.
        with pytest.raises(PerformanceContractError, match="capture_id"):
            self._observation(capture_id="")

    def test_counts_cannot_exceed_the_event_count(self) -> None:
        with pytest.raises(PerformanceContractError, match="cannot exceed event_count"):
            self._observation(event_count=1, note_on_count=1, note_off_count=1)

    def test_velocity_bounds_must_be_ordered(self) -> None:
        with pytest.raises(PerformanceContractError, match="velocity_max"):
            self._observation(velocity_min=100, velocity_max=10)

    def test_event_times_must_be_ordered(self) -> None:
        with pytest.raises(PerformanceContractError, match="last_event_time_ns"):
            self._observation(first_event_time_ns=100, last_event_time_ns=10)

    def test_channels_observed_must_be_unique(self) -> None:
        with pytest.raises(PerformanceContractError, match="duplicates"):
            self._observation(channels_observed=(0, 0))

    def test_valid_observation_constructs(self) -> None:
        observation = self._observation(unresolved_string_event_count=2)
        assert observation.has_unresolved_string_identity is True
        assert self._observation().has_unresolved_string_identity is False
