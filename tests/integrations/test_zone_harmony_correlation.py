from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.digest import compute_revision_digest
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.core.spatial_mapping import (
    generate_candidates,
    instrument_profile_from_mapping,
)
from master_all_strings.integrations.zone_harmony import (
    ZoneId,
    ZoneSemanticBundleV1,
    ZoneSemanticCorrelationError,
    ZoneSemanticEventV1,
    ZoneSemanticRole,
    correlate_zone_semantics,
)
from master_all_strings.integrations.zone_harmony.models import ZoneSemanticProvenanceV1

_GUITAR = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "instruments"
    / "examples"
    / "guitar-standard-6.json"
)


def _events() -> tuple[MusicalEvent, ...]:
    return (
        MusicalEvent("comp:000000", 60, 0, 480),
        MusicalEvent("comp:000001", 61, 480, 480),
    )


def _semantics() -> ZoneSemanticBundleV1:
    return ZoneSemanticBundleV1(
        artifact_type="zone_semantics",
        schema_version="1.0",
        theory_name="String Master Zone/Tritone",
        theory_version="0.1.0",
        source_id="request-1",
        events=(
            ZoneSemanticEventV1(
                "comp:000000", 0, ZoneId.ZONE_1, "0-6", (ZoneSemanticRole.ZONE_1,)
            ),
            ZoneSemanticEventV1(
                "comp:000001", 1, ZoneId.ZONE_2, "1-7", (ZoneSemanticRole.ZONE_2,)
            ),
        ),
        transitions=(),
        provenance=ZoneSemanticProvenanceV1(
            "sg-agentd", "clip-1", "request-1", "5" * 40, (("producer", "zt_band"),)
        ),
    )


def _digest(events: tuple[MusicalEvent, ...]) -> str:
    return compute_revision_digest(
        document_id="doc-1",
        revision_number=1,
        parent_revision_id=None,
        ticks_per_quarter=480,
        events=events,
        tempo_changes=(
            TempoChangeV1(schema_version="1.0.0", tick=0, microseconds_per_quarter=500_000),
        ),
        meter_changes=(
            MeterChangeV1(schema_version="1.0.0", tick=0, numerator=4, denominator=4),
        ),
    )


def test_correlation_preserves_canonical_event_digest_and_object_identity() -> None:
    events = _events()
    before = _digest(events)

    correlated = correlate_zone_semantics(events, _semantics())

    assert tuple(item.canonical_event for item in correlated) == events
    assert all(
        item.canonical_event is event for item, event in zip(correlated, events, strict=True)
    )
    assert _digest(tuple(item.canonical_event for item in correlated)) == before


def test_msme_candidates_are_identical_with_or_without_zone_correlation() -> None:
    events = _events()
    instrument = instrument_profile_from_mapping(json.loads(_GUITAR.read_text(encoding="utf-8")))
    before = tuple(generate_candidates(event, instrument) for event in events)

    correlated = correlate_zone_semantics(events, _semantics())
    after = tuple(generate_candidates(item.canonical_event, instrument) for item in correlated)

    assert after == before


def test_rejects_missing_or_unexpected_semantic_event_ids() -> None:
    semantics = replace(_semantics(), events=_semantics().events[:1])

    with pytest.raises(ZoneSemanticCorrelationError, match="identity mismatch"):
        correlate_zone_semantics(_events(), semantics)


def test_rejects_pitch_disagreement_without_reclassifying_it() -> None:
    wrong = replace(_semantics().events[0], pitch_class=11)
    semantics = replace(_semantics(), events=(wrong, _semantics().events[1]))

    with pytest.raises(ZoneSemanticCorrelationError, match="pitch disagrees"):
        correlate_zone_semantics(_events(), semantics)
