"""Immutable mirrors of the external Zone semantic artifact contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ZoneSemanticContractError(ValueError):
    """The external artifact does not satisfy the supported V1 contract."""


class ZoneId(StrEnum):
    ZONE_1 = "ZONE_1"
    ZONE_2 = "ZONE_2"


class ZoneTransitionType(StrEnum):
    HALF_STEP = "HALF_STEP"
    WHOLE_STEP = "WHOLE_STEP"
    TRITONE = "TRITONE"
    OTHER = "OTHER"


class ZoneSemanticRole(StrEnum):
    ZONE_1 = "ZONE_1"
    ZONE_2 = "ZONE_2"
    TRITONE_ANCHOR = "TRITONE_ANCHOR"
    HALF_STEP_CROSSING = "HALF_STEP_CROSSING"
    WHOLE_STEP_STABLE = "WHOLE_STEP_STABLE"


def _non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ZoneSemanticContractError(f"{field} must be non-empty")


@dataclass(frozen=True)
class ZoneTransitionSemanticV1:
    from_event_id: str
    to_event_id: str
    interval_semitones: int
    transition_type: ZoneTransitionType
    from_zone: ZoneId
    to_zone: ZoneId
    crosses_zone: bool
    semantic_roles: tuple[ZoneSemanticRole, ...]

    def __post_init__(self) -> None:
        _non_empty(self.from_event_id, "from_event_id")
        _non_empty(self.to_event_id, "to_event_id")
        if isinstance(self.interval_semitones, bool) or not 0 <= self.interval_semitones <= 11:
            raise ZoneSemanticContractError("interval_semitones must be an integer from 0 to 11")
        if not isinstance(self.crosses_zone, bool):
            raise ZoneSemanticContractError("crosses_zone must be a boolean")


@dataclass(frozen=True)
class ZoneSemanticEventV1:
    event_id: str
    pitch_class: int
    zone_id: ZoneId
    tritone_axis_id: str
    semantic_roles: tuple[ZoneSemanticRole, ...]
    transition_from_previous: ZoneTransitionSemanticV1 | None = None

    def __post_init__(self) -> None:
        _non_empty(self.event_id, "event_id")
        if isinstance(self.pitch_class, bool) or not 0 <= self.pitch_class <= 11:
            raise ZoneSemanticContractError("pitch_class must be an integer from 0 to 11")
        _non_empty(self.tritone_axis_id, "tritone_axis_id")


@dataclass(frozen=True)
class ZoneSemanticProvenanceV1:
    producer: str
    source_bundle_id: str
    generation_id: str | None
    string_master_commit: str
    authority: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _non_empty(self.producer, "producer")
        _non_empty(self.source_bundle_id, "source_bundle_id")
        _non_empty(self.string_master_commit, "string_master_commit")
        if self.generation_id is not None:
            _non_empty(self.generation_id, "generation_id")


@dataclass(frozen=True)
class ZoneSemanticBundleV1:
    artifact_type: str
    schema_version: str
    theory_name: str
    theory_version: str
    source_id: str
    events: tuple[ZoneSemanticEventV1, ...]
    transitions: tuple[ZoneTransitionSemanticV1, ...]
    provenance: ZoneSemanticProvenanceV1

    def __post_init__(self) -> None:
        if self.artifact_type != "zone_semantics":
            raise ZoneSemanticContractError("unsupported artifact_type")
        if self.schema_version != "1.0":
            raise ZoneSemanticContractError("unsupported Zone semantic schema version")
        _non_empty(self.theory_name, "theory_name")
        _non_empty(self.theory_version, "theory_version")
        _non_empty(self.source_id, "source_id")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ZoneSemanticContractError("Zone semantic event IDs must be unique")


__all__ = [
    "ZoneId",
    "ZoneSemanticBundleV1",
    "ZoneSemanticContractError",
    "ZoneSemanticEventV1",
    "ZoneSemanticProvenanceV1",
    "ZoneSemanticRole",
    "ZoneTransitionSemanticV1",
    "ZoneTransitionType",
]
