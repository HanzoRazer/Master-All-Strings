"""Loading and validating declarative runtime configuration.

Everything here is read-only. These functions never install a runtime, download a
plugin, change a system audio setting, execute a shell command from configuration,
or scan a directory the caller did not name (ADR-0007 §7 prohibited behavior).

Cross-file rules live here rather than in JSON Schema, because a schema validates one
document and cannot see another: an unknown ``synth_id`` and a duplicate
``runtime_id`` are only visible with the registry in hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
    require_schema_version,
)
from master_all_strings.performance.contracts.runtime import (
    PerformanceRuntimeConfigV1,
    RuntimeKind,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCE_DIR = _REPO_ROOT / "resources" / "performance"
SCHEMA_DIR = RESOURCE_DIR / "schema"
EXAMPLE_DIR = RESOURCE_DIR / "examples"

SYNTH_REGISTRY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class SynthEntry:
    """One approved synthesizer.

    ``license_status`` and ``distribution_status`` are carried into the runtime rather
    than checked once at review time, so a caller can refuse to select a synth that is
    not cleared for the context it is running in (ADR-0007 D17).
    """

    synth_id: str
    display_name: str
    plugin_format: str
    plugin_identifier: str
    version: str | None
    preset: str | None
    license_status: str
    distribution_status: str
    pi_status: str
    measured_cpu: float | None
    measured_memory: int | None
    requires_sound_library: bool
    notes: str

    @property
    def is_distributable(self) -> bool:
        """Whether this synth is cleared for redistribution.

        Development availability is not redistribution approval.
        """
        return self.distribution_status == "approved" and self.license_status == "approved"


@dataclass(frozen=True)
class SynthRegistry:
    """The approved-synthesizer registry."""

    schema_version: str
    synths: tuple[SynthEntry, ...]

    def get(self, synth_id: str) -> SynthEntry:
        """Return the entry for ``synth_id`` or raise."""
        for entry in self.synths:
            if entry.synth_id == synth_id:
                return entry
        known = sorted(e.synth_id for e in self.synths)
        raise PerformanceContractError(f"unknown synth_id {synth_id!r}; registered: {known}")

    def has(self, synth_id: str) -> bool:
        """Whether ``synth_id`` is registered."""
        return any(e.synth_id == synth_id for e in self.synths)


@dataclass(frozen=True)
class RuntimeProfile:
    """A configuration resolved against the registries it depends on."""

    config: PerformanceRuntimeConfigV1
    synth: SynthEntry


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PerformanceContractError(f"file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PerformanceContractError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PerformanceContractError(f"{path.name} must contain a JSON object")
    return data


def load_runtime_config(path: Path) -> PerformanceRuntimeConfigV1:
    """Load and validate a runtime configuration from disk."""
    return parse_runtime_config(_read_json(path))


def parse_runtime_config(data: dict[str, Any]) -> PerformanceRuntimeConfigV1:
    """Build a validated configuration from decoded JSON."""
    expected = {
        "schema_version",
        "runtime_id",
        "runtime_kind",
        "runtime_version_policy",
        "executable",
        "session_template",
        "audio_backend",
        "sample_rate_hz",
        "buffer_frames",
        "audio_output",
        "midi_inputs",
        "synth_id",
        "startup_timeout_ms",
        "health_timeout_ms",
        "shutdown_timeout_ms",
        "offline_required",
        "requires_network",
        "metadata",
    }
    missing = sorted(expected - set(data))
    if missing:
        raise PerformanceContractError(f"runtime config is missing keys: {missing}")
    extra = sorted(set(data) - expected)
    if extra:
        raise PerformanceContractError(f"runtime config has unexpected keys: {extra}")

    kind_value = data["runtime_kind"]
    try:
        kind = RuntimeKind(kind_value)
    except ValueError as exc:
        known = sorted(k.value for k in RuntimeKind)
        raise PerformanceContractError(
            f"unknown runtime_kind {kind_value!r}; known kinds: {known}"
        ) from exc

    metadata = data["metadata"]
    if not isinstance(metadata, dict):
        raise PerformanceContractError("metadata must be an object")

    return PerformanceRuntimeConfigV1(
        schema_version=data["schema_version"],
        runtime_id=data["runtime_id"],
        runtime_kind=kind,
        runtime_version_policy=data["runtime_version_policy"],
        executable=data["executable"],
        session_template=data["session_template"],
        audio_backend=data["audio_backend"],
        sample_rate_hz=data["sample_rate_hz"],
        buffer_frames=data["buffer_frames"],
        audio_output=data["audio_output"],
        midi_inputs=tuple(data["midi_inputs"]),
        synth_id=data["synth_id"],
        startup_timeout_ms=data["startup_timeout_ms"],
        health_timeout_ms=data["health_timeout_ms"],
        shutdown_timeout_ms=data["shutdown_timeout_ms"],
        offline_required=data["offline_required"],
        requires_network=data["requires_network"],
        metadata=tuple(sorted((str(k), str(v)) for k, v in metadata.items())),
    )


def validate_runtime_config(
    config: PerformanceRuntimeConfigV1, registry: SynthRegistry | None = None
) -> list[str]:
    """Return every cross-field or cross-file problem (empty when clean).

    Returns findings rather than raising: a caller validating several configurations
    wants all the problems at once, not the first one.
    """
    problems: list[str] = []
    if registry is not None and not registry.has(config.synth_id):
        known = sorted(e.synth_id for e in registry.synths)
        problems.append(f"synth_id {config.synth_id!r} is not in the registry; known: {known}")
    if config.offline_required and config.requires_network:
        problems.append("offline_required is true but requires_network is also true")
    # Placeholders are correct in a committed reference file and wrong on a device.
    # Reported as a finding rather than an error so the reference config still loads.
    for name in ("executable", "session_template", "audio_output"):
        value = getattr(config, name)
        if value.startswith("REPLACE_WITH_"):
            problems.append(f"{name} is still a placeholder ({value})")
    for source in config.midi_inputs:
        if source.startswith("REPLACE_WITH_"):
            problems.append(f"midi_inputs contains a placeholder ({source})")
    return problems


def validate_runtime_configs(configs: list[PerformanceRuntimeConfigV1]) -> list[str]:
    """Return problems across a set of configurations, such as a duplicate id."""
    problems: list[str] = []
    seen: set[str] = set()
    for config in configs:
        if config.runtime_id in seen:
            problems.append(f"duplicate runtime_id {config.runtime_id!r}")
        seen.add(config.runtime_id)
    return problems


def load_synth_registry(path: Path | None = None) -> SynthRegistry:
    """Load the approved-synthesizer registry."""
    return parse_synth_registry(_read_json(path or EXAMPLE_DIR / "synth_registry_v1.json"))


def parse_synth_registry(data: dict[str, Any]) -> SynthRegistry:
    """Build a registry from decoded JSON."""
    require_schema_version(data.get("schema_version", ""), SYNTH_REGISTRY_SCHEMA_VERSION)
    raw_synths = data.get("synths")
    if not isinstance(raw_synths, list) or not raw_synths:
        raise PerformanceContractError("synths must be a non-empty array")

    entries: list[SynthEntry] = []
    for raw in raw_synths:
        if not isinstance(raw, dict):
            raise PerformanceContractError("each synth entry must be an object")
        require_identifier(raw.get("synth_id", ""), "synth_id")
        entry = SynthEntry(
            synth_id=raw["synth_id"],
            display_name=raw["display_name"],
            plugin_format=raw["plugin_format"],
            plugin_identifier=raw["plugin_identifier"],
            version=raw["version"],
            preset=raw["preset"],
            license_status=raw["license_status"],
            distribution_status=raw["distribution_status"],
            pi_status=raw["pi_status"],
            measured_cpu=raw["measured_cpu"],
            measured_memory=raw["measured_memory"],
            requires_sound_library=raw["requires_sound_library"],
            notes=raw.get("notes", ""),
        )
        # Mirrors the schema gate, so a registry built in memory cannot claim
        # distribution approval that the file form would have refused.
        if entry.distribution_status == "approved" and entry.license_status != "approved":
            raise PerformanceContractError(
                f"synth {entry.synth_id!r} claims distribution approval "
                "while its license status is unresolved"
            )
        entries.append(entry)

    ids = [e.synth_id for e in entries]
    if len(ids) != len(set(ids)):
        raise PerformanceContractError("synth_id values must be unique")
    return SynthRegistry(schema_version=data["schema_version"], synths=tuple(entries))


def resolve_runtime_profile(
    config: PerformanceRuntimeConfigV1, registry: SynthRegistry
) -> RuntimeProfile:
    """Resolve a configuration against the synth registry.

    Raises if the configured synth is unknown: selection is by registry identifier, so
    an unregistered synth cannot be reached at all (ADR-0007 D17).
    """
    return RuntimeProfile(config=config, synth=registry.get(config.synth_id))
