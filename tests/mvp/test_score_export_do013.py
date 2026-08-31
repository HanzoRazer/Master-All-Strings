"""Static export of the canonical revision and its score projections (DO-013).

The export exists so a citation resolves. A ``tab.json`` naming a revision id is
only worth something if the named revision sits beside it and is the same
revision the lesson actually produces -- otherwise the exported directory is a
second score model wearing Core's identity, which is what the boundary forbids.

These tests assert that relationship end to end: one revision on both
projections, the same revision the lesson mints, readable back without loss, and
byte-identical on re-export.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from master_all_strings.core.projections.serialization import canonical_projection_digest
from master_all_strings.core.score.provenance import ScoreSourceKind
from master_all_strings.core.score.serialization import revision_from_dict, revision_to_dict
from master_all_strings.lesson.canonicalization import (
    AUTHORED_LESSON_POLICY_VERSION,
    build_authored_lesson_revision,
)
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest
from master_all_strings.mvp.web_export import export_score_projections, export_web_fixtures

WEB_ROOT = Path("web/mvp1")
MANIFEST = load_demo_manifest()
DEMO_IDS = [entry.demo_id for entry in MANIFEST]
PROFILE_BY_DEMO = {entry.demo_id: entry.instrument_profile_id for entry in MANIFEST}
GOLDEN = "half_steps_one_string"


def _lesson_dir(demo_id: str) -> Path:
    return WEB_ROOT / "projections" / demo_id


def _load(demo_id: str, name: str) -> dict:
    return json.loads((_lesson_dir(demo_id) / name).read_text(encoding="utf-8"))


def _authored(demo_id: str):
    """Rebuild a lesson's revision exactly as the product path does."""

    assignment = load_demo_assignment(demo_id)
    return build_authored_lesson_revision(
        resolve_lesson_assignment(assignment),
        created_at=assignment.provenance.created_at_utc,
    )


# --- the citation resolves ---------------------------------------------------


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_every_lesson_exports_a_revision_and_both_projections(demo_id: str) -> None:
    for name in ("canonical_revision.json", "tab.json", "notation.json"):
        assert (_lesson_dir(demo_id) / name).exists(), f"{demo_id} is missing {name}"


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_both_projections_cite_the_revision_exported_beside_them(demo_id: str) -> None:
    """D5: the cited id must resolve against a file a reader can open."""

    revision_id = _load(demo_id, "canonical_revision.json")["revision_id"]
    for name in ("tab.json", "notation.json"):
        result = _load(demo_id, name)
        assert result["canonical_revision_id"] == revision_id
        assert result["payload"]["canonical_revision_id"] == revision_id


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_tab_and_notation_are_two_views_of_one_revision(demo_id: str) -> None:
    """Not merely both resolvable -- both the *same*, which is the whole claim."""

    assert (
        _load(demo_id, "tab.json")["canonical_revision_id"]
        == _load(demo_id, "notation.json")["canonical_revision_id"]
    )


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_exported_revision_is_the_one_the_lesson_mints(demo_id: str) -> None:
    """The export records Core's revision; it does not author one of its own."""

    authored = _authored(demo_id)
    exported = _load(demo_id, "canonical_revision.json")
    assert exported["revision_id"] == authored.revision.revision_id
    assert exported["document_id"] == authored.document_id
    assert exported["content_digest"] == authored.revision.content_digest


# --- the artifact is lossless ------------------------------------------------


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_exported_revision_reads_back_unchanged(demo_id: str) -> None:
    exported = _load(demo_id, "canonical_revision.json")
    assert revision_to_dict(revision_from_dict(exported)) == exported


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_reading_the_revision_back_preserves_its_music(demo_id: str) -> None:
    """A round-trip that only preserved identifiers would prove nothing."""

    authored = _authored(demo_id).revision
    restored = revision_from_dict(_load(demo_id, "canonical_revision.json"))
    assert restored.events == authored.events
    assert restored.tempo_changes == authored.tempo_changes
    assert restored.meter_changes == authored.meter_changes
    assert restored.ticks_per_quarter == authored.ticks_per_quarter


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_exported_revision_records_where_it_came_from(demo_id: str) -> None:
    provenance = _load(demo_id, "canonical_revision.json")["provenance"]
    assert provenance["source_kind"] == ScoreSourceKind.MANUAL_CONSTRUCTION.value
    assert provenance["policy_version"] == AUTHORED_LESSON_POLICY_VERSION
    # Authored lessons have no capture behind them, so recording per-event
    # capture provenance would be a fabrication.
    assert provenance["event_provenance"] == []


# --- digests -----------------------------------------------------------------


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_exported_digests_match_the_live_bundle(
    app: MvpApplication, demo_id: str
) -> None:
    """A recorded digest nothing recomputes is a decoration."""

    response = app.run_demo(demo_id, instrument_profile_id=PROFILE_BY_DEMO[demo_id])
    assert response.score is not None
    assert _load(demo_id, "tab.json")["digest"] == canonical_projection_digest(
        response.score.tab_payload
    )
    assert _load(demo_id, "notation.json")["digest"] == canonical_projection_digest(
        response.score.notation_payload
    )


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_tab_and_notation_of_one_lesson_carry_different_digests(demo_id: str) -> None:
    assert _load(demo_id, "tab.json")["digest"] != _load(demo_id, "notation.json")["digest"]


# --- shape and separation ----------------------------------------------------


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_tab_names_its_instrument_and_notation_does_not(demo_id: str) -> None:
    """Fingering independence, visible in the artifacts themselves."""

    assert _load(demo_id, "tab.json")["payload"]["instrument_profile_id"]
    assert "instrument_profile_id" not in _load(demo_id, "notation.json")["payload"]


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_score_directory_does_not_shadow_the_flat_export(demo_id: str) -> None:
    """DO-008 and DO-012 consumers must find their files exactly where they were."""

    assert (WEB_ROOT / "projections" / f"{demo_id}.json").is_file()
    assert _lesson_dir(demo_id).is_dir()


def test_only_manifest_lessons_have_score_directories() -> None:
    exported = {path.name for path in (WEB_ROOT / "projections").iterdir() if path.is_dir()}
    assert exported == set(DEMO_IDS)


# --- determinism -------------------------------------------------------------


def test_re_export_is_byte_identical(app: MvpApplication, tmp_path: Path) -> None:
    """Two exports of one lesson must not differ, or the fixtures cannot be golden."""

    export_web_fixtures(app, tmp_path)
    first = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    export_web_fixtures(app, tmp_path)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == first


def test_export_reports_the_files_it_wrote(app: MvpApplication, tmp_path: Path) -> None:
    response = app.run_demo(GOLDEN, instrument_profile_id=PROFILE_BY_DEMO[GOLDEN])
    written = export_score_projections(response, tmp_path / GOLDEN)
    assert [path.name for path in written] == [
        "canonical_revision.json",
        "tab.json",
        "notation.json",
    ]
    assert all(path.exists() for path in written)


def test_a_response_without_a_score_bundle_exports_nothing(
    app: MvpApplication, tmp_path: Path
) -> None:
    """Callers predating DO-013 keep working rather than failing on a missing bundle."""

    response = app.run_demo(GOLDEN, instrument_profile_id=PROFILE_BY_DEMO[GOLDEN])
    stripped = dataclasses.replace(response, score=None)
    assert export_score_projections(stripped, tmp_path / GOLDEN) == ()
    assert not (tmp_path / GOLDEN).exists()
