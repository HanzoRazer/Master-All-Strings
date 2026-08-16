"""Identity-safe correlation of external semantics with canonical musical events."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.integrations.zone_harmony.models import (
    ZoneSemanticBundleV1,
    ZoneSemanticEventV1,
)


class ZoneSemanticCorrelationError(ValueError):
    """Semantic and canonical event identities cannot be joined safely."""


@dataclass(frozen=True)
class CorrelatedZoneEventV1:
    """External decoration paired with, but not merged into, a canonical event."""

    canonical_event: MusicalEvent
    zone_semantics: ZoneSemanticEventV1


def correlate_zone_semantics(
    events: Sequence[MusicalEvent],
    semantics: ZoneSemanticBundleV1,
) -> tuple[CorrelatedZoneEventV1, ...]:
    """Join by stable event ID and verify generic pitch identity only."""

    if any(not isinstance(event, MusicalEvent) for event in events):
        raise ZoneSemanticCorrelationError("events must contain MusicalEvent values")
    canonical_by_id = {event.event_id: event for event in events}
    if len(canonical_by_id) != len(events):
        raise ZoneSemanticCorrelationError("canonical event IDs must be unique")
    semantic_by_id = {event.event_id: event for event in semantics.events}
    if set(canonical_by_id) != set(semantic_by_id):
        missing = sorted(set(canonical_by_id) - set(semantic_by_id))
        unexpected = sorted(set(semantic_by_id) - set(canonical_by_id))
        raise ZoneSemanticCorrelationError(
            f"semantic event identity mismatch; missing={missing}, unexpected={unexpected}"
        )

    correlated: list[CorrelatedZoneEventV1] = []
    for event in events:
        semantic = semantic_by_id[event.event_id]
        # Pitch-class reduction is generic pitch identity validation, not Zone theory.
        if event.midi_note % 12 != semantic.pitch_class:
            raise ZoneSemanticCorrelationError(
                f"semantic pitch disagrees with canonical event {event.event_id!r}"
            )
        correlated.append(CorrelatedZoneEventV1(event, semantic))
    return tuple(correlated)


__all__ = [
    "CorrelatedZoneEventV1",
    "ZoneSemanticCorrelationError",
    "correlate_zone_semantics",
]
