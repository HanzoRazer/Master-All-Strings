"""Schema and Python-contract conformance (DO-006 §8.6 and rulings §5).

Two authorities describe the same records — frozen dataclasses and hand-written JSON
Schema — so the real risk is that they drift apart. These tests hold them together:
every valid fixture must pass both, every invalid fixture must fail its *named*
validator, and the enums, required fields, and bounds must match on both sides.

The invalid-fixture manifest records which validator rejects each case, because the
honest answer is not "the schema catches everything". Strictly increasing sequence
numbers across an array is not expressible in JSON Schema and is Python-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from helpers import EXAMPLE_DIR, SCHEMA_DIR, load_json

from master_all_strings.performance.configuration import parse_runtime_config
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    MidiEventType,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeKind,
    RuntimeState,
    SubsystemState,
)
from master_all_strings.performance.export import (
    deserialize_raw_capture,
    deserialize_runtime_health,
    serialize_raw_capture,
    serialize_runtime_health,
    to_dict,
)

CAPTURE_DIR = EXAMPLE_DIR / "captures"
HEALTH_DIR = EXAMPLE_DIR / "health"
SESSION_DIR = EXAMPLE_DIR / "sessions"
INVALID_DIR = EXAMPLE_DIR / "invalid"

SCHEMAS = {
    "captured_midi_event_v1",
    "performance_runtime_config_v1",
    "performance_session_config_v1",
    "raw_performance_capture_v1",
    "runtime_capability_registry_v1",
    "runtime_health_v1",
    "synth_registry_v1",
}


def load_schema(name: str) -> dict[str, Any]:
    return dict(load_json(SCHEMA_DIR / f"{name}.schema.json"))


def capture_fixtures() -> list[Path]:
    return sorted(CAPTURE_DIR.glob("*.json"))


def invalid_fixtures() -> list[str]:
    manifest = load_json(INVALID_DIR / "EXPECTED_FAILURES.json")
    return sorted(manifest["fixtures"])


class TestSchemaFilesAreWellFormed:
    @pytest.mark.parametrize("name", sorted(SCHEMAS))
    def test_every_schema_is_valid_json_schema(self, name: str) -> None:
        jsonschema.Draft202012Validator.check_schema(load_schema(name))

    @pytest.mark.parametrize("name", sorted(SCHEMAS))
    def test_every_schema_rejects_undeclared_properties(self, name: str) -> None:
        # Undeclared properties would let a record carry meaning nothing validates.
        assert load_schema(name)["additionalProperties"] is False

    @pytest.mark.parametrize("name", sorted(SCHEMAS))
    def test_every_schema_pins_an_exact_version(self, name: str) -> None:
        properties = load_schema(name)["properties"]
        assert properties["schema_version"]["const"] == "1.0.0"

    def test_schema_directory_holds_exactly_the_expected_files(self) -> None:
        found = {p.name.replace(".schema.json", "") for p in SCHEMA_DIR.glob("*.schema.json")}
        assert found == SCHEMAS


class TestEmbeddedEventDefinitionDoesNotDrift:
    def test_capture_schema_embeds_the_event_schema_verbatim(self) -> None:
        # Duplicated because cross-file $ref resolution is library-version fragile;
        # this test is what makes the duplication safe.
        standalone = load_schema("captured_midi_event_v1")
        embedded = load_schema("raw_performance_capture_v1")["$defs"]["capturedMidiEvent"]
        for key in ("type", "additionalProperties", "required", "properties", "allOf"):
            assert embedded[key] == standalone[key], f"embedded event drifted on {key!r}"


class TestValidFixturesPass:
    @pytest.mark.parametrize("path", capture_fixtures(), ids=lambda p: p.stem)
    def test_capture_fixture_validates(self, path: Path) -> None:
        jsonschema.validate(load_json(path), load_schema("raw_performance_capture_v1"))

    @pytest.mark.parametrize("path", capture_fixtures(), ids=lambda p: p.stem)
    def test_capture_fixture_events_validate_standalone(self, path: Path) -> None:
        schema = load_schema("captured_midi_event_v1")
        for event in load_json(path)["events"]:
            jsonschema.validate(event, schema)

    @pytest.mark.parametrize(
        "path", sorted(HEALTH_DIR.glob("*.json")), ids=lambda p: p.stem
    )
    def test_health_fixture_validates(self, path: Path) -> None:
        jsonschema.validate(load_json(path), load_schema("runtime_health_v1"))

    @pytest.mark.parametrize(
        "path", sorted(SESSION_DIR.glob("*.json")), ids=lambda p: p.stem
    )
    def test_session_fixture_validates(self, path: Path) -> None:
        jsonschema.validate(load_json(path), load_schema("performance_session_config_v1"))

    def test_reference_config_validates(self) -> None:
        jsonschema.validate(
            load_json(EXAMPLE_DIR / "pi_ardour_reference_v1.json"),
            load_schema("performance_runtime_config_v1"),
        )

    def test_synth_registry_validates(self) -> None:
        jsonschema.validate(
            load_json(EXAMPLE_DIR / "synth_registry_v1.json"),
            load_schema("synth_registry_v1"),
        )

    def test_capability_registry_validates(self) -> None:
        jsonschema.validate(
            load_json(EXAMPLE_DIR / "runtime_capability_registry_v1.json"),
            load_schema("runtime_capability_registry_v1"),
        )

    def test_the_fixture_set_covers_every_required_case(self) -> None:
        stems = {p.stem for p in capture_fixtures()}
        for required in (
            "capture_monophonic_complete",
            "capture_per_string_channel",
            "capture_controller_events",
            "capture_pitch_bend",
            "capture_interrupted",
            "capture_runtime_fault",
            "capture_missing_note_off",
        ):
            assert required in stems


class TestInvalidFixturesFailForANamedReason:
    def test_manifest_covers_every_invalid_fixture(self) -> None:
        manifest = load_json(INVALID_DIR / "EXPECTED_FAILURES.json")["fixtures"]
        on_disk = {p.name for p in INVALID_DIR.glob("*.json")} - {"EXPECTED_FAILURES.json"}
        assert set(manifest) == on_disk

    @pytest.mark.parametrize("name", invalid_fixtures())
    def test_every_invalid_fixture_has_a_reason(self, name: str) -> None:
        entry = load_json(INVALID_DIR / "EXPECTED_FAILURES.json")["fixtures"][name]
        assert entry["reason"].strip()
        assert entry["rejected_by"] in ("schema", "python")

    @pytest.mark.parametrize("name", invalid_fixtures())
    def test_every_invalid_fixture_is_rejected_by_its_named_validator(self, name: str) -> None:
        entry = load_json(INVALID_DIR / "EXPECTED_FAILURES.json")["fixtures"][name]
        data = load_json(INVALID_DIR / name)
        schema = load_schema(entry["schema"])

        rejected_by_schema = True
        try:
            jsonschema.validate(data, schema)
            rejected_by_schema = False
        except jsonschema.ValidationError:
            pass

        if entry["rejected_by"] == "schema":
            assert rejected_by_schema, f"{name} should fail schema validation"
        else:
            # Named python: the schema deliberately cannot express this rule, so the
            # contract must be the one that refuses it.
            assert not rejected_by_schema, f"{name} is marked python-only but schema caught it"
            with pytest.raises(PerformanceContractError):
                deserialize_raw_capture(data)

    def test_the_python_only_case_is_the_sequence_rule(self) -> None:
        manifest = load_json(INVALID_DIR / "EXPECTED_FAILURES.json")["fixtures"]
        python_only = {n for n, e in manifest.items() if e["rejected_by"] == "python"}
        assert python_only == {"capture_duplicate_sequence_number.json"}


class TestEnumsMatchBetweenPythonAndSchema:
    def test_event_type_enum_matches(self) -> None:
        schema = load_schema("captured_midi_event_v1")
        assert set(schema["properties"]["event_type"]["enum"]) == {
            m.value for m in MidiEventType
        }

    def test_completion_state_enum_matches(self) -> None:
        schema = load_schema("raw_performance_capture_v1")
        assert set(schema["properties"]["completion_state"]["enum"]) == {
            m.value for m in CaptureCompletionState
        }

    def test_runtime_state_enum_matches(self) -> None:
        schema = load_schema("runtime_health_v1")
        assert set(schema["properties"]["state"]["enum"]) == {m.value for m in RuntimeState}

    def test_subsystem_state_enum_matches(self) -> None:
        schema = load_schema("runtime_health_v1")
        assert set(schema["$defs"]["subsystemState"]["enum"]) == {
            m.value for m in SubsystemState
        }

    def test_fault_code_enum_matches(self) -> None:
        schema = load_schema("runtime_health_v1")
        assert set(schema["$defs"]["fault"]["properties"]["code"]["enum"]) == {
            m.value for m in FaultCode
        }

    def test_runtime_kind_enum_matches(self) -> None:
        schema = load_schema("performance_runtime_config_v1")
        assert set(schema["properties"]["runtime_kind"]["enum"]) == {
            m.value for m in RuntimeKind
        }


class TestRequiredFieldsAndBoundsMatch:
    def test_event_required_fields_match_the_dataclass(self) -> None:
        import dataclasses

        from master_all_strings.performance.contracts.capture import CapturedMidiEventV1

        schema = load_schema("captured_midi_event_v1")
        assert set(schema["required"]) == {f.name for f in dataclasses.fields(CapturedMidiEventV1)}

    def test_capture_required_fields_match_the_dataclass(self) -> None:
        import dataclasses

        from master_all_strings.performance.contracts.capture import RawPerformanceCaptureV1

        schema = load_schema("raw_performance_capture_v1")
        assert set(schema["required"]) == {
            f.name for f in dataclasses.fields(RawPerformanceCaptureV1)
        }

    def test_health_required_fields_match_the_dataclass(self) -> None:
        import dataclasses

        from master_all_strings.performance.contracts.runtime import RuntimeHealthV1

        schema = load_schema("runtime_health_v1")
        assert set(schema["required"]) == {f.name for f in dataclasses.fields(RuntimeHealthV1)}

    def test_note_and_velocity_bounds_match(self) -> None:
        properties = load_schema("captured_midi_event_v1")["properties"]
        assert properties["note"]["maximum"] == 127
        assert properties["velocity"]["maximum"] == 127
        assert properties["channel"]["maximum"] == 15

    def test_pitch_bend_bounds_match(self) -> None:
        from master_all_strings.performance.contracts.capture import (
            MAX_PITCH_BEND,
            MIN_PITCH_BEND,
        )

        properties = load_schema("captured_midi_event_v1")["properties"]
        assert properties["pitch_bend"]["minimum"] == MIN_PITCH_BEND
        assert properties["pitch_bend"]["maximum"] == MAX_PITCH_BEND

    def test_raw_payload_bound_matches(self) -> None:
        from master_all_strings.performance.contracts.errors import MAX_RAW_PAYLOAD_BYTES

        properties = load_schema("captured_midi_event_v1")["properties"]
        assert properties["raw_payload"]["maxItems"] == MAX_RAW_PAYLOAD_BYTES

    def test_sample_rate_and_buffer_options_match(self) -> None:
        from master_all_strings.performance.contracts.runtime import (
            SUPPORTED_BUFFER_FRAMES,
            SUPPORTED_SAMPLE_RATES,
        )

        properties = load_schema("performance_runtime_config_v1")["properties"]
        assert tuple(properties["sample_rate_hz"]["enum"]) == SUPPORTED_SAMPLE_RATES
        assert tuple(properties["buffer_frames"]["enum"]) == SUPPORTED_BUFFER_FRAMES

    def test_first_target_track_bound_matches(self) -> None:
        from master_all_strings.performance.contracts.session import MAX_TRACKS_FIRST_TARGET

        schema = load_schema("performance_session_config_v1")
        assert schema["properties"]["tracks"]["maxItems"] == MAX_TRACKS_FIRST_TARGET

    def test_optional_fields_are_nullable_on_both_sides(self) -> None:
        properties = load_schema("captured_midi_event_v1")["properties"]
        for name in ("note", "velocity", "controller", "controller_value", "pitch_bend"):
            assert "null" in properties[name]["type"], name
        assert "null" in properties["source_string"]["type"]


class TestRoundTrip:
    @pytest.mark.parametrize("path", capture_fixtures(), ids=lambda p: p.stem)
    def test_fixture_reconstructs_an_equivalent_contract(self, path: Path) -> None:
        data = load_json(path)
        capture = deserialize_raw_capture(data)
        assert capture.capture_id == data["capture_id"]
        assert capture.event_count == len(data["events"])

    @pytest.mark.parametrize("path", capture_fixtures(), ids=lambda p: p.stem)
    def test_contract_reserializes_to_schema_valid_json(self, path: Path) -> None:
        capture = deserialize_raw_capture(load_json(path))
        reserialized = json.loads(serialize_raw_capture(capture))
        jsonschema.validate(reserialized, load_schema("raw_performance_capture_v1"))

    @pytest.mark.parametrize("path", capture_fixtures(), ids=lambda p: p.stem)
    def test_round_trip_is_lossless(self, path: Path) -> None:
        original = load_json(path)
        round_tripped = json.loads(serialize_raw_capture(deserialize_raw_capture(original)))
        assert round_tripped == original

    @pytest.mark.parametrize(
        "path", sorted(HEALTH_DIR.glob("*.json")), ids=lambda p: p.stem
    )
    def test_health_round_trip_is_lossless(self, path: Path) -> None:
        original = load_json(path)
        round_tripped = json.loads(serialize_runtime_health(deserialize_runtime_health(original)))
        assert round_tripped == original

    def test_config_round_trip_preserves_every_field(self) -> None:
        original = load_json(EXAMPLE_DIR / "pi_ardour_reference_v1.json")
        config = parse_runtime_config(dict(original))
        encoded = to_dict(config)
        assert encoded["metadata"] == original["metadata"]
        assert encoded["midi_inputs"] == original["midi_inputs"]

    def test_serialization_is_deterministic(self) -> None:
        path = CAPTURE_DIR / "capture_monophonic_complete.json"
        capture = deserialize_raw_capture(load_json(path))
        assert serialize_raw_capture(capture) == serialize_raw_capture(capture)
