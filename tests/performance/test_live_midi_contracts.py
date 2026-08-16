from __future__ import annotations

import dataclasses

import jsonschema
import pytest
from helpers import SCHEMA_DIR, load_json

from master_all_strings.core.foundation import SpatialMappingError
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
    UnmatchedMidiNoteOffV1,
)
from master_all_strings.performance.export import to_dict


def _note(**changes: object) -> ObservedMidiNoteV1:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observed_event_id": "observed-1",
        "capture_id": "capture-1",
        "note_on_event_id": "raw-on-1",
        "note_off_event_id": "raw-off-1",
        "midi_note": 64,
        "velocity": 96,
        "channel": 0,
        "source_device": "device-1",
        "note_on_time_ns": 1_000,
        "note_off_time_ns": 2_500,
        "duration_ns": 1_500,
        "source_string": 3,
        "status": ObservedMidiNoteStatus.COMPLETE,
        "repetition_index": 2,
        "practice_onset_seconds": None,
        "estimated_start_tick": None,
    }
    values.update(changes)
    return ObservedMidiNoteV1(**values)  # type: ignore[arg-type]


def test_observed_note_is_immutable_independent_evidence() -> None:
    note = _note()
    assert note.observed_event_id != note.note_on_event_id
    assert note.repetition_index == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        note.midi_note = 65  # type: ignore[misc]


def test_unmatched_note_on_cannot_invent_note_off_or_duration() -> None:
    note = _note(
        note_off_event_id=None,
        note_off_time_ns=None,
        duration_ns=None,
        status=ObservedMidiNoteStatus.UNMATCHED_NOTE_ON,
    )
    assert note.duration_ns is None
    with pytest.raises(PerformanceContractError, match="must not invent"):
        dataclasses.replace(note, duration_ns=10)


def test_complete_note_duration_must_equal_raw_timestamp_delta() -> None:
    with pytest.raises(PerformanceContractError, match="timestamp delta"):
        _note(duration_ns=1_499)


def test_unmatched_note_off_is_preserved_as_narrow_diagnostic() -> None:
    diagnostic = UnmatchedMidiNoteOffV1(
        schema_version="1.0.0",
        raw_event_id="raw-off-2",
        capture_id="capture-1",
        midi_note=67,
        channel=1,
        source_device="device-1",
        capture_time_ns=3_000,
        source_string=None,
        repetition_index=0,
    )
    assert diagnostic.midi_note == 67


def test_observed_note_schema_matches_contract_and_serialization() -> None:
    schema = load_json(SCHEMA_DIR / "observed_midi_note_v1.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(to_dict(_note()), schema)
    assert set(schema["required"]) == {
        field.name for field in dataclasses.fields(ObservedMidiNoteV1)
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"midi_note": 128}, "midi_note"),
        ({"velocity": 0}, "velocity"),
        ({"repetition_index": -1}, "repetition_index"),
        ({"practice_onset_seconds": float("nan")}, "practice_onset_seconds"),
    ],
)
def test_invalid_observed_note_evidence_is_rejected(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(SpatialMappingError, match=message):
        _note(**change)
