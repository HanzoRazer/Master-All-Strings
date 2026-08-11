"""Add external semantic IDs to the MVP projection without changing spatial truth."""

from __future__ import annotations

from dataclasses import replace

from master_all_strings.integrations.zone_harmony.correlation import CorrelatedZoneEventV1
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import (
    FretboardScrollProjectionV1,
    ZoneSemanticProjectionV1,
)
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    validate_projection,
)


def zone_projection_for_event(item: CorrelatedZoneEventV1) -> ZoneSemanticProjectionV1:
    semantic = item.zone_semantics
    incoming = semantic.transition_from_previous
    return ZoneSemanticProjectionV1(
        zone_id=semantic.zone_id.value,
        semantic_roles=tuple(role.value for role in semantic.semantic_roles),
        tritone_axis_id=semantic.tritone_axis_id,
        transition_from_previous=None if incoming is None else incoming.transition_type.value,
    )


def apply_zone_semantics_to_projection(
    projection: FretboardScrollProjectionV1,
    correlated: tuple[CorrelatedZoneEventV1, ...],
) -> FretboardScrollProjectionV1:
    """Decorate projected notes by event ID; spatial fields remain authoritative."""

    by_event = {
        item.canonical_event.event_id: zone_projection_for_event(item) for item in correlated
    }
    projection_ids = {note.event_id for note in projection.notes}
    if set(by_event) != projection_ids:
        raise ProjectionBuildError("Zone semantics do not cover the projected event identities")
    original_digest = compute_projection_digest(projection)
    decorated = replace(
        projection,
        notes=tuple(
            replace(note, zone_semantics=by_event[note.event_id]) for note in projection.notes
        ),
    )
    validate_projection(decorated)
    if compute_projection_digest(decorated) != original_digest:
        raise ProjectionBuildError("Zone decoration changed spatial projection identity")
    return decorated


__all__ = ["apply_zone_semantics_to_projection", "zone_projection_for_event"]
