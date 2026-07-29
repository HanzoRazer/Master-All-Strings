"""Deterministic serialization for Performance Engine records.

Two properties matter more than convenience here:

* **Determinism.** The same record always produces byte-identical JSON. Field order
  follows dataclass declaration order, and mapping fields are key-sorted. A capture
  that serializes differently on two runs cannot be digested, compared, or cited.
* **Round-trip fidelity.** ``deserialize_*`` reconstructs a record equal to the
  original. Optional fields serialize as ``null`` rather than being omitted, so the
  JSON shape is fixed and a missing key is an error rather than a default.

Nothing here writes to disk or opens a network connection; callers decide where bytes
go.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CapturedMidiEventV1,
    CaptureSourceV1,
    MidiEventType,
    PerformanceObservationV1,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeFaultV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeKind,
    RuntimeState,
    SubsystemState,
)
from master_all_strings.performance.contracts.session import MeterV1

# Fields held as tuples of (key, value) pairs in Python but serialized as JSON
# objects, because a mapping is what they are -- the tuple form exists only so the
# containing dataclass can stay frozen and hashable.
_MAPPING_FIELDS = frozenset({"metadata", "provenance"})


def _encode(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name), f.name) for f in fields(value)}
    if isinstance(value, tuple):
        if field_name in _MAPPING_FIELDS:
            return {str(k): str(v) for k, v in sorted(value)}
        return [_encode(item) for item in value]
    return value


def to_dict(record: Any) -> dict[str, Any]:
    """Encode a contract dataclass into a JSON-ready dict."""
    if not is_dataclass(record) or isinstance(record, type):
        raise PerformanceContractError("to_dict requires a contract dataclass instance")
    return {f.name: _encode(getattr(record, f.name), f.name) for f in fields(record)}


def to_json(record: Any) -> str:
    """Encode a contract dataclass into deterministic JSON text."""
    return json.dumps(to_dict(record), indent=2, sort_keys=False) + "\n"


def serialize_raw_capture(capture: RawPerformanceCaptureV1) -> str:
    """Serialize a raw capture."""
    if not isinstance(capture, RawPerformanceCaptureV1):
        raise PerformanceContractError("expected a RawPerformanceCaptureV1")
    return to_json(capture)


def serialize_runtime_health(health: RuntimeHealthV1) -> str:
    """Serialize a runtime health snapshot."""
    if not isinstance(health, RuntimeHealthV1):
        raise PerformanceContractError("expected a RuntimeHealthV1")
    return to_json(health)


def serialize_performance_observation(observation: PerformanceObservationV1) -> str:
    """Serialize a performance observation."""
    if not isinstance(observation, PerformanceObservationV1):
        raise PerformanceContractError("expected a PerformanceObservationV1")
    return to_json(observation)


def capture_digest(capture: RawPerformanceCaptureV1) -> str:
    """A stable content digest of a capture.

    Used as ``raw_capture_digest`` on an ingestion request so Musical Core can verify
    it received the record it was promised, without Performance handing over a
    structure Core might mutate. Deterministic serialization is what makes this
    meaningful.
    """
    payload = serialize_raw_capture(capture).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _require_keys(data: dict[str, Any], expected: tuple[str, ...], label: str) -> None:
    missing = [k for k in expected if k not in data]
    if missing:
        raise PerformanceContractError(f"{label} is missing required keys: {missing}")
    extra = [k for k in data if k not in expected]
    if extra:
        raise PerformanceContractError(f"{label} has unexpected keys: {extra}")


def _mapping_to_pairs(value: Any, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise PerformanceContractError(f"{label} must be an object")
    return tuple(sorted((str(k), str(v)) for k, v in value.items()))


def deserialize_meter(data: dict[str, Any]) -> MeterV1:
    """Reconstruct a ``MeterV1``."""
    _require_keys(data, ("schema_version", "beats_per_bar", "beat_unit"), "meter")
    return MeterV1(
        schema_version=data["schema_version"],
        beats_per_bar=data["beats_per_bar"],
        beat_unit=data["beat_unit"],
    )


def deserialize_fault(data: dict[str, Any]) -> RuntimeFaultV1:
    """Reconstruct a ``RuntimeFaultV1``."""
    _require_keys(
        data,
        (
            "schema_version",
            "fault_id",
            "code",
            "subsystem",
            "detail",
            "occurred_at",
            "recoverable",
        ),
        "fault",
    )
    return RuntimeFaultV1(
        schema_version=data["schema_version"],
        fault_id=data["fault_id"],
        code=FaultCode(data["code"]),
        subsystem=data["subsystem"],
        detail=data["detail"],
        occurred_at=data["occurred_at"],
        recoverable=data["recoverable"],
    )


def deserialize_runtime_identity(data: dict[str, Any]) -> RuntimeIdentityV1:
    """Reconstruct a ``RuntimeIdentityV1``."""
    _require_keys(
        data,
        (
            "schema_version",
            "runtime_id",
            "runtime_kind",
            "reported_version",
            "version_policy",
            "version_supported",
        ),
        "runtime_identity",
    )
    return RuntimeIdentityV1(
        schema_version=data["schema_version"],
        runtime_id=data["runtime_id"],
        runtime_kind=RuntimeKind(data["runtime_kind"]),
        reported_version=data["reported_version"],
        version_policy=data["version_policy"],
        version_supported=data["version_supported"],
    )


def deserialize_capture_source(data: dict[str, Any]) -> CaptureSourceV1:
    """Reconstruct a ``CaptureSourceV1``."""
    _require_keys(
        data,
        ("schema_version", "source_id", "port", "device", "supplies_string_identity"),
        "source_identity",
    )
    return CaptureSourceV1(
        schema_version=data["schema_version"],
        source_id=data["source_id"],
        port=data["port"],
        device=data["device"],
        supplies_string_identity=data["supplies_string_identity"],
    )


def deserialize_midi_event(data: dict[str, Any]) -> CapturedMidiEventV1:
    """Reconstruct a ``CapturedMidiEventV1``."""
    _require_keys(
        data,
        (
            "schema_version",
            "event_id",
            "sequence_number",
            "event_type",
            "capture_time_ns",
            "channel",
            "source_port",
            "source_device",
            "note",
            "velocity",
            "controller",
            "controller_value",
            "pitch_bend",
            "source_string",
            "raw_payload",
        ),
        "event",
    )
    return CapturedMidiEventV1(
        schema_version=data["schema_version"],
        event_id=data["event_id"],
        sequence_number=data["sequence_number"],
        event_type=MidiEventType(data["event_type"]),
        capture_time_ns=data["capture_time_ns"],
        channel=data["channel"],
        source_port=data["source_port"],
        source_device=data["source_device"],
        note=data["note"],
        velocity=data["velocity"],
        controller=data["controller"],
        controller_value=data["controller_value"],
        pitch_bend=data["pitch_bend"],
        source_string=data["source_string"],
        raw_payload=tuple(data["raw_payload"]),
    )


def deserialize_raw_capture(data: dict[str, Any]) -> RawPerformanceCaptureV1:
    """Reconstruct a ``RawPerformanceCaptureV1`` from decoded JSON."""
    _require_keys(
        data,
        (
            "schema_version",
            "capture_id",
            "session_id",
            "runtime_identity",
            "source_identity",
            "started_at",
            "ended_at",
            "completion_state",
            "tempo_context",
            "meter_context",
            "events",
            "warnings",
            "faults",
            "provenance",
        ),
        "capture",
    )
    return RawPerformanceCaptureV1(
        schema_version=data["schema_version"],
        capture_id=data["capture_id"],
        session_id=data["session_id"],
        runtime_identity=deserialize_runtime_identity(data["runtime_identity"]),
        source_identity=deserialize_capture_source(data["source_identity"]),
        started_at=data["started_at"],
        completion_state=CaptureCompletionState(data["completion_state"]),
        tempo_context=data["tempo_context"],
        meter_context=deserialize_meter(data["meter_context"]),
        events=tuple(deserialize_midi_event(e) for e in data["events"]),
        ended_at=data["ended_at"],
        warnings=tuple(data["warnings"]),
        faults=tuple(deserialize_fault(f) for f in data["faults"]),
        provenance=_mapping_to_pairs(data["provenance"], "provenance"),
    )


def deserialize_runtime_health(data: dict[str, Any]) -> RuntimeHealthV1:
    """Reconstruct a ``RuntimeHealthV1`` from decoded JSON."""
    _require_keys(
        data,
        (
            "schema_version",
            "runtime_id",
            "checked_at",
            "state",
            "process",
            "audio_backend",
            "audio_output",
            "midi_input",
            "synth",
            "session",
            "capture",
            "faults",
        ),
        "health",
    )
    return RuntimeHealthV1(
        schema_version=data["schema_version"],
        runtime_id=data["runtime_id"],
        checked_at=data["checked_at"],
        state=RuntimeState(data["state"]),
        process=SubsystemState(data["process"]),
        audio_backend=SubsystemState(data["audio_backend"]),
        audio_output=SubsystemState(data["audio_output"]),
        midi_input=SubsystemState(data["midi_input"]),
        synth=SubsystemState(data["synth"]),
        session=SubsystemState(data["session"]),
        capture=SubsystemState(data["capture"]),
        faults=tuple(deserialize_fault(f) for f in data["faults"]),
    )
