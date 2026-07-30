"""Canonical score document and revision model.

**Owning engine: Musical Core** (ADR-0008). Musical Core is the only authority that may
mint a document id, a revision id, a revision number, or a content digest; every other
engine references those identities and never generates a replacement.

Import order note: this package depends on ``core.musical_events`` and
``core.foundation`` and on nothing else in the repository. It must never import from
``performance``, and it has no Educational or Creative dependency either.
"""

from __future__ import annotations

from master_all_strings.core.score.errors import (
    DIGEST_LENGTH,
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
    ScoreContractError,
)
from master_all_strings.core.score.meter import SUPPORTED_DENOMINATORS, MeterChangeV1
from master_all_strings.core.score.models import (
    FIRST_REVISION_NUMBER,
    SUPPORTED_TICKS_PER_QUARTER,
    CanonicalScoreRevisionV1,
    ScoreDocumentV1,
)
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    RoundingPolicy,
    ScoreSourceKind,
    SourceEventProvenanceV1,
)
from master_all_strings.core.score.tempo import (
    DEFAULT_MICROSECONDS_PER_QUARTER,
    MICROSECONDS_PER_MINUTE,
    TempoChangeV1,
    tempo_from_bpm,
)

__all__ = [
    "DEFAULT_MICROSECONDS_PER_QUARTER",
    "DIGEST_LENGTH",
    "FIRST_REVISION_NUMBER",
    "MICROSECONDS_PER_MINUTE",
    "REVISION_ID_DIGEST_PREFIX",
    "REVISION_ID_PREFIX",
    "SUPPORTED_DENOMINATORS",
    "SUPPORTED_TICKS_PER_QUARTER",
    "CanonicalScoreRevisionV1",
    "MeterChangeV1",
    "RevisionProvenanceV1",
    "RoundingPolicy",
    "ScoreContractError",
    "ScoreDocumentV1",
    "ScoreSourceKind",
    "SourceEventProvenanceV1",
    "TempoChangeV1",
    "tempo_from_bpm",
]
