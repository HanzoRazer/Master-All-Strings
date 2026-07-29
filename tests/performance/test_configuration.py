"""Configuration loading and validation (DO-006 §8.2).

Valid configurations must load; invalid ones must fail for a nameable reason. Rules
that need more than one document -- an unknown synth, a duplicate runtime id -- live
in the validator rather than in JSON Schema, because a schema validates one file and
cannot see another.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from helpers import load_json

from master_all_strings.performance.configuration import (
    EXAMPLE_DIR,
    RuntimeProfile,
    load_runtime_config,
    load_synth_registry,
    parse_runtime_config,
    parse_synth_registry,
    resolve_runtime_profile,
    validate_runtime_config,
    validate_runtime_configs,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import RuntimeKind

CONFIG_PATH = EXAMPLE_DIR / "pi_ardour_reference_v1.json"


@pytest.fixture
def raw_config() -> dict[str, Any]:
    return copy.deepcopy(load_json(CONFIG_PATH))


def _deployable(raw: dict[str, Any]) -> dict[str, Any]:
    """Replace the reference placeholders so the config models a real device."""
    raw = copy.deepcopy(raw)
    raw["executable"] = "/usr/bin/ardour9"
    raw["session_template"] = "/opt/mas/templates/single-midi-track"
    raw["audio_output"] = "hw:0,0"
    raw["midi_inputs"] = ["hw:1,0,0"]
    raw["synth_id"] = "reasonablesynth"
    return raw


class TestValidConfigurations:
    def test_reference_config_loads(self) -> None:
        config = load_runtime_config(CONFIG_PATH)
        assert config.runtime_kind is RuntimeKind.ARDOUR
        assert config.runtime_version_policy == ">=9.7,<10"

    def test_reference_config_declares_offline_operation(self) -> None:
        config = load_runtime_config(CONFIG_PATH)
        assert config.offline_required is True
        assert config.requires_network is False

    def test_reference_config_reports_placeholders_as_findings(self) -> None:
        # A committed reference is a template, not a deployable configuration.
        config = load_runtime_config(CONFIG_PATH)
        problems = validate_runtime_config(config, load_synth_registry())
        assert any("placeholder" in p for p in problems)

    def test_deployable_config_has_no_findings(self, raw_config: dict[str, Any]) -> None:
        config = parse_runtime_config(_deployable(raw_config))
        assert validate_runtime_config(config, load_synth_registry()) == []

    @pytest.mark.parametrize("rate", [44100, 48000, 88200, 96000])
    def test_supported_sample_rates_are_accepted(
        self, raw_config: dict[str, Any], rate: int
    ) -> None:
        raw = _deployable(raw_config)
        raw["sample_rate_hz"] = rate
        assert parse_runtime_config(raw).sample_rate_hz == rate

    @pytest.mark.parametrize("frames", [16, 64, 256, 2048])
    def test_supported_buffer_sizes_are_accepted(
        self, raw_config: dict[str, Any], frames: int
    ) -> None:
        raw = _deployable(raw_config)
        raw["buffer_frames"] = frames
        assert parse_runtime_config(raw).buffer_frames == frames


class TestInvalidConfigurations:
    def test_zero_buffer_size_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["buffer_frames"] = 0
        with pytest.raises(PerformanceContractError, match="buffer_frames"):
            parse_runtime_config(raw_config)

    def test_negative_timeout_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["startup_timeout_ms"] = -1
        with pytest.raises(PerformanceContractError, match="startup_timeout_ms"):
            parse_runtime_config(raw_config)

    def test_zero_timeout_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["health_timeout_ms"] = 0
        with pytest.raises(PerformanceContractError, match="health_timeout_ms"):
            parse_runtime_config(raw_config)

    def test_missing_midi_source_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["midi_inputs"] = []
        with pytest.raises(PerformanceContractError, match="at least one source"):
            parse_runtime_config(raw_config)

    def test_duplicate_midi_sources_are_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["midi_inputs"] = ["a", "a"]
        with pytest.raises(PerformanceContractError, match="duplicates"):
            parse_runtime_config(raw_config)

    def test_unknown_runtime_kind_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["runtime_kind"] = "cubase"
        with pytest.raises(PerformanceContractError, match="unknown runtime_kind"):
            parse_runtime_config(raw_config)

    def test_blank_session_template_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["session_template"] = ""
        with pytest.raises(PerformanceContractError, match="session_template"):
            parse_runtime_config(raw_config)

    def test_unsupported_sample_rate_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["sample_rate_hz"] = 22050
        with pytest.raises(PerformanceContractError, match="sample_rate_hz"):
            parse_runtime_config(raw_config)

    def test_cloud_dependency_while_offline_required_is_rejected(
        self, raw_config: dict[str, Any]
    ) -> None:
        # A dead instrument on a stage is the failure this prevents.
        raw_config["requires_network"] = True
        with pytest.raises(PerformanceContractError, match="requires_network must be false"):
            parse_runtime_config(raw_config)

    def test_missing_key_is_rejected(self, raw_config: dict[str, Any]) -> None:
        del raw_config["synth_id"]
        with pytest.raises(PerformanceContractError, match="missing keys"):
            parse_runtime_config(raw_config)

    def test_unexpected_key_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["surprise"] = 1
        with pytest.raises(PerformanceContractError, match="unexpected keys"):
            parse_runtime_config(raw_config)

    def test_non_object_metadata_is_rejected(self, raw_config: dict[str, Any]) -> None:
        raw_config["metadata"] = []
        with pytest.raises(PerformanceContractError, match="metadata"):
            parse_runtime_config(raw_config)

    def test_missing_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(PerformanceContractError, match="file not found"):
            load_runtime_config(tmp_path / "absent.json")

    def test_malformed_json_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(PerformanceContractError, match="not valid JSON"):
            load_runtime_config(path)

    def test_non_object_document_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "list.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(PerformanceContractError, match="JSON object"):
            load_runtime_config(path)


class TestCrossFileRules:
    def test_unknown_synth_is_reported(self, raw_config: dict[str, Any]) -> None:
        raw = _deployable(raw_config)
        raw["synth_id"] = "not-a-registered-synth"
        config = parse_runtime_config(raw)
        problems = validate_runtime_config(config, load_synth_registry())
        assert any("not in the registry" in p for p in problems)

    def test_duplicate_runtime_id_is_reported(self, raw_config: dict[str, Any]) -> None:
        config = parse_runtime_config(_deployable(raw_config))
        assert validate_runtime_configs([config]) == []
        problems = validate_runtime_configs([config, config])
        assert any("duplicate runtime_id" in p for p in problems)

    def test_validation_without_a_registry_skips_the_synth_check(
        self, raw_config: dict[str, Any]
    ) -> None:
        raw = _deployable(raw_config)
        raw["synth_id"] = "unknown"
        assert validate_runtime_config(parse_runtime_config(raw)) == []


class TestSynthRegistry:
    def test_registry_loads(self) -> None:
        registry = load_synth_registry()
        assert registry.has("reasonablesynth")
        assert registry.has("a-fluidsynth")

    def test_first_proof_default_needs_no_sound_library(self) -> None:
        # The reason it is the default: no soundfont means no unresolved
        # sound-library licensing question on the acceptance path.
        assert load_synth_registry().get("reasonablesynth").requires_sound_library is False

    def test_secondary_synth_requires_a_sound_library(self) -> None:
        assert load_synth_registry().get("a-fluidsynth").requires_sound_library is True

    def test_unresolved_license_is_not_distributable(self) -> None:
        # Development availability is not redistribution approval.
        assert load_synth_registry().get("reasonablesynth").is_distributable is False

    def test_unknown_synth_id_raises_with_the_known_set(self) -> None:
        with pytest.raises(PerformanceContractError, match="unknown synth_id"):
            load_synth_registry().get("nope")

    def test_distribution_approval_requires_license_approval(self) -> None:
        raw = copy.deepcopy(load_json(EXAMPLE_DIR / "synth_registry_v1.json"))
        raw["synths"][1]["distribution_status"] = "approved"
        with pytest.raises(PerformanceContractError, match="distribution approval"):
            parse_synth_registry(raw)

    def test_duplicate_synth_ids_are_rejected(self) -> None:
        raw = copy.deepcopy(load_json(EXAMPLE_DIR / "synth_registry_v1.json"))
        raw["synths"].append(copy.deepcopy(raw["synths"][0]))
        with pytest.raises(PerformanceContractError, match="unique"):
            parse_synth_registry(raw)

    def test_empty_registry_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="non-empty"):
            parse_synth_registry({"schema_version": "1.0.0", "synths": []})

    def test_non_object_entry_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="must be an object"):
            parse_synth_registry({"schema_version": "1.0.0", "synths": ["x"]})

    def test_wrong_registry_schema_version_is_rejected(self) -> None:
        with pytest.raises(PerformanceContractError, match="schema_version"):
            parse_synth_registry({"schema_version": "9.9.9", "synths": []})


class TestRuntimeProfile:
    def test_profile_resolves_the_configured_synth(self, raw_config: dict[str, Any]) -> None:
        config = parse_runtime_config(_deployable(raw_config))
        profile = resolve_runtime_profile(config, load_synth_registry())
        assert isinstance(profile, RuntimeProfile)
        assert profile.synth.synth_id == "reasonablesynth"

    def test_unregistered_synth_cannot_be_resolved(self, raw_config: dict[str, Any]) -> None:
        # Selection is by registry identifier, so an unregistered synth is
        # unreachable rather than merely discouraged.
        raw = _deployable(raw_config)
        raw["synth_id"] = "arbitrary-plugin.lv2"
        config = parse_runtime_config(raw)
        with pytest.raises(PerformanceContractError, match="unknown synth_id"):
            resolve_runtime_profile(config, load_synth_registry())
