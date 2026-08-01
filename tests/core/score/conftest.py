"""Fixtures for canonical score tests.

Deterministic throughout: no clock is read and no randomness is used, so a revision
built twice from these fixtures is byte-identical. That is what makes the digest
assertions in A3 meaningful.
"""

from __future__ import annotations

import hashlib

import pytest

from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.errors import (
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1, ScoreDocumentV1
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    ScoreSourceKind,
)
from master_all_strings.core.score.tempo import TempoChangeV1, tempo_from_bpm

T0 = "2026-07-29T10:00:00Z"
DOCUMENT_ID = "score-0001"
TICKS_PER_QUARTER = 960


def digest_for(label: str) -> str:
    """A stable stand-in digest.

    A2 validates that ``revision_id`` derives from ``content_digest``; it does not yet
    compute real content digests, which is A3's job. Deriving a fixture digest from a
    label keeps the pair internally consistent without pretending the content was
    hashed.
    """
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def revision_id_for(digest: str) -> str:
    """The revision id that a digest must produce."""
    return REVISION_ID_PREFIX + digest[:REVISION_ID_DIGEST_PREFIX]


@pytest.fixture
def tempo() -> TempoChangeV1:
    return tempo_from_bpm(120.0)


@pytest.fixture
def meter() -> MeterChangeV1:
    return MeterChangeV1(
        schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
    )


@pytest.fixture
def provenance() -> RevisionProvenanceV1:
    return RevisionProvenanceV1(
        schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
        source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
        policy_version="test-1",
    )


def make_event(
    index: int,
    *,
    midi_note: int = 60,
    start_tick: int = 0,
    duration_ticks: int = 480,
    velocity: int = 90,
    voice_id: str | None = None,
) -> MusicalEvent:
    """Build a canonical event with a deterministic id."""
    return MusicalEvent(
        event_id=f"evt-{index:04d}",
        midi_note=midi_note,
        start_tick=start_tick,
        duration_ticks=duration_ticks,
        velocity=velocity,
        voice_id=voice_id,
    )


def make_revision(
    *,
    revision_number: int = 1,
    parent_revision_id: str | None = None,
    document_id: str = DOCUMENT_ID,
    events: tuple[MusicalEvent, ...] = (),
    tempo_changes: tuple[TempoChangeV1, ...] | None = None,
    meter_changes: tuple[MeterChangeV1, ...] | None = None,
    provenance: RevisionProvenanceV1 | None = None,
    digest_label: str | None = None,
    ticks_per_quarter: int = TICKS_PER_QUARTER,
    created_at: str = T0,
) -> CanonicalScoreRevisionV1:
    """Build a structurally valid revision."""
    digest = digest_for(digest_label or f"{document_id}-{revision_number}")
    return CanonicalScoreRevisionV1(
        schema_version=CanonicalScoreRevisionV1.SCHEMA_VERSION,
        revision_id=revision_id_for(digest),
        document_id=document_id,
        revision_number=revision_number,
        parent_revision_id=parent_revision_id,
        created_at=created_at,
        ticks_per_quarter=ticks_per_quarter,
        content_digest=digest,
        provenance=provenance
        or RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
            policy_version="test-1",
        ),
        events=events,
        tempo_changes=tempo_changes
        if tempo_changes is not None
        else (tempo_from_bpm(120.0),),
        meter_changes=meter_changes
        if meter_changes is not None
        else (
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION,
                tick=0,
                numerator=4,
                denominator=4,
            ),
        ),
    )


@pytest.fixture
def origin_revision() -> CanonicalScoreRevisionV1:
    return make_revision(events=(make_event(0), make_event(1, start_tick=480)))


@pytest.fixture
def document(origin_revision: CanonicalScoreRevisionV1) -> ScoreDocumentV1:
    return ScoreDocumentV1(
        schema_version=ScoreDocumentV1.SCHEMA_VERSION,
        document_id=DOCUMENT_ID,
        created_at=T0,
        current_revision_id=origin_revision.revision_id,
        revision_count=1,
    )
