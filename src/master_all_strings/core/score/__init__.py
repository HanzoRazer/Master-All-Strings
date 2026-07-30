"""Canonical score document and revision model.

**Owning engine: Musical Core** (ADR-0008). Musical Core is the only authority that may
mint a document id, a revision id, a revision number, or a content digest; every other
engine references those identities and never generates a replacement.

Import order note: this package depends on ``core.musical_events`` and
``core.foundation`` and on nothing else in the repository. It must never import from
``performance``, and it has no Educational or Creative dependency either.
"""

from __future__ import annotations

from master_all_strings.core.score.canonicalize import (
    canonicalize_events,
    canonicalize_meter_changes,
    canonicalize_tempo_changes,
)
from master_all_strings.core.score.digest import (
    compute_revision_digest,
    derive_revision_id,
    serialize_revision_content,
    verify_revision_digest,
)
from master_all_strings.core.score.errors import (
    DIGEST_LENGTH,
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
    ScoreContractError,
)
from master_all_strings.core.score.ids import (
    DeterministicDocumentIdAuthority,
    DocumentIdAuthority,
    FixedDocumentIdAuthority,
    UuidDocumentIdAuthority,
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
from master_all_strings.core.score.timing import (
    DEFAULT_TICKS_PER_QUARTER,
    TickConversion,
    convert_duration,
    convert_elapsed,
    nanoseconds_to_ticks,
    ticks_to_nanoseconds,
)

__all__ = [
    "CanonicalScoreRevisionV1",
    "DEFAULT_MICROSECONDS_PER_QUARTER",
    "DEFAULT_TICKS_PER_QUARTER",
    "DIGEST_LENGTH",
    "DeterministicDocumentIdAuthority",
    "DocumentIdAuthority",
    "FIRST_REVISION_NUMBER",
    "FixedDocumentIdAuthority",
    "MICROSECONDS_PER_MINUTE",
    "MeterChangeV1",
    "REVISION_ID_DIGEST_PREFIX",
    "REVISION_ID_PREFIX",
    "RevisionProvenanceV1",
    "RoundingPolicy",
    "SUPPORTED_DENOMINATORS",
    "SUPPORTED_TICKS_PER_QUARTER",
    "ScoreContractError",
    "ScoreDocumentV1",
    "ScoreSourceKind",
    "SourceEventProvenanceV1",
    "TempoChangeV1",
    "TickConversion",
    "UuidDocumentIdAuthority",
    "canonicalize_events",
    "canonicalize_meter_changes",
    "canonicalize_tempo_changes",
    "compute_revision_digest",
    "convert_duration",
    "convert_elapsed",
    "derive_revision_id",
    "nanoseconds_to_ticks",
    "serialize_revision_content",
    "tempo_from_bpm",
    "ticks_to_nanoseconds",
    "verify_revision_digest",
]
