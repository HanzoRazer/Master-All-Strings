from __future__ import annotations

import json
from pathlib import Path

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.integrations.zone_harmony import (
    correlate_zone_semantics,
    load_zone_semantics_from_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "resources/mvp2/do008_bundle"


def test_checked_in_bundle_correlates_all_authoritative_semantic_events() -> None:
    semantics = load_zone_semantics_from_bundle(EVIDENCE)
    assert semantics is not None
    events = tuple(
        MusicalEvent(**item)
        for item in json.loads((EVIDENCE / "canonical_events.json").read_text(encoding="utf-8"))
    )

    correlated = correlate_zone_semantics(events, semantics)

    assert len(correlated) == len(events) == 48
    assert {item.zone_semantics.zone_id.value for item in correlated} == {"ZONE_1", "ZONE_2"}
    assert semantics.provenance.string_master_commit == "5d7af1d0efcd026c8cdf861c8a0f8467d77ee03e"


def test_browser_evidence_contains_zone_and_one_string_projection() -> None:
    payload = json.loads((ROOT / "web/mvp1/do008/projection.json").read_text(encoding="utf-8"))
    notes = payload["projection"]["notes"]
    teaching = payload["teaching_aids"]["one_string"]

    assert all(note["zone_semantics"] for note in notes)
    assert {note["zone_semantics"]["zone_id"] for note in notes} == {"ZONE_1", "ZONE_2"}
    assert any(
        "TRITONE_ANCHOR" in note["zone_semantics"]["semantic_roles"] for note in notes
    )
    assert any(
        "HALF_STEP_CROSSING" in note["zone_semantics"]["semantic_roles"] for note in notes
    )
    assert any(
        event["status"] == "unplayable"
        for projection in teaching
        for event in projection["events"]
    )
