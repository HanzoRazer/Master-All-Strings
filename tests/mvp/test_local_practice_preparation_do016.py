"""Preparing a chosen delivery builds a bundle and writes nothing.

The choice is revalidated, the envelope is captured once, and the existing
pipeline produces the projection, playback plan, practice policy, and score.
A missing choice, a swapped envelope, or a known assignment failure stops
before any of those artifacts are returned.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    LessonDeliveryPreviewService,
    UnresolvableAssignmentError,
)
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import (
    LessonDeliveryNotFoundError,
    LessonDeliveryService,
)
from master_all_strings.education.local_practice_choice import (
    LocalPracticeChoiceService,
    StalePreviewError,
    UnknownPracticeChoiceError,
)
from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    LessonRoutingV1,
    SerializedMeterChangeV1,
    SerializedTempoChangeV1,
    TeacherOverrideV1,
)
from master_all_strings.lesson.serialization import (
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.local_practice_preparation import (
    PREPARATION_STATUS_PREPARED,
    LocalPracticePreparationService,
    PreparationFailure,
    UnpreparableAssignmentError,
    UnsupportedInstrumentError,
    preparation_to_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
OTHER = "sha256:" + "cd" * 32


def load(name: str) -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / name).read_text(encoding="utf-8"))


def service_for(
    application: MvpApplication | None = None,
) -> tuple[LessonDeliveryService, LocalPracticeChoiceService, LocalPracticePreparationService]:
    deliveries = LessonDeliveryService()
    choices = LocalPracticeChoiceService(LessonDeliveryPreviewService(deliveries))
    prepared = LocalPracticePreparationService(
        deliveries,
        choices,
        application or MvpApplication(),
    )
    return deliveries, choices, prepared


def receive(
    deliveries: LessonDeliveryService,
    assignment: LessonAssignmentV1,
    delivery_id: str = "delivery-001",
) -> Any:
    return deliveries.receive(
        envelope_for(
            assignment,
            delivery_id=delivery_id,
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )


def choose_pins(choices: LocalPracticeChoiceService, envelope: Any) -> None:
    choices.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )


def snapshot(
    deliveries: LessonDeliveryService, choices: LocalPracticeChoiceService
) -> tuple[Any, Any]:
    return (
        tuple(
            (key, deliveries.repository._deliveries[key])  # noqa: SLF001
            for key in sorted(deliveries.repository._deliveries)  # noqa: SLF001
        ),
        tuple(
            (key, choices.repository._choices[key])  # noqa: SLF001
            for key in sorted(choices.repository._choices)  # noqa: SLF001
        ),
    )


@pytest.fixture(scope="module")
def application() -> MvpApplication:
    return MvpApplication()


def test_receive_preview_choose_prepare_matches_the_choice(application: MvpApplication) -> None:
    assignment = load("instruction_future_fields.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    preview = LessonDeliveryPreviewService(deliveries).preview(envelope.delivery_id)
    choose_pins(choices, envelope)
    before = snapshot(deliveries, choices)
    result = prepared.prepare(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    document = preparation_to_dict(result)
    assert result.preparation_status == PREPARATION_STATUS_PREPARED
    assert document["delivery_id"] == preview.delivery_id == envelope.delivery_id
    assert document["assignment_id"] == preview.assignment_id
    assert document["content_id"] == preview.content_id
    assert document["assignment_artifact_digest"] == envelope.assignment_artifact_digest
    assert document["assignment_behavior_digest"] == envelope.assignment_behavior_digest
    assert document["projection"]["demo_id"] is None
    assert document["projection"]["instrument_id"] == (
        assignment.spatial_guidance.instrument_profile_id
    )
    tempos = document["projection"]["projection"]["tempo_changes"]
    assert tempos[0]["tempo_bpm"] == assignment.musical_content.tempo_changes[0].tempo_bpm
    meters = document["score"]["canonical_revision"]["meter_changes"]
    assert meters[0]["numerator"] == assignment.musical_content.meter_changes[0].numerator
    projection_digest = document["projection"]["projection"]["projection_digest"]
    assert document["assignment_artifact_digest"] != projection_digest
    revision_id = document["score"]["canonical_revision"]["revision_id"]
    assert document["assignment_behavior_digest"] != revision_id
    assert snapshot(deliveries, choices) == before
    assert serialize_lesson_assignment(deliveries.get(envelope.delivery_id).assignment) == (
        serialize_lesson_assignment(assignment)
    )


def test_teacher_override_tempo_meter_and_simultaneous_notes_keep_their_shape(
    application: MvpApplication,
) -> None:
    override = load("valid_teacher_override.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, override, "delivery-override")
    choose_pins(choices, envelope)
    document = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    origins = {
        note["selection_origin"] for note in document["projection"]["projection"]["notes"]
    }
    assert "teacher_override" in origins

    base = load("local_midi_basic.json")
    first = base.musical_content.events[0]
    chord = replace(
        base,
        musical_content=replace(
            base.musical_content,
            events=(
                first,
                replace(first, event_id="ev-chord", midi_note=first.midi_note + 4),
            )
            + base.musical_content.events[1:],
        ),
    )
    envelope = receive(deliveries, chord, "delivery-chord")
    choose_pins(choices, envelope)
    document = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    notes = document["projection"]["projection"]["notes"]
    paired = [note for note in notes if note["event_id"] in {first.event_id, "ev-chord"}]
    assert len(paired) == 2
    assert paired[0]["onset_tick"] == paired[1]["onset_tick"]
    assert "chord_aware_selection" in document["projection"]["unsupported_features"]

    content = base.musical_content
    varied = replace(
        base,
        musical_content=replace(
            content,
            tempo_changes=content.tempo_changes
            + (SerializedTempoChangeV1(tick=480, tempo_bpm=120.0),),
            meter_changes=content.meter_changes
            + (SerializedMeterChangeV1(tick=960, numerator=3, denominator=4),),
        ),
    )
    envelope = receive(deliveries, varied, "delivery-time")
    choose_pins(choices, envelope)
    document = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    tempo_changes = document["projection"]["projection"]["tempo_changes"]
    tempo_bpm = [change["tempo_bpm"] for change in tempo_changes]
    assert 100.0 in tempo_bpm and 120.0 in tempo_bpm
    meter_pairs = [
        (change["numerator"], change["denominator"])
        for change in document["score"]["canonical_revision"]["meter_changes"]
    ]
    assert (4, 4) in meter_pairs and (3, 4) in meter_pairs


def test_an_unplayable_note_stays_unresolved(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    first = assignment.musical_content.events[0]
    unplayable = replace(
        assignment,
        musical_content=replace(
            assignment.musical_content,
            events=(replace(first, midi_note=0),) + assignment.musical_content.events[1:],
        ),
    )
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, unplayable, "delivery-unplayable")
    choose_pins(choices, envelope)
    document = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    row = next(
        note
        for note in document["projection"]["projection"]["notes"]
        if note["event_id"] == first.event_id
    )
    assert row["status"] == "unplayable"
    assert row["unresolved_reason"]
    assert any(first.event_id in warning for warning in document["projection"]["warnings"])
    tab_row = next(
        event
        for event in document["score"]["tab"]["payload"]["events"]
        if event["canonical_event_id"] == first.event_id
    )
    assert tab_row["status"] != "playable"


def test_two_deliveries_of_one_assignment_stay_distinct(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    first = receive(deliveries, assignment, "delivery-a")
    second = receive(deliveries, assignment, "delivery-b")
    choose_pins(choices, first)
    choose_pins(choices, second)
    left = prepared.prepare(
        first.delivery_id, first.assignment_artifact_digest, first.assignment_behavior_digest
    )
    right = prepared.prepare(
        second.delivery_id, second.assignment_artifact_digest, second.assignment_behavior_digest
    )
    assert left.delivery_id != right.delivery_id
    assert left.assignment_id == right.assignment_id
    assert left.assignment_artifact_digest == right.assignment_artifact_digest


def test_repeating_preparation_writes_nothing(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    choose_pins(choices, envelope)
    before = snapshot(deliveries, choices)
    first = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    second = preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )
    assert snapshot(deliveries, choices) == before
    assert first["delivery_id"] == second["delivery_id"] == envelope.delivery_id
    assert set(first) == set(second)


def test_a_delivery_without_a_choice_is_not_prepared(application: MvpApplication) -> None:
    deliveries, _choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    before = snapshot(deliveries, prepared.choices)
    with pytest.raises(UnknownPracticeChoiceError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert snapshot(deliveries, prepared.choices) == before


def test_a_removed_delivery_is_missing(application: MvpApplication) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    choose_pins(choices, envelope)
    del deliveries.repository._deliveries[envelope.delivery_id]  # noqa: SLF001
    with pytest.raises(LessonDeliveryNotFoundError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert choices.repository.get(envelope.delivery_id) is not None


def test_corrupt_declared_digests_are_an_integrity_failure(application: MvpApplication) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    choose_pins(choices, envelope)
    stored = deliveries.repository._deliveries[envelope.delivery_id]  # noqa: SLF001
    deliveries.repository._deliveries[envelope.delivery_id] = replace(  # noqa: SLF001
        stored, assignment_artifact_digest=OTHER
    )
    with pytest.raises(DeliveryIntegrityError):
        prepared.prepare(
            envelope.delivery_id,
            stored.assignment_artifact_digest,
            stored.assignment_behavior_digest,
        )
    assert choices.repository.get(envelope.delivery_id) is not None


def test_an_intact_replacement_with_different_pins_is_stale(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    choose_pins(choices, envelope)
    rerouted = envelope_for(
        replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b")),
        delivery_id=envelope.delivery_id,
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.repository._deliveries[envelope.delivery_id] = rerouted  # noqa: SLF001
    with pytest.raises(StalePreviewError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )


@pytest.mark.parametrize(
    ("artifact_pin", "behavior_pin"),
    [(OTHER, None), (None, OTHER)],
)
def test_either_request_digest_can_be_stale(
    application: MvpApplication, artifact_pin: str | None, behavior_pin: str | None
) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    choose_pins(choices, envelope)
    before = snapshot(deliveries, choices)
    with pytest.raises(StalePreviewError):
        prepared.prepare(
            envelope.delivery_id,
            artifact_pin or envelope.assignment_artifact_digest,
            behavior_pin or envelope.assignment_behavior_digest,
        )
    assert snapshot(deliveries, choices) == before


def test_physical_validation_fails_after_a_successful_preview(application: MvpApplication) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(
        deliveries, load("invalid/override_impossible_position.json"), "delivery-fret"
    )
    preview = LessonDeliveryPreviewService(deliveries).preview(envelope.delivery_id)
    assert preview.preview_status == "READY"
    choose_pins(choices, envelope)
    before = snapshot(deliveries, choices)
    with pytest.raises(UnpreparableAssignmentError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert snapshot(deliveries, choices) == before


def test_an_unavailable_instrument_is_refused(application: MvpApplication) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("invalid/unknown_instrument.json"), "delivery-instrument")
    choose_pins(choices, envelope)
    with pytest.raises(UnsupportedInstrumentError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )


def test_an_unresolvable_replacement_stays_unresolvable(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    choose_pins(choices, envelope)
    broken = envelope_for(
        replace(
            assignment,
            teacher_overrides=(
                TeacherOverrideV1(
                    event_id="not-in-the-lesson",
                    string_id="1",
                    physical_fret_number=1,
                ),
            ),
        ),
        delivery_id=envelope.delivery_id,
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.repository._deliveries[envelope.delivery_id] = broken  # noqa: SLF001
    with pytest.raises(UnresolvableAssignmentError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )


def test_unexpected_pipeline_and_serialization_failures_stay_internal(
    application: MvpApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    choose_pins(choices, envelope)

    def boom(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("secret pipeline")

    monkeypatch.setattr(prepared.application, "run_assignment_json", boom)
    with pytest.raises(PreparationFailure) as caught:
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert "secret" not in str(caught.value)
    assert snapshot(deliveries, choices)[0]


def test_an_inconsistent_revision_citation_is_internal(
    application: MvpApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from master_all_strings.mvp import local_practice_preparation as preparation_module

    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, load("local_midi_basic.json"))
    choose_pins(choices, envelope)
    real = preparation_module.score_export_payload

    def shifted(response: Any) -> Any:
        payload = real(response)
        assert payload is not None
        payload["tab"]["canonical_revision_id"] = "rev-not-exported"
        return payload

    monkeypatch.setattr(preparation_module, "score_export_payload", shifted)
    with pytest.raises(PreparationFailure) as caught:
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert "rev-not-exported" not in str(caught.value)


def test_a_swap_between_revalidation_and_capture_is_visible(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    choose_pins(choices, envelope)
    replacement = envelope_for(
        replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b")),
        delivery_id=envelope.delivery_id,
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    real_get = choices.get

    def swap_then_return(delivery_id: str) -> Any:
        choice = real_get(delivery_id)
        deliveries.repository._deliveries[delivery_id] = replacement  # noqa: SLF001
        return choice

    choices.get = swap_then_return  # type: ignore[method-assign]
    with pytest.raises(StalePreviewError):
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )


def test_preparation_reads_the_captured_envelope_once(application: MvpApplication) -> None:
    assignment = load("local_midi_basic.json")
    deliveries, choices, prepared = service_for(application)
    envelope = receive(deliveries, assignment)
    choose_pins(choices, envelope)
    calls: list[str] = []
    real_get = deliveries.repository.get

    def counting(delivery_id: str) -> Any:
        calls.append(delivery_id)
        if len(calls) > 2:
            raise AssertionError("preparation loaded the delivery again")
        return real_get(delivery_id)

    deliveries.repository.get = counting  # type: ignore[method-assign]
    seen: list[object] = []
    real_run = prepared.application.run_assignment_json

    def run_and_replace(text: object, instrument_profile_id: str | None = None) -> Any:
        assert instrument_profile_id is None
        seen.append(text)
        deliveries.repository._deliveries[envelope.delivery_id] = envelope_for(  # noqa: SLF001
            replace(assignment, routing=LessonRoutingV1(classroom_id="class-9")),
            delivery_id=envelope.delivery_id,
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
        return real_run(text)  # type: ignore[arg-type]

    prepared.application.run_assignment_json = run_and_replace  # type: ignore[method-assign]
    result = prepared.prepare(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    assert calls == [envelope.delivery_id, envelope.delivery_id]
    assert len(seen) == 1
    assert result.assignment_id == assignment.assignment_id
    assert result.assignment_artifact_digest == envelope.assignment_artifact_digest
