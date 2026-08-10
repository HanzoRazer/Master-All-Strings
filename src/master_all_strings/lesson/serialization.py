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


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LessonValidationError("expected string or null", code="malformed_assignment")
    return value


def deserialize_lesson_assignment(text: str | bytes | dict[str, Any]) -> LessonAssignmentV1:
    """Deserialize JSON into LessonAssignmentV1; reject unsupported schemas."""

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

    schema_id = data.get("schema_id")
    schema_version = data.get("schema_version")
    if schema_id != LESSON_ASSIGNMENT_SCHEMA_ID:
        raise LessonSchemaError(
            f"unsupported schema_id: {schema_id!r}",
            code="unsupported_schema",
        )
    if schema_version != LESSON_ASSIGNMENT_SCHEMA_VERSION:
        raise LessonSchemaError(
            f"unsupported schema_version: {schema_version!r}",
            code="unsupported_schema",
        )

    try:
        identity_data = _require_mapping(data["identity"], "identity")
        content_data = _require_mapping(data["musical_content"], "musical_content")
        playback_data = _require_mapping(data["playback"], "playback")
        spatial_data = _require_mapping(data["spatial_guidance"], "spatial_guidance")
        provenance_data = _require_mapping(data["provenance"], "provenance")
        instruction_data = _require_mapping(data.get("instruction") or {}, "instruction")
        assessment_data = _require_mapping(data.get("assessment") or {}, "assessment")
    except KeyError as exc:
        raise LessonValidationError(
            f"missing required field: {exc.args[0]}",
            code="missing_content",
        ) from exc

    events = tuple(
        SerializedCanonicalEventV1(
            event_id=item["event_id"],
            midi_note=item["midi_note"],
            start_tick=item["start_tick"],
            duration_ticks=item["duration_ticks"],
            velocity=item.get("velocity", 64),
            cents_offset=float(item.get("cents_offset", 0.0)),
            voice_id=item.get("voice_id"),
        )
        for item in content_data.get("events", ())
    )
    tempo_changes = tuple(
        SerializedTempoChangeV1(tick=item["tick"], tempo_bpm=float(item["tempo_bpm"]))
        for item in content_data.get("tempo_changes", ())
    )
    meter_changes = tuple(
        SerializedMeterChangeV1(
            tick=item["tick"],
            numerator=item["numerator"],
            denominator=item["denominator"],
        )
        for item in content_data.get("meter_changes", ())
    )

    overrides_raw = data.get("teacher_overrides") or ()
    teacher_overrides = tuple(
        TeacherOverrideV1(
            event_id=item["event_id"],
            string_id=item["string_id"],
            physical_fret_number=item["physical_fret_number"],
            reason=item.get("reason"),
            teacher_note=item.get("teacher_note"),
        )
        for item in overrides_raw
    )

    routing_raw = data.get("routing")
    routing: LessonRoutingV1 | None
    if routing_raw is None:
        routing = None
    else:
        routing_data = _require_mapping(routing_raw, "routing")
        routing = LessonRoutingV1(
            sender_device_id=_optional_str(routing_data.get("sender_device_id")),
            recipient_device_id=_optional_str(routing_data.get("recipient_device_id")),
            classroom_id=_optional_str(routing_data.get("classroom_id")),
        )

    return LessonAssignmentV1(
        schema_id=str(schema_id),
        schema_version=str(schema_version),
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
            tempo_changes=tempo_changes,
            meter_changes=meter_changes,
        ),
        playback=LessonPlaybackPolicyV1(
            tempo_override=playback_data.get("tempo_override"),
            start_tick=playback_data.get("start_tick"),
            end_tick=playback_data.get("end_tick"),
            loop_enabled=bool(playback_data.get("loop_enabled", False)),
            count_in_bars=playback_data.get("count_in_bars"),
        ),
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id=spatial_data["instrument_profile_id"],
            fingering_policy_id=spatial_data["fingering_policy_id"],
            preferred_fret_min=spatial_data.get("preferred_fret_min"),
            preferred_fret_max=spatial_data.get("preferred_fret_max"),
            open_string_preference=spatial_data.get("open_string_preference", "allow"),
        ),
        teacher_overrides=teacher_overrides,
        instruction=LessonInstructionV1(
            objective=instruction_data.get("objective"),
            repetitions=instruction_data.get("repetitions"),
            difficulty=instruction_data.get("difficulty"),
            curriculum_ref=instruction_data.get("curriculum_ref"),
            teacher_note=instruction_data.get("teacher_note"),
        ),
        assessment=LessonAssessmentV1(
            enabled=bool(assessment_data.get("enabled", False)),
            mode=assessment_data.get("mode", "disabled"),
            note_accuracy_required=assessment_data.get("note_accuracy_required"),
            timing_tolerance_ms=assessment_data.get("timing_tolerance_ms"),
            required_successful_repetitions=assessment_data.get(
                "required_successful_repetitions"
            ),
        ),
        provenance=LessonProvenanceV1(
            created_by=provenance_data["created_by"],
            created_at_utc=provenance_data["created_at_utc"],
            source_type=provenance_data["source_type"],
            source_name=provenance_data.get("source_name"),
        ),
        routing=routing,
    )
