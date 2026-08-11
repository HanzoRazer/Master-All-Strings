"""Manifest-first consumption of String Master Zone Harmony semantics."""

from master_all_strings.integrations.zone_harmony.correlation import (
    CorrelatedZoneEventV1,
    ZoneSemanticCorrelationError,
    correlate_zone_semantics,
)
from master_all_strings.integrations.zone_harmony.loader import (
    ZoneSemanticLoadError,
    load_zone_semantics_from_bundle,
)
from master_all_strings.integrations.zone_harmony.models import (
    ZoneId,
    ZoneSemanticBundleV1,
    ZoneSemanticEventV1,
    ZoneSemanticRole,
    ZoneTransitionSemanticV1,
    ZoneTransitionType,
)
from master_all_strings.integrations.zone_harmony.projection import (
    apply_zone_semantics_to_projection,
    zone_projection_for_event,
)

__all__ = [
    "ZoneId",
    "CorrelatedZoneEventV1",
    "ZoneSemanticBundleV1",
    "ZoneSemanticEventV1",
    "ZoneSemanticLoadError",
    "ZoneSemanticCorrelationError",
    "ZoneSemanticRole",
    "ZoneTransitionSemanticV1",
    "ZoneTransitionType",
    "load_zone_semantics_from_bundle",
    "correlate_zone_semantics",
    "apply_zone_semantics_to_projection",
    "zone_projection_for_event",
]
