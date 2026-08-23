"""Deterministic serialization for DO-012 presentation contracts.

The browser produces this state at runtime; Python owns the normative shape.
Round-tripping has to be lossless and byte-stable, or the fixture vectors the
Node tests are checked against stop meaning anything.
"""

from __future__ import annotations

import json

import pytest

from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
    SyncCorrection,
    SynchronizationHealthV1,
    SynchronizationStatus,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError
from master_all_strings.presentation.serialization import from_dict, to_dict, to_json

V = PRESENTATION_SCHEMA_VERSION
LESSON = "half_steps_one_string"

ANCHOR = TimelineAnchorV1(schema_version=V, tick=1920, seconds=1.0)

TIMELINE = TeachingTimelineStateV1(
    schema_version=V,
    lesson_id=LESSON,
    sequence=12,
    position_tick=2880,
    position_seconds=1.5,
    playing=True,
    playback_rate=0.75,
    loop_enabled=True,
    repetition_index=2,
    loop_start_tick=1920,
    loop_end_tick=4800,
    loop_start_seconds=1.0,
    loop_end_seconds=2.5,
)

PLAYHEAD = TeachingPlayheadStateV1(
    schema_version=V,
    lesson_id=LESSON,
    sequence=12,
    position_tick=2880,
    position_seconds=1.5,
    active_event_ids=("evt-003", "evt-004"),
    repetition_index=2,
)

BINDING = MediaTimelineBindingV1(
    schema_version=V,
    binding_id="binding-half-steps-demo",
    lesson_id=LESSON,
    media_id="half-steps-demo-video",
    sync_mode=MediaSyncMode.SYNCHRONIZED,
    lesson_anchor_seconds=0.0,
    media_anchor_seconds=0.0,
    lesson_end_seconds=3.0,
    media_end_seconds=3.0,
)

HEALTH = SynchronizationHealthV1(
    schema_version=V,
    follower_id="media:half-steps-demo-video",
    sequence=9,
    status=SynchronizationStatus.DRIFTING,
    expected_time_seconds=1.5,
    actual_time_seconds=1.575,
    drift_ms=75.0,
    last_correction=SyncCorrection.RESAMPLE,
)

RECORDS = [ANCHOR, TIMELINE, PLAYHEAD, BINDING, HEALTH]


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: type(r).__name__)
def test_round_trip_is_lossless(record: object) -> None:
    restored = from_dict(type(record), to_dict(record))
    assert restored == record


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: type(r).__name__)
def test_serialization_is_byte_stable(record: object) -> None:
    assert to_json(record) == to_json(record)
    assert to_json(from_dict(type(record), to_dict(record))) == to_json(record)


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: type(r).__name__)
def test_serialized_form_is_valid_json_ending_in_newline(record: object) -> None:
    text = to_json(record)
    assert text.endswith("\n")
    assert json.loads(text) == to_dict(record)


def test_enums_serialize_as_their_string_values() -> None:
    payload = to_dict(HEALTH)
    assert payload["status"] == "drifting"
    assert payload["last_correction"] == "resample"
    assert to_dict(BINDING)["sync_mode"] == "synchronized"


def test_optional_enum_survives_none() -> None:
    health = SynchronizationHealthV1(
        schema_version=V,
        follower_id="media:demo",
        sequence=1,
        status=SynchronizationStatus.DETACHED,
    )
    assert to_dict(health)["last_correction"] is None
    assert from_dict(SynchronizationHealthV1, to_dict(health)) == health


def test_active_event_ids_restore_as_a_tuple() -> None:
    """JSON has only arrays; the contract requires a tuple."""

    restored = from_dict(TeachingPlayheadStateV1, to_dict(PLAYHEAD))
    assert isinstance(restored.active_event_ids, tuple)


def test_unknown_field_is_rejected_rather_than_ignored() -> None:
    """Silently dropping a field would let a newer record appear to validate."""

    payload = to_dict(PLAYHEAD)
    payload["canonical_revision_id"] = "rev-123"
    with pytest.raises(PresentationContractError, match="unknown field"):
        from_dict(TeachingPlayheadStateV1, payload)


def test_to_dict_rejects_foreign_types() -> None:
    with pytest.raises(PresentationContractError, match="presentation contract"):
        to_dict({"not": "a contract"})


def test_from_dict_rejects_foreign_types() -> None:
    with pytest.raises(PresentationContractError, match="unsupported"):
        from_dict(dict, {})  # type: ignore[arg-type]


def test_from_dict_rejects_non_mapping_payload() -> None:
    with pytest.raises(PresentationContractError, match="mapping"):
        from_dict(TimelineAnchorV1, ["not", "a", "mapping"])  # type: ignore[arg-type]


def test_missing_optional_field_falls_back_to_the_declared_default() -> None:
    payload = to_dict(BINDING)
    del payload["lesson_end_seconds"]
    del payload["media_end_seconds"]
    restored = from_dict(MediaTimelineBindingV1, payload)
    assert restored.lesson_end_seconds is None
