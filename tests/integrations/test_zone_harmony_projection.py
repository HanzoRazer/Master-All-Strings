from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.integrations.zone_harmony import (
    CorrelatedZoneEventV1,
    ZoneId,
    ZoneSemanticEventV1,
    ZoneSemanticRole,
    apply_zone_semantics_to_projection,
)
from master_all_strings.mvp.application import MvpApplication, load_default_instrument_catalog
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    deserialize_fretboard_projection,
    serialize_fretboard_projection,
)


@pytest.fixture
def app() -> MvpApplication:
    return MvpApplication(instrument_profiles=load_default_instrument_catalog())


def _correlations(app: MvpApplication) -> tuple[CorrelatedZoneEventV1, ...]:
    response = app.run_demo("ascending_scale")
    canonical = {
        note.event_id: MusicalEvent(
            note.event_id,
            note.midi_note,
            note.onset_tick,
            note.duration_ticks,
        )
        for note in response.projection.notes
    }
    return tuple(
        CorrelatedZoneEventV1(
            canonical_event=canonical[note.event_id],
            zone_semantics=ZoneSemanticEventV1(
                event_id=note.event_id,
                pitch_class=note.midi_note % 12,
                zone_id=ZoneId.ZONE_1,
                tritone_axis_id="0-6",
                semantic_roles=(ZoneSemanticRole.ZONE_1,),
            ),
        )
        for note in response.projection.notes
    )


def _spatial_rows(projection):
    return tuple(
        (
            note.event_id,
            note.onset_tick,
            note.duration_ticks,
            note.string_id,
            note.fret_number,
            note.normalized_position,
            note.selection_origin,
        )
        for note in projection.notes
    )


def test_zone_projection_is_additive_and_spatially_identical(app: MvpApplication) -> None:
    plain = app.run_demo("ascending_scale").projection
    decorated = apply_zone_semantics_to_projection(plain, _correlations(app))

    assert _spatial_rows(decorated) == _spatial_rows(plain)
    assert decorated.projection_digest == plain.projection_digest
    assert compute_projection_digest(decorated) == compute_projection_digest(plain)
    assert all(note.zone_semantics is not None for note in decorated.notes)


def test_absent_semantics_do_not_change_existing_serialization(app: MvpApplication) -> None:
    plain = app.run_demo("ascending_scale").projection

    assert '"zone_semantics"' not in serialize_fretboard_projection(plain)


def test_decorated_projection_round_trips_semantic_ids(app: MvpApplication) -> None:
    plain = app.run_demo("ascending_scale").projection
    decorated = apply_zone_semantics_to_projection(plain, _correlations(app))

    restored = deserialize_fretboard_projection(serialize_fretboard_projection(decorated))

    assert restored.notes[0].zone_semantics == decorated.notes[0].zone_semantics
    assert restored.projection_digest == plain.projection_digest
