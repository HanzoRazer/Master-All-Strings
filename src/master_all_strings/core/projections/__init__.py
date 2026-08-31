"""Canonical projection contracts and builders (DO-013 / MVP 2C).

Governance assigns ``ProjectionRequestV1`` and ``ProjectionResultV1`` to
``MUSICAL_CORE``, so the authoritative projection vocabulary lives here rather
than in a presentation package. See
``docs/architecture/SCORE_PROJECTION_BOUNDARY.md``.
"""

from __future__ import annotations

from master_all_strings.core.projections.contracts import (
    DISPLAY_DURATION_QUARTER_FRACTIONS,
    PROJECTION_SCHEMA_VERSION,
    DisplayDuration,
    NotationDisplayPolicy,
    NotationEventKind,
    NotationEventV1,
    NotationMeasureV1,
    NotationProjectionV1,
    ProjectionKind,
    ProjectionRequestV1,
    ProjectionResultV1,
    ProjectionUnsupportedFeatureV1,
    RestDerivation,
    TabEventStatus,
    TabEventV1,
    TabProjectionV1,
    UnsupportedFeatureCode,
)

__all__ = [
    "DISPLAY_DURATION_QUARTER_FRACTIONS",
    "PROJECTION_SCHEMA_VERSION",
    "DisplayDuration",
    "NotationDisplayPolicy",
    "NotationEventKind",
    "NotationEventV1",
    "NotationMeasureV1",
    "NotationProjectionV1",
    "ProjectionKind",
    "ProjectionRequestV1",
    "ProjectionResultV1",
    "ProjectionUnsupportedFeatureV1",
    "RestDerivation",
    "TabEventStatus",
    "TabEventV1",
    "TabProjectionV1",
    "UnsupportedFeatureCode",
]
