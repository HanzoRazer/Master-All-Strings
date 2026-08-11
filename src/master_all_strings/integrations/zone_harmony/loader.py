"""Hash-verified, manifest-first Zone semantic artifact loading."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from master_all_strings.integrations.zone_harmony.models import (
    ZoneId,
    ZoneSemanticBundleV1,
    ZoneSemanticContractError,
    ZoneSemanticEventV1,
    ZoneSemanticProvenanceV1,
    ZoneSemanticRole,
    ZoneTransitionSemanticV1,
    ZoneTransitionType,
)


class ZoneSemanticLoadError(ValueError):
    """A declared external Zone semantic artifact cannot be trusted or loaded."""


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ZoneSemanticLoadError(f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ZoneSemanticLoadError(f"{field} must be a non-empty string")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ZoneSemanticLoadError(f"{field} must be an integer")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ZoneSemanticLoadError(f"{field} must be a boolean")
    return value


def _roles(value: object) -> tuple[ZoneSemanticRole, ...]:
    if not isinstance(value, list):
        raise ZoneSemanticLoadError("semantic_roles must be an array")
    try:
        return tuple(ZoneSemanticRole(_string(role, "semantic role")) for role in value)
    except ValueError as exc:
        raise ZoneSemanticLoadError("unknown Zone semantic role") from exc


def _transition(value: object) -> ZoneTransitionSemanticV1:
    item = _object(value, "transition")
    try:
        return ZoneTransitionSemanticV1(
            from_event_id=_string(item.get("from_event_id"), "from_event_id"),
            to_event_id=_string(item.get("to_event_id"), "to_event_id"),
            interval_semitones=_integer(item.get("interval_semitones"), "interval_semitones"),
            transition_type=ZoneTransitionType(
                _string(item.get("transition_type"), "transition_type")
            ),
            from_zone=ZoneId(_string(item.get("from_zone"), "from_zone")),
            to_zone=ZoneId(_string(item.get("to_zone"), "to_zone")),
            crosses_zone=_boolean(item.get("crosses_zone"), "crosses_zone"),
            semantic_roles=_roles(item.get("semantic_roles")),
        )
    except (ValueError, ZoneSemanticContractError) as exc:
        raise ZoneSemanticLoadError(f"invalid Zone transition: {exc}") from exc


def _event(value: object) -> ZoneSemanticEventV1:
    item = _object(value, "event")
    incoming = item.get("transition_from_previous")
    try:
        return ZoneSemanticEventV1(
            event_id=_string(item.get("event_id"), "event_id"),
            pitch_class=_integer(item.get("pitch_class"), "pitch_class"),
            zone_id=ZoneId(_string(item.get("zone_id"), "zone_id")),
            tritone_axis_id=_string(item.get("tritone_axis_id"), "tritone_axis_id"),
            semantic_roles=_roles(item.get("semantic_roles")),
            transition_from_previous=None if incoming is None else _transition(incoming),
        )
    except (ValueError, ZoneSemanticContractError) as exc:
        raise ZoneSemanticLoadError(f"invalid Zone event: {exc}") from exc


def _parse_bundle(payload: object) -> ZoneSemanticBundleV1:
    item = _object(payload, "Zone semantic artifact")
    events = item.get("events")
    transitions = item.get("transitions")
    if not isinstance(events, list) or not isinstance(transitions, list):
        raise ZoneSemanticLoadError("events and transitions must be arrays")
    provenance = _object(item.get("provenance"), "provenance")
    authority = _object(provenance.get("authority"), "provenance.authority")
    try:
        return ZoneSemanticBundleV1(
            artifact_type=_string(item.get("artifact_type"), "artifact_type"),
            schema_version=_string(item.get("schema_version"), "schema_version"),
            theory_name=_string(item.get("theory_name"), "theory_name"),
            theory_version=_string(item.get("theory_version"), "theory_version"),
            source_id=_string(item.get("source_id"), "source_id"),
            events=tuple(_event(event) for event in events),
            transitions=tuple(_transition(transition) for transition in transitions),
            provenance=ZoneSemanticProvenanceV1(
                producer=_string(provenance.get("producer"), "provenance.producer"),
                source_bundle_id=_string(
                    provenance.get("source_bundle_id"), "provenance.source_bundle_id"
                ),
                generation_id=(
                    None
                    if provenance.get("generation_id") is None
                    else _string(provenance.get("generation_id"), "provenance.generation_id")
                ),
                string_master_commit=_string(
                    provenance.get("string_master_commit"),
                    "provenance.string_master_commit",
                ),
                authority=tuple(
                    sorted(
                        (_string(key, "authority key"), _string(value, "authority value"))
                        for key, value in authority.items()
                    )
                ),
            ),
        )
    except ZoneSemanticContractError as exc:
        raise ZoneSemanticLoadError(str(exc)) from exc


def _manifest_entry(manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    extensions = manifest.get("extensions")
    if isinstance(extensions, dict) and "zone_semantics" in extensions:
        return _object(extensions["zone_semantics"], "extensions.zone_semantics")
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("artifact_id") == "zone_semantics_json":
                return cast(Mapping[str, Any], artifact)
    if isinstance(artifacts, dict):
        for artifact in artifacts.values():
            if isinstance(artifact, dict) and artifact.get("artifact_type") == "zone_semantics":
                return cast(Mapping[str, Any], artifact)
    return None


def load_zone_semantics_from_bundle(bundle_dir: Path) -> ZoneSemanticBundleV1 | None:
    """Load optional semantics declared by the bundle manifest; never scan by filename."""

    root = bundle_dir.resolve()
    manifest_path = root / "clip.bundle.json"
    if not manifest_path.is_file():
        raise ZoneSemanticLoadError("bundle manifest is missing")
    try:
        manifest = _object(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    except (OSError, json.JSONDecodeError) as exc:
        raise ZoneSemanticLoadError("bundle manifest is unreadable") from exc
    entry = _manifest_entry(manifest)
    if entry is None:
        return None

    if entry.get("artifact_type", "zone_semantics") != "zone_semantics":
        raise ZoneSemanticLoadError("manifest declares an unsupported semantic artifact type")
    if entry.get("schema_version", "1.0") != "1.0":
        raise ZoneSemanticLoadError("manifest declares an unsupported semantic schema version")
    if entry.get("content_type", "application/json") != "application/json":
        raise ZoneSemanticLoadError("Zone semantic artifact must be JSON")
    relative_path = Path(_string(entry.get("path"), "Zone semantic artifact path"))
    artifact_path = (root / relative_path).resolve()
    try:
        artifact_path.relative_to(root)
    except ValueError as exc:
        raise ZoneSemanticLoadError("Zone semantic artifact escapes the bundle") from exc
    expected_hash = _string(entry.get("sha256"), "Zone semantic artifact sha256")
    try:
        payload = artifact_path.read_bytes()
    except OSError as exc:
        raise ZoneSemanticLoadError("Zone semantic artifact is missing") from exc
    actual_hash = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if actual_hash != expected_hash:
        raise ZoneSemanticLoadError("Zone semantic artifact sha256 mismatch")
    try:
        return _parse_bundle(json.loads(payload))
    except json.JSONDecodeError as exc:
        raise ZoneSemanticLoadError("Zone semantic artifact is not valid JSON") from exc


__all__ = ["ZoneSemanticLoadError", "load_zone_semantics_from_bundle"]
