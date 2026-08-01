"""Deterministic revision identity.

``revision_id`` is derived from a sha256 over a canonical serialization, so identity
follows content rather than being assigned. Two callers who build the same revision get
the same id, and any change to what the revision *is* changes the id.

## What the digest covers, and why

**Included.** ``document_id``, ``revision_number``, ``parent_revision_id``,
``ticks_per_quarter``, and the canonicalized events, tempo map, and meter map.

Lineage is inside the digest deliberately. Without it, reverting a document to earlier
content would reproduce the original revision's id while carrying a different revision
number — two distinct revisions sharing one identity, which would make
``get_revision(revision_id)`` ambiguous and break the ``revision_id ==
"rev-" + digest[:24]`` invariant that every citation depends on.

**Excluded.** ``created_at``, because when a revision was recorded is not what it is;
including it would mean the same music ingested twice produced different identities.
``provenance``, because it is audit evidence *about* the derivation, not the content —
two revisions of identical music differing only in rounding residue are the same music.
Document ``title`` and ``description``, because renaming a work does not change its
music, and they live on the document rather than the revision anyway.

## Serialization

A compact JSON array form with fixed field order — not ``sort_keys``, which would make
the format depend on field naming, and not ``repr``, which is not stable across
versions. Floats appear only for ``cents_offset``; it is emitted with ``repr`` so the
value round-trips exactly rather than being reformatted.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol, runtime_checkable

from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.canonicalize import (
    canonicalize_events,
    canonicalize_meter_changes,
    canonicalize_tempo_changes,
)
from master_all_strings.core.score.errors import (
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
    ScoreContractError,
    require_digest,
    require_identifier,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.tempo import TempoChangeV1

# Bumping this changes every revision id, so it is a deliberate, breaking act.
CONTENT_SERIALIZATION_VERSION = "1"

# Named so tests can assert the policy rather than re-deriving it from behaviour.
DIGEST_INCLUDED_FIELDS = (
    "document_id",
    "revision_number",
    "parent_revision_id",
    "ticks_per_quarter",
    "events",
    "tempo_changes",
    "meter_changes",
)
DIGEST_EXCLUDED_FIELDS = ("created_at", "provenance", "title", "description")


def _event_row(event: MusicalEvent) -> list[Any]:
    return [
        event.event_id,
        event.midi_note,
        event.start_tick,
        event.duration_ticks,
        event.velocity,
        repr(float(event.cents_offset)),
        event.voice_id,
    ]


def _tempo_row(change: TempoChangeV1) -> list[Any]:
    return [change.tick, change.microseconds_per_quarter]


def _meter_row(change: MeterChangeV1) -> list[Any]:
    return [change.tick, change.numerator, change.denominator]


def serialize_revision_content(
    *,
    document_id: str,
    revision_number: int,
    parent_revision_id: str | None,
    ticks_per_quarter: int,
    events: tuple[MusicalEvent, ...],
    tempo_changes: tuple[TempoChangeV1, ...],
    meter_changes: tuple[MeterChangeV1, ...],
) -> str:
    """Return the canonical serialization a revision digest is taken over.

    Canonicalizes ordering first, so callers need not, and so the result cannot depend
    on the order the caller happened to build.
    """
    require_identifier(document_id, "document_id")
    payload: list[Any] = [
        CONTENT_SERIALIZATION_VERSION,
        document_id,
        revision_number,
        parent_revision_id,
        ticks_per_quarter,
        [_event_row(event) for event in canonicalize_events(events)],
        [_tempo_row(change) for change in canonicalize_tempo_changes(tempo_changes)],
        [_meter_row(change) for change in canonicalize_meter_changes(meter_changes)],
    ]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def compute_revision_digest(
    *,
    document_id: str,
    revision_number: int,
    parent_revision_id: str | None,
    ticks_per_quarter: int,
    events: tuple[MusicalEvent, ...],
    tempo_changes: tuple[TempoChangeV1, ...],
    meter_changes: tuple[MeterChangeV1, ...],
) -> str:
    """Return the lowercase sha256 hex digest of a revision's canonical content."""
    serialized = serialize_revision_content(
        document_id=document_id,
        revision_number=revision_number,
        parent_revision_id=parent_revision_id,
        ticks_per_quarter=ticks_per_quarter,
        events=events,
        tempo_changes=tempo_changes,
        meter_changes=meter_changes,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def derive_revision_id(content_digest: str) -> str:
    """Return the public revision id for a digest.

    The full digest is always stored on the revision; this is a shortened, readable
    handle. 24 hex characters is 96 bits, which makes an accidental collision
    negligible for any realistic revision count while keeping the id human-quotable.
    """
    require_digest(content_digest, "content_digest")
    return REVISION_ID_PREFIX + content_digest[:REVISION_ID_DIGEST_PREFIX]


@runtime_checkable
class RevisionContentLike(Protocol):
    """The attributes a digest can be computed from.

    Structural rather than nominal so the check can run against a deserialized record
    before it has been promoted to a ``CanonicalScoreRevisionV1``, which is precisely
    when verifying the digest is most useful.
    """

    document_id: str
    revision_number: int
    parent_revision_id: str | None
    ticks_per_quarter: int
    content_digest: str
    events: tuple[MusicalEvent, ...]
    tempo_changes: tuple[TempoChangeV1, ...]
    meter_changes: tuple[MeterChangeV1, ...]


def verify_revision_digest(revision: RevisionContentLike) -> bool:
    """Whether a revision's stored digest matches its content.

    Returns ``False`` rather than raising on malformed input: a corrupt record is a
    verification failure, not a programming error at the call site.
    """
    try:
        expected = compute_revision_digest(
            document_id=revision.document_id,
            revision_number=revision.revision_number,
            parent_revision_id=revision.parent_revision_id,
            ticks_per_quarter=revision.ticks_per_quarter,
            events=revision.events,
            tempo_changes=revision.tempo_changes,
            meter_changes=revision.meter_changes,
        )
    except (AttributeError, ScoreContractError):
        return False
    return bool(expected == revision.content_digest)
