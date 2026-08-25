"""Regenerate the synthetic projection fixtures (DO-013A).

The eleven bundled lessons are deliberately ordinary: every one is 480 PPQ in a
single meter with exact quarter-note rhythm and no silence. That is the right
shape for teaching material and the wrong shape for proving what the projection
builders do at their edges. Nothing in the corpus changes meter, leaves a gap,
carries a duration the notation grammar cannot spell, or places two identical
pitches across a barline where an engraver would expect a tie.

So these five cases are constructed. What they are *not* is a second
implementation: each revision is minted through Core's own
``CanonicalRevisionService`` and then run through the same
``build_tab_projection`` / ``build_notation_projection`` the product calls. The
fixture supplies unusual input; every answer in the output comes from production
code, which is why the files are generated rather than hand-written.

The cases are declared here as events and meters rather than as expected output,
so a change in Core or in a builder shows up as a diff in the generated JSON
instead of silently disagreeing with a hand-typed expectation.

These revisions are not lessons and must never become lessons. They carry their
own provenance policy and their own visibly synthetic timestamp so that no
artifact of theirs can be mistaken for authored teaching material.

Usage: python scripts/build_projection_fixtures.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.projections.notation import build_notation_projection
from master_all_strings.core.projections.serialization import projection_to_json
from master_all_strings.core.projections.tab import (
    SelectedSpatialRealizationV1,
    build_tab_projection,
)
from master_all_strings.core.score.ids import LessonDocumentIdAuthority
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.score.provenance import RevisionProvenanceV1, ScoreSourceKind
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository
from master_all_strings.core.score.revision_service import CanonicalRevisionService
from master_all_strings.core.score.tempo import tempo_from_bpm
from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.mvp.application import load_default_instrument_catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "resources" / "projections" / "examples"

#: Every synthetic revision is stamped with this instead of a lesson's own date.
#:
#: Fixed, deterministic, and visibly not a lesson: no bundled lesson claims this
#: timestamp, so an artifact carrying it cannot be mistaken for authored
#: material, and no wall clock is ever read.
SYNTHETIC_FIXTURE_CREATED_AT_UTC = "2026-08-25T00:00:00Z"

#: Distinct from the authored-lesson token, so provenance never claims a fixture
#: came from the teaching corpus.
SYNTHETIC_FIXTURE_POLICY_VERSION = "SYNTHETIC_PROJECTION_FIXTURE_V1"

INSTRUMENT_PROFILE_ID = "guitar-standard-6"

TICKS_PER_QUARTER = 480
QUARTER = TICKS_PER_QUARTER
MEASURE_4_4 = QUARTER * 4


def _four_four(tick: int = 0) -> MeterChangeV1:
    return _meter(tick, 4, 4)


def _meter(tick: int, numerator: int, denominator: int) -> MeterChangeV1:
    return MeterChangeV1(
        schema_version=MeterChangeV1.SCHEMA_VERSION,
        tick=tick,
        numerator=numerator,
        denominator=denominator,
    )


def _note(event_id: str, midi_note: int, start_tick: int, duration_ticks: int) -> MusicalEvent:
    return MusicalEvent(
        event_id=event_id,
        midi_note=midi_note,
        start_tick=start_tick,
        duration_ticks=duration_ticks,
    )


@dataclass(frozen=True)
class SyntheticCase:
    """One constructed revision plus the reason it exists."""

    name: str
    #: What this case proves. Carried with the data so a failing fixture explains
    #: itself rather than leaving a reader to reverse-engineer the intent.
    proves: str
    content_id: str
    kind: str
    events: tuple[MusicalEvent, ...]
    meter_changes: tuple[MeterChangeV1, ...] = field(default_factory=lambda: (_four_four(),))
    ticks_per_quarter: int = TICKS_PER_QUARTER
    tempo_bpm: float = 120.0
    created_at: str = SYNTHETIC_FIXTURE_CREATED_AT_UTC
    #: Canonical event ids that deliberately receive no selected spatial
    #: evidence. Only meaningful for TAB cases.
    withheld_selection: tuple[str, ...] = ()


# --- the five authorized cases ------------------------------------------------

#: A note whose spatial realization is withheld.
#:
#: TAB must say it does not know rather than reaching past the selection for a
#: candidate of its own. ``ev-1`` is a control: same builder, same call, evidence
#: present -- so the fixture shows the difference is the evidence and not the code
#: path. Explicit unplayability is already witnessed by the real
#: ``unplayable_note`` lesson and is not duplicated here.
UNRESOLVED_TAB = SyntheticCase(
    name="unresolved_tab",
    proves="absent selected spatial evidence yields UNRESOLVED, never an invented fret",
    content_id="synthetic_unresolved_tab",
    kind="tab",
    events=(
        _note("ev-1", 64, 0, QUARTER),
        _note("ev-2", 65, QUARTER, QUARTER),
    ),
    withheld_selection=("ev-2",),
)

#: 4/4 for one measure, then 3/4.
#:
#: The second measure is 1440 ticks rather than 1920, so a builder that cached the
#: opening meter would place the later notes in the wrong bar.
METER_CHANGE_NOTATION = SyntheticCase(
    name="meter_change_notation",
    proves="measures are built from the meter in force, on both sides of a change",
    content_id="synthetic_meter_change",
    kind="notation",
    events=(
        _note("ev-1", 60, 0, QUARTER),
        _note("ev-2", 62, QUARTER, QUARTER),
        _note("ev-3", 64, QUARTER * 2, QUARTER),
        _note("ev-4", 65, QUARTER * 3, QUARTER),
        _note("ev-5", 67, MEASURE_4_4, QUARTER),
        _note("ev-6", 69, MEASURE_4_4 + QUARTER, QUARTER),
        _note("ev-7", 71, MEASURE_4_4 + QUARTER * 2, QUARTER),
    ),
    meter_changes=(_four_four(), _meter(MEASURE_4_4, 3, 4)),
)

#: A real gap: sounding [0,480), silent [480,720), sounding [720,960).
#:
#: The silence is genuine -- no note of any kind is sounding across it -- so
#: exactly one rest is owed, and it is an eighth.
GLOBAL_REST_NOTATION = SyntheticCase(
    name="global_rest_notation",
    proves="a rest is derived for true global silence and for nothing else",
    content_id="synthetic_global_rest",
    kind="notation",
    events=(
        _note("ev-1", 64, 0, QUARTER),
        _note("ev-2", 67, 720, 240),
    ),
)

#: 45 ticks at 480 PPQ is not any note value, dotted or otherwise.
#:
#: The nearest spellings are a thirty-second (60) and nothing below it, and
#: rounding to either would be the projection quietly changing the music. The
#: derived rest inherits the problem -- 435 ticks is equally unspellable -- which
#: is worth showing: unsupported-ness propagates rather than being smoothed away
#: once it reaches a value the builder itself computed.
UNSUPPORTED_DURATION_NOTATION = SyntheticCase(
    name="unsupported_duration_notation",
    proves="an unspellable duration is reported and preserved, never rounded",
    content_id="synthetic_unsupported_duration",
    kind="notation",
    events=(
        _note("ev-1", 64, 0, 45),
        _note("ev-2", 64, QUARTER, QUARTER),
    ),
)

#: Two whole notes on the same pitch, meeting exactly at a barline.
#:
#: This is the textbook shape an engraver ties, and the canonical revision says
#: nothing about a tie. So the fixture's value is entirely negative: it exists to
#: fail if the builder ever starts inferring one from pitch and adjacency.
UNSUPPORTED_TIE_NOTATION = SyntheticCase(
    name="unsupported_tie_notation",
    proves="adjacent same-pitch notes across a barline stay independent, untied",
    content_id="synthetic_unsupported_tie",
    kind="notation",
    events=(
        _note("ev-1", 64, 0, MEASURE_4_4),
        _note("ev-2", 64, MEASURE_4_4, MEASURE_4_4),
    ),
)

CASES: tuple[SyntheticCase, ...] = (
    UNRESOLVED_TAB,
    METER_CHANGE_NOTATION,
    GLOBAL_REST_NOTATION,
    UNSUPPORTED_DURATION_NOTATION,
    UNSUPPORTED_TIE_NOTATION,
)


def build_synthetic_revision(case: SyntheticCase) -> CanonicalScoreRevisionV1:
    """Mint a case's revision through Core, exactly as the product path does.

    Same service, same document authority, same manual-construction door. Only
    the provenance policy differs, and it differs so that a synthetic revision
    can never be mistaken for an authored lesson.
    """

    service = CanonicalRevisionService(
        InMemoryCanonicalScoreRepository(), LessonDocumentIdAuthority(case.content_id)
    )
    creation = service.create_document_with_revision(
        created_at=case.created_at,
        provenance=RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
            policy_version=SYNTHETIC_FIXTURE_POLICY_VERSION,
            source_reference=case.content_id,
        ),
        events=case.events,
        tempo_changes=(tempo_from_bpm(case.tempo_bpm, tick=0),),
        meter_changes=case.meter_changes,
        ticks_per_quarter=case.ticks_per_quarter,
        title=case.name,
    )
    return creation.revision


def build_selection(
    case: SyntheticCase, revision: CanonicalScoreRevisionV1
) -> dict[str, SelectedSpatialRealizationV1]:
    """Realize each event spatially, except the ones the case withholds.

    Candidates come from the real spatial mapper rather than from hand-written
    string/fret pairs, so the selected evidence a TAB fixture consumes is the
    same kind of evidence the product produces.
    """

    profile = load_default_instrument_catalog()[INSTRUMENT_PROFILE_ID]
    selected: dict[str, SelectedSpatialRealizationV1] = {}
    for event in revision.events:
        if event.event_id in case.withheld_selection:
            continue
        candidates = generate_candidates(event, profile)
        if not candidates:
            continue
        selected[event.event_id] = SelectedSpatialRealizationV1(
            canonical_event_id=event.event_id, position=candidates[0]
        )
    return selected


def render_case(case: SyntheticCase) -> str:
    """Run one case through the production builder and serialize the result."""

    revision = build_synthetic_revision(case)
    if case.kind == "tab":
        payload = build_tab_projection(
            revision,
            instrument_profile_id=INSTRUMENT_PROFILE_ID,
            selected=build_selection(case, revision),
        )
    else:
        payload = build_notation_projection(revision)
    return projection_to_json(payload)


def fixture_path(case: SyntheticCase) -> Path:
    return EXAMPLES / f"{case.name}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the checked-in fixtures match, without writing",
    )
    args = parser.parse_args(argv)

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for case in CASES:
        rendered = render_case(case)
        path = fixture_path(case)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                stale.append(case.name)
            continue
        path.write_text(rendered, encoding="utf-8")

    if args.check:
        if stale:
            print("stale projection fixtures: " + ", ".join(stale), file=sys.stderr)
            print("run: python scripts/build_projection_fixtures.py", file=sys.stderr)
            return 1
        print(f"projection fixtures current: {len(CASES)} cases")
        return 0

    print(f"wrote {len(CASES)} projection fixtures to {EXAMPLES}")
    for case in CASES:
        print(f"  {case.name}.json  -- {case.proves}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
