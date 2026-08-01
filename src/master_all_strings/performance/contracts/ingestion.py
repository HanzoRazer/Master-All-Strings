"""The Performance side of the Musical Core ingestion seam.

``CanonicalIngestionRequestV1`` and ``ProjectionType`` are **defined in Musical Core**
and re-exported here. DO-006 defined them in this package, which was wrong even then --
the registry has always recorded ``CanonicalIngestionRequestV1`` as
``owning_engine: MUSICAL_CORE``, ``producers: [PERFORMANCE_ENGINE]``. It only became
load-bearing in DO-007, when Core grew a service that consumes the request: leaving the
class here would have forced ``core`` to import from ``performance`` and break the
dependency matrix.

The direction is now correct. Performance imports from Core, which is permitted;
nothing in Core imports from Performance.

The rule this seam enforces is unchanged (ADR-0007 D5, ADR-0008 D2):

* Performance **may** reference a ``canonical_revision_id`` after Core supplies one.
* Performance **may not** mint one.
* Performance **may not** treat a runtime session id as one.
* Performance **may not** implement a competing revision model.

The request now carries no revision field at all, so there is nothing to populate by
mistake. Core's answer arrives on ``CanonicalIngestionResultV1``.
"""

from __future__ import annotations

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    ProjectionType,
    SourceMidiEventKind,
    SourceMidiEventV1,
)
from master_all_strings.core.ingestion.results import CanonicalIngestionResultV1

DEFAULT_PROJECTIONS = (
    ProjectionType.PIANO_ROLL,
    ProjectionType.NOTATION,
    ProjectionType.TAB,
)

__all__ = [
    "DEFAULT_PROJECTIONS",
    "CanonicalIngestionRequestV1",
    "CanonicalIngestionResultV1",
    "ProjectionType",
    "SourceMidiEventKind",
    "SourceMidiEventV1",
]
