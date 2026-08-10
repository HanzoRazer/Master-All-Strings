"""Deterministic JSON serialization for LessonAssignmentV1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .errors import LessonSchemaError, LessonValidationError
from .models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LESSON_ASSIGNMENT_SCHEMA_VERSION,
    LessonAssessmentV1,
    LessonAssignmentV1,
    LessonIdentityV1,
    LessonInstructionV1,
    LessonMusicalContentV1,
    LessonPlaybackPolicyV1,
    LessonProvenanceV1,
    LessonRoutingV1,
    LessonSpatialGuidanceV1,
    SerializedCanonicalEventV1,
    SerializedMeterChangeV1,
    SerializedTempoChangeV1,
    TeacherOverrideV1,
)

__all__ = [
    "compute_assignment_artifact_digest",
    "compute_lesson_behavior_digest",
    "deserialize_lesson_assignment",
    "serialize_lesson_assignment",
    "to_behavior_dict",
    "to_dict",
]

_TOP_LEVEL_REQUIRED = (
    "schema_id",
    "schema_version",
    "identity",
    "musical_content",
    "playback",
    "spatial_guidance",
    "teacher_overrides",
    "instruction",
    "assessment",
    "provenance",
)
_TOP_LEVEL_OPTIONAL = ("routing",)

_IDENTITY_REQUIRED = ("assignment_id", "content_id", "title")
_IDENTITY_OPTIONAL = ("description",)

_CONTENT_REQUIRED = (
    "format",
    "ticks_per_quarter",
    "events",
    "tempo_changes",
    "meter_changes",
)

_EVENT_REQUIRED = (
    "event_id",
    "midi_note",
    "start_tick",
    "duration_ticks",
    "velocity",
    "cents_offset",
    "voice_id",
)

_TEMPO_REQUIRED = ("tick", "tempo_bpm")
_METER_REQUIRED = ("tick", "numerator", "denominator")

_PLAYBACK_REQUIRED = (
    "tempo_override",
    "start_tick",
    "end_tick",
    "loop_enabled",
    "count_in_bars",
)

_SPATIAL_REQUIRED = (
    "instrument_profile_id",
    "fingering_policy_id",
    "preferred_fret_min",
    "preferred_fret_max",
    "open_string_preference",
)

_OVERRIDE_REQUIRED = (
    "event_id",
    "string_id",
    "physical_fret_number",
    "reason",
    "teacher_note",
)

_INSTRUCTION_REQUIRED = (
    "objective",
    "repetitions",
    "difficulty",
    "curriculum_ref",
    "teacher_note",
)

_ASSESSMENT_REQUIRED = (
    "enabled",
    "mode",
    "note_accuracy_required",
    "timing_tolerance_ms",
    "required_successful_repetitions",
)

_PROVENANCE_REQUIRED = ("created_by", "created_at_utc", "source_type", "source_name")

_ROUTING_REQUIRED = ("sender_device_id", "recipient_device_id", "classroom_id")


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def to_dict(assignment: LessonAssignmentV1) -> dict[str, Any]:
    """Encode an assignment into a JSON-ready dict (dataclass field order)."""

    if not isinstance(assignment, LessonAssignmentV1):
        raise LessonValidationError("expected LessonAssignmentV1", code="invalid_assignment")
    encoded = _encode(assignment)
    if not isinstance(encoded, dict):
        raise LessonValidationError("assignment encoding failed", code="invalid_assignment")
    return encoded


def serialize_lesson_assignment(assignment: LessonAssignmentV1) -> str:
    """Serialize to deterministic UTF-8 JSON text."""

    return json.dumps(to_dict(assignment), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def to_behavior_dict(assignment: LessonAssignmentV1) -> dict[str, Any]:
    """Subset of the assignment that defines musical/instructional behavior.

    Excludes routing and non-behavioral provenance fields (created_at / created_by).
    """

    data = to_dict(assignment)
    data.pop("routing", None)
    provenance = dict(data.get("provenance") or {})
    provenance.pop("created_at_utc", None)
    provenance.pop("created_by", None)
    data["provenance"] = provenance
    return data


def compute_lesson_behavior_digest(assignment: LessonAssignmentV1) -> str:
    """Digest of musically/instructionally behavioral fields (routing excluded)."""

    payload = json.dumps(
        to_behavior_dict(assignment),
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compute_assignment_artifact_digest(assignment: LessonAssignmentV1) -> str:
    """Full serialized artifact identity, distinct from the behavior digest."""

    payload = serialize_lesson_assignment(assignment).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LessonValidationError(f"{label} must be an object", code="malformed_assignment")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise LessonValidationError(f"{label} must be an array", code="malformed_assignment")
    return value


def _require_keys(
    data: dict[str, Any],
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    label: str,
) -> None:
    """Enforce schema-equivalent required/allowed key sets (additionalProperties: false)."""

    missing = [key for key in required if key not in data]
    if missing:
        raise LessonValidationError(
            f"{label} is missing required keys: {missing}",
            code="malformed_assignment",
        )
    allowed = set(required) | set(optional)
    extra = sorted(key for key in data if key not in allowed)
    if extra:
        raise LessonValidationError(
            f"{label} has unexpected keys: {extra}",
            code="unexpected_properties",
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LessonValidationError("expected string or null", code="malformed_assignment")
    return value


def _mapping_items(items: list[Any], label: str) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        mapped.append(_require_mapping(item, f"{label}[{index}]"))
    return mapped


def deserialize_lesson_assignment(text: str | bytes | dict[str, Any]) -> LessonAssignmentV1:
    """Deserialize JSON into LessonAssignmentV1; reject unsupported schemas.

    Enforces the same closed object shape as the JSON Schema
    (``additionalProperties: false``) and does not coerce booleans or numeric
    types — raw values are passed to frozen validators.
    """

    if isinstance(text, dict):
        data = text
    else:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LessonValidationError(
                f"malformed JSON: {exc.msg}",
                code="malformed_assignment",
            ) from exc
        data = _require_mapping(loaded, "assignment")

    # Fail closed on unknown schema versions before interpreting other fields.
    if "schema_id" in data and data["schema_id"] != LESSON_ASSIGNMENT_SCHEMA_ID:
        raise LessonSchemaError(
            f"unsupported schema_id: {data['schema_id']!r}",
            code="unsupported_schema",
        )
    if "schema_version" in data and data["schema_version"] != LESSON_ASSIGNMENT_SCHEMA_VERSION:
        raise LessonSchemaError(
            f"unsupported schema_version: {data['schema_version']!r}",
            code="unsupported_schema",
        )

    _require_keys(
        data,
        required=_TOP_LEVEL_REQUIRED,
        optional=_TOP_LEVEL_OPTIONAL,
        label="assignment",
    )

    schema_id = data["schema_id"]
    schema_version = data["schema_version"]

    identity_data = _require_mapping(data["identity"], "identity")
    _require_keys(
        identity_data,
        required=_IDENTITY_REQUIRED,
        optional=_IDENTITY_OPTIONAL,
        label="identity",
    )

    content_data = _require_mapping(data["musical_content"], "musical_content")
    _require_keys(content_data, required=_CONTENT_REQUIRED, label="musical_content")

    playback_data = _require_mapping(data["playback"], "playback")
    _require_keys(playback_data, required=_PLAYBACK_REQUIRED, label="playback")

    spatial_data = _require_mapping(data["spatial_guidance"], "spatial_guidance")
    _require_keys(spatial_data, required=_SPATIAL_REQUIRED, label="spatial_guidance")

    provenance_data = _require_mapping(data["provenance"], "provenance")
    _require_keys(provenance_data, required=_PROVENANCE_REQUIRED, label="provenance")

    instruction_data = _require_mapping(data["instruction"], "instruction")
    _require_keys(instruction_data, required=_INSTRUCTION_REQUIRED, label="instruction")

    assessment_data = _require_mapping(data["assessment"], "assessment")
    _require_keys(assessment_data, required=_ASSESSMENT_REQUIRED, label="assessment")

    event_items = _mapping_items(_require_list(content_data["events"], "events"), "events")
    parsed_events: list[SerializedCanonicalEventV1] = []
    for item_data in event_items:
        _require_keys(item_data, required=_EVENT_REQUIRED, label="event")
        parsed_events.append(
            SerializedCanonicalEventV1(
                event_id=item_data["event_id"],
                midi_note=item_data["midi_note"],
                start_tick=item_data["start_tick"],
                duration_ticks=item_data["duration_ticks"],
                velocity=item_data["velocity"],
                cents_offset=item_data["cents_offset"],
                voice_id=item_data["voice_id"],
            )
        )
    events = tuple(parsed_events)

    tempo_items = _mapping_items(
        _require_list(content_data["tempo_changes"], "tempo_changes"),
        "tempo_changes",
    )
    tempo_changes: list[SerializedTempoChangeV1] = []
    for item_data in tempo_items:
        _require_keys(item_data, required=_TEMPO_REQUIRED, label="tempo_change")
        tempo_changes.append(
            SerializedTempoChangeV1(
                tick=item_data["tick"],
                tempo_bpm=item_data["tempo_bpm"],
            )
        )

    meter_items = _mapping_items(
        _require_list(content_data["meter_changes"], "meter_changes"),
        "meter_changes",
    )
    meter_changes: list[SerializedMeterChangeV1] = []
    for item_data in meter_items:
        _require_keys(item_data, required=_METER_REQUIRED, label="meter_change")
        meter_changes.append(
            SerializedMeterChangeV1(
                tick=item_data["tick"],
                numerator=item_data["numerator"],
                denominator=item_data["denominator"],
            )
        )

    override_items = _mapping_items(
        _require_list(data["teacher_overrides"], "teacher_overrides"),
        "teacher_overrides",
    )
    teacher_overrides: list[TeacherOverrideV1] = []
    for item_data in override_items:
        _require_keys(item_data, required=_OVERRIDE_REQUIRED, label="teacher_override")
        teacher_overrides.append(
            TeacherOverrideV1(
                event_id=item_data["event_id"],
                string_id=item_data["string_id"],
                physical_fret_number=item_data["physical_fret_number"],
                reason=item_data["reason"],
                teacher_note=item_data["teacher_note"],
            )
        )

    routing_raw = data.get("routing")
    routing: LessonRoutingV1 | None
    if routing_raw is None:
        routing = None
    else:
        routing_data = _require_mapping(routing_raw, "routing")
        _require_keys(routing_data, required=_ROUTING_REQUIRED, label="routing")
        routing = LessonRoutingV1(
            sender_device_id=_optional_str(routing_data["sender_device_id"]),
            recipient_device_id=_optional_str(routing_data["recipient_device_id"]),
            classroom_id=_optional_str(routing_data["classroom_id"]),
        )

    return LessonAssignmentV1(
        schema_id=schema_id,
        schema_version=schema_version,
        identity=LessonIdentityV1(
            assignment_id=identity_data["assignment_id"],
            content_id=identity_data["content_id"],
            title=identity_data["title"],
            description=identity_data.get("description"),
        ),
        musical_content=LessonMusicalContentV1(
            format=content_data["format"],
            ticks_per_quarter=content_data["ticks_per_quarter"],
            events=events,
            tempo_changes=tuple(tempo_changes),
            meter_changes=tuple(meter_changes),
        ),
        playback=LessonPlaybackPolicyV1(
            tempo_override=playback_data["tempo_override"],
            start_tick=playback_data["start_tick"],
            end_tick=playback_data["end_tick"],
            loop_enabled=playback_data["loop_enabled"],
            count_in_bars=playback_data["count_in_bars"],
        ),
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id=spatial_data["instrument_profile_id"],
            fingering_policy_id=spatial_data["fingering_policy_id"],
            preferred_fret_min=spatial_data["preferred_fret_min"],
            preferred_fret_max=spatial_data["preferred_fret_max"],
            open_string_preference=spatial_data["open_string_preference"],
        ),
        teacher_overrides=tuple(teacher_overrides),
        instruction=LessonInstructionV1(
            objective=instruction_data["objective"],
            repetitions=instruction_data["repetitions"],
            difficulty=instruction_data["difficulty"],
            curriculum_ref=instruction_data["curriculum_ref"],
            teacher_note=instruction_data["teacher_note"],
        ),
        assessment=LessonAssessmentV1(
            enabled=assessment_data["enabled"],
            mode=assessment_data["mode"],
            note_accuracy_required=assessment_data["note_accuracy_required"],
            timing_tolerance_ms=assessment_data["timing_tolerance_ms"],
            required_successful_repetitions=assessment_data[
                "required_successful_repetitions"
            ],
        ),
        provenance=LessonProvenanceV1(
            created_by=provenance_data["created_by"],
            created_at_utc=provenance_data["created_at_utc"],
            source_type=provenance_data["source_type"],
            source_name=provenance_data["source_name"],
        ),
        routing=routing,
    )
