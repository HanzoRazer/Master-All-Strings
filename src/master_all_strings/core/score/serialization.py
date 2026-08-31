"""Serialize a canonical score revision (DO-013).

A revision that is only computed cannot be cited: a projection naming a revision
id nothing stores is decoration. This module writes the revision itself, so the
citation resolves against a file a reader can open.

The deserializer exists to prove the serializer. If reading the artifact back
does not reproduce the same revision -- same content, same identity -- then the
exported file is a second score model wearing the revision's name, which is
exactly what the boundary forbids.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    RoundingPolicy,
    ScoreSourceKind,
    SourceEventProvenanceV1,
)
from master_all_strings.core.score.tempo import TempoChangeV1

__all__ = ["revision_from_dict", "revision_to_dict"]


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def revision_to_dict(revision: CanonicalScoreRevisionV1) -> dict[str, Any]:
    """Encode a revision, every field included.

    Nothing is dropped -- not ``created_at``, not ``provenance``, not the derived
    ``content_digest``. They are excluded from *identity*, which is a different
    question from whether the artifact should record them: a reader inspecting a
    revision wants to know where it came from.
    """

    if not isinstance(revision, CanonicalScoreRevisionV1):
        raise ScoreContractError("expected CanonicalScoreRevisionV1")
    encoded = _encode(revision)
    if not isinstance(encoded, dict):
        raise ScoreContractError("revision encoding failed")
    return encoded


def _event(payload: dict[str, Any]) -> MusicalEvent:
    return MusicalEvent(
        event_id=payload["event_id"],
        midi_note=payload["midi_note"],
        start_tick=payload["start_tick"],
        duration_ticks=payload["duration_ticks"],
        velocity=payload.get("velocity", 64),
        cents_offset=payload.get("cents_offset", 0.0),
        voice_id=payload.get("voice_id"),
    )


def _source_event_provenance(payload: dict[str, Any]) -> SourceEventProvenanceV1:
    """Rebuild per-event capture provenance.

    Only populated for revisions that came from a performance capture. Authored
    lessons carry none, but the serializer has to round-trip captured revisions
    too or it would only be a serializer for half the corpus.
    """

    return SourceEventProvenanceV1(
        schema_version=payload["schema_version"],
        canonical_event_id=payload["canonical_event_id"],
        source_capture_event_ids=tuple(payload.get("source_capture_event_ids", ())),
        source_channel=payload["source_channel"],
        observed_source_string=payload.get("observed_source_string"),
        source_capture_time_ns=payload["source_capture_time_ns"],
        source_release_time_ns=payload["source_release_time_ns"],
        converted_start_tick=payload["converted_start_tick"],
        converted_duration_ticks=payload["converted_duration_ticks"],
        rounding_delta_start_ns=payload["rounding_delta_start_ns"],
        rounding_delta_duration_ns=payload["rounding_delta_duration_ns"],
        rounding_policy=RoundingPolicy(payload["rounding_policy"]),
        ticks_per_quarter=payload["ticks_per_quarter"],
        microseconds_per_quarter=payload["microseconds_per_quarter"],
    )


def revision_from_dict(payload: dict[str, Any]) -> CanonicalScoreRevisionV1:
    """Rebuild a revision from its serialized form.

    Reconstructs the declared fields only. ``revision_id`` and ``content_digest``
    are read back as recorded rather than recomputed, so a round-trip that
    disagrees with the original is visible as a mismatch instead of being
    silently repaired.
    """

    if not isinstance(payload, dict):
        raise ScoreContractError("revision payload must be a mapping")

    provenance_payload = payload["provenance"]
    provenance = RevisionProvenanceV1(
        schema_version=provenance_payload["schema_version"],
        source_kind=ScoreSourceKind(provenance_payload["source_kind"]),
        policy_version=provenance_payload["policy_version"],
        source_reference=provenance_payload.get("source_reference"),
        event_provenance=tuple(
            _source_event_provenance(item)
            for item in provenance_payload.get("event_provenance", ())
        ),
        notes=tuple(provenance_payload.get("notes", ())),
    )

    return CanonicalScoreRevisionV1(
        schema_version=payload["schema_version"],
        revision_id=payload["revision_id"],
        document_id=payload["document_id"],
        revision_number=payload["revision_number"],
        parent_revision_id=payload.get("parent_revision_id"),
        created_at=payload["created_at"],
        ticks_per_quarter=payload["ticks_per_quarter"],
        content_digest=payload["content_digest"],
        provenance=provenance,
        events=tuple(_event(item) for item in payload.get("events", ())),
        tempo_changes=tuple(
            TempoChangeV1(
                schema_version=item["schema_version"],
                tick=item["tick"],
                microseconds_per_quarter=item["microseconds_per_quarter"],
            )
            for item in payload.get("tempo_changes", ())
        ),
        meter_changes=tuple(
            MeterChangeV1(
                schema_version=item["schema_version"],
                tick=item["tick"],
                numerator=item["numerator"],
                denominator=item["denominator"],
            )
            for item in payload.get("meter_changes", ())
        ),
    )
