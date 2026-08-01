"""Canonical ingestion — the Performance-to-Musical-Core seam.

**Owning engine: Musical Core.** These contracts are Core-owned even though Performance
produces the request, the same asymmetry ``ScoreEditCommandSet`` uses: the engine that
owns the canonical model owns the vocabulary for changing it, even when another engine
speaks it.

This package imports nothing from ``performance``. It cannot: Musical Core must not
depend on any other engine. Performance imports *these* contracts, which is the
permitted direction.
"""

from __future__ import annotations

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    ProjectionType,
    SourceMidiEventKind,
    SourceMidiEventV1,
)
from master_all_strings.core.ingestion.policies import (
    POLICY_VERSION,
    ImportOutcome,
    import_direct_events,
)
from master_all_strings.core.ingestion.results import (
    CanonicalIngestionResultV1,
    IngestionRejectionV1,
    IngestionStatus,
    IngestionWarningCode,
    IngestionWarningV1,
    RejectionReason,
)
from master_all_strings.core.ingestion.service import (
    CanonicalIngestionService,
    IngestionIdempotencyConflictError,
)

__all__ = [
    "POLICY_VERSION",
    "CanonicalIngestionRequestV1",
    "CanonicalIngestionResultV1",
    "CanonicalIngestionService",
    "ImportOutcome",
    "IngestionIdempotencyConflictError",
    "IngestionRejectionV1",
    "IngestionStatus",
    "IngestionWarningCode",
    "IngestionWarningV1",
    "ProjectionType",
    "RejectionReason",
    "SourceMidiEventKind",
    "SourceMidiEventV1",
    "import_direct_events",
]
