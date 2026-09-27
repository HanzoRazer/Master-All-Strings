"""Previewing a received delivery reads it and does not start it.

The inbox already holds the envelope. A preview rechecks the two digests pinned
on that envelope, asks the canonical resolver what the lesson is, and returns
a bounded summary. Acceptance, playback, evaluation and guided sessions are
later decisions, and a preview that performed any of them would make "show me
the lesson" and "the student is doing the lesson" the same event.
"""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1
from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    LessonDeliveryPreviewService,
    LessonDeliveryPreviewV1,
    PlaybackPolicySummaryV1,
    UnresolvableAssignmentError,
    preview_to_dict,
)
from master_all_strings.education.assignment_delivery_repository import (
    InMemoryLessonDeliveryRepository,
)
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import (
    LessonDeliveryNotFoundError,
    LessonDeliveryService,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    LessonRoutingV1,
    SerializedMeterChangeV1,
    TeacherOverrideV1,
)
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.lesson.serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
PREVIEW_SOURCE = (
    REPO_ROOT / "src" / "master_all_strings" / "education" / "assignment_delivery_preview.py"
)
FORBIDDEN_IMPORTS = (
    "master_all_strings.performance",
    "master_all_strings.core.transport",
    "master_all_strings.education.evaluation",
    "master_all_strings.education.guided_session",
    "master_all_strings.education.guided_session_service",
    "master_all_strings.mvp.application",
    "master_all_strings.mvp.orchestrator",
    "master_all_strings.mvp.playback",
)


class _GuardingRepository(InMemoryLessonDeliveryRepository):
    """Counts writes. A preview that stores something fails the test."""

    def __init__(self) -> None:
        super().__init__()
        self.writes = 0

    def put_if_absent(self, envelope: LessonDeliveryEnvelopeV1) -> bool:
        self.writes += 1
        return super().put_if_absent(envelope)


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment(
        (EXAMPLES / "instruction_future_fields.json").read_text(encoding="utf-8")
    )


def deliver(
    assignment: LessonAssignmentV1,
    delivery_id: str = "delivery-001",
    *,
    recipient_ref: str = "student-bo",
    classroom_ref: str | None = None,
) -> LessonDeliveryEnvelopeV1:
    return envelope_for(
        assignment,
        delivery_id=delivery_id,
        sender_ref="teacher-ana",
        recipient_ref=recipient_ref,
        classroom_ref=classroom_ref,
    )


def service_holding(
    *envelopes: LessonDeliveryEnvelopeV1,
) -> tuple[LessonDeliveryPreviewService, LessonDeliveryService, _GuardingRepository]:
    repository = _GuardingRepository()
    inbox = LessonDeliveryService(repository=repository)
    for envelope in envelopes:
        inbox.receive(envelope)
    return LessonDeliveryPreviewService(inbox), inbox, repository


def test_a_received_delivery_previews_the_resolved_lesson(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment, classroom_ref="class-7b")
    previews, _inbox, _repository = service_holding(envelope)
    resolved = resolve_lesson_assignment(assignment)

    preview = previews.preview(envelope.delivery_id)
    document = preview_to_dict(preview)

    assert preview.preview_status == "READY"
    assert document["schema_id"] == "master_all_strings.lesson_delivery_preview"
    assert document["schema_version"] == "1.0.0"
    assert document["delivery_id"] == envelope.delivery_id
    assert document["assignment_id"] == resolved.assignment_id
    assert document["content_id"] == resolved.content_id
    assert document["title"] == resolved.title == "Blues Turnaround"
    assert document["canonical_event_ids"] == [event.event_id for event in resolved.events]
    assert document["canonical_event_ids"] == ["ev-1", "ev-2", "ev-3"]
    assert document["canonical_event_count"] == len(resolved.events) == 3
    assert document["meter_change_count"] == len(resolved.meter_changes) == 1
    assert document["instruction_objective"] == resolved.instruction_objective
    assert document["instruction_objective"] == "Play the turnaround cleanly"
    assert document["teacher_note"] == resolved.teacher_note == "Watch the third"
    # Declared on the envelope, not recomputed on the way out.
    assert document["assignment_artifact_digest"] == envelope.assignment_artifact_digest
    assert document["assignment_behavior_digest"] == envelope.assignment_behavior_digest
    playback = document["playback_policy"]
    assert isinstance(playback, dict)
    assert playback == {
        "tempo_bpm": resolved.playback.tempo_bpm,
        "start_tick": resolved.playback.start_tick,
        "end_tick": resolved.playback.end_tick,
        "loop_enabled": resolved.playback.loop_enabled,
        "count_in_bars": resolved.playback.count_in_bars,
        "ticks_per_quarter": resolved.playback.ticks_per_quarter,
        "source_tempo_bpm": resolved.playback.source_tempo_bpm,
    }
    spatial = document["spatial_policy"]
    assert isinstance(spatial, dict)
    assert spatial["instrument_profile_id"] == resolved.spatial.instrument_profile_id
    assert spatial["fingering_policy_id"] == resolved.spatial.fingering_policy_id
    assert spatial["preferred_fret_min"] == resolved.spatial.preferred_fret_min
    assert spatial["preferred_fret_max"] == resolved.spatial.preferred_fret_max
    assert spatial["open_string_preference"] == resolved.spatial.open_string_preference.value
    for absent in (
        "sender_ref",
        "recipient_ref",
        "classroom_ref",
        "assignment",
        "playable",
        "accepted",
    ):
        assert absent not in document


def test_meter_count_follows_the_resolver_not_the_raw_map(assignment: LessonAssignmentV1) -> None:
    # Two declarations at one tick collapse to one canonical change. Counting
    # the assignment's list would report a meter map the resolver does not hold.
    doubled = replace(
        assignment.musical_content,
        meter_changes=(
            SerializedMeterChangeV1(tick=0, numerator=4, denominator=4),
            SerializedMeterChangeV1(tick=0, numerator=3, denominator=4),
        ),
    )
    lesson = replace(assignment, musical_content=doubled)
    envelope = deliver(lesson)
    previews, _inbox, _repository = service_holding(envelope)
    resolved = resolve_lesson_assignment(lesson)

    assert len(lesson.musical_content.meter_changes) == 2
    assert len(resolved.meter_changes) == 1
    assert previews.preview(envelope.delivery_id).meter_change_count == 1


def test_two_recipients_share_the_lesson_and_not_the_delivery(
    assignment: LessonAssignmentV1,
) -> None:
    first = deliver(assignment, "delivery-001", recipient_ref="student-bo")
    second = deliver(
        assignment, "delivery-002", recipient_ref="student-dee", classroom_ref="class-7b"
    )
    previews, _inbox, _repository = service_holding(first, second)

    left = preview_to_dict(previews.preview(first.delivery_id))
    right = preview_to_dict(previews.preview(second.delivery_id))

    assert left["delivery_id"] != right["delivery_id"]
    assert left["assignment_behavior_digest"] == right["assignment_behavior_digest"]
    assert left["canonical_event_ids"] == right["canonical_event_ids"]
    assert left["title"] == right["title"]
    assert "recipient_ref" not in left
    assert "sender_ref" not in left
    assert "classroom_ref" not in right


def test_routing_changes_the_artifact_digest_and_not_the_behavior(
    assignment: LessonAssignmentV1,
) -> None:
    rerouted = replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b"))
    assert compute_assignment_artifact_digest(rerouted) != compute_assignment_artifact_digest(
        assignment
    )
    assert compute_lesson_behavior_digest(rerouted) == compute_lesson_behavior_digest(assignment)

    original = deliver(assignment, "delivery-001")
    redirected = deliver(rerouted, "delivery-002", recipient_ref="student-dee")
    previews, _inbox, _repository = service_holding(original, redirected)
    left = preview_to_dict(previews.preview(original.delivery_id))
    right = preview_to_dict(previews.preview(redirected.delivery_id))

    assert left["assignment_artifact_digest"] == original.assignment_artifact_digest
    assert right["assignment_artifact_digest"] == redirected.assignment_artifact_digest
    assert left["assignment_artifact_digest"] != right["assignment_artifact_digest"]
    assert left["assignment_behavior_digest"] == right["assignment_behavior_digest"]
    assert left["canonical_event_ids"] == right["canonical_event_ids"]


@pytest.mark.parametrize(
    "field_name",
    ["assignment_artifact_digest", "assignment_behavior_digest"],
)
def test_a_digest_mismatch_fails_before_resolution(
    assignment: LessonAssignmentV1, field_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope = deliver(assignment)
    tampered = replace(envelope, **{field_name: "sha256:" + "ab" * 32})
    repository = InMemoryLessonDeliveryRepository()
    assert repository.put_if_absent(tampered)
    previews = LessonDeliveryPreviewService(LessonDeliveryService(repository=repository))

    def explode(_assignment: LessonAssignmentV1) -> None:
        raise AssertionError("resolver ran after a digest mismatch")

    monkeypatch.setattr(
        "master_all_strings.education.assignment_delivery_preview.resolve_lesson_assignment",
        explode,
    )
    with pytest.raises(DeliveryIntegrityError, match=field_name):
        previews.preview(envelope.delivery_id)
    assert repository.get(envelope.delivery_id) == tampered


def test_an_unknown_delivery_is_not_found() -> None:
    previews = LessonDeliveryPreviewService(LessonDeliveryService())
    with pytest.raises(LessonDeliveryNotFoundError, match="missing"):
        previews.preview("missing")


def test_an_unresolvable_assignment_leaves_the_inbox(assignment: LessonAssignmentV1) -> None:
    broken = replace(
        assignment,
        teacher_overrides=(
            TeacherOverrideV1(
                event_id="not-in-the-lesson",
                string_id="1",
                physical_fret_number=1,
            ),
        ),
    )
    envelope = deliver(broken)
    previews, inbox, repository = service_holding(envelope)
    writes = repository.writes
    stored = inbox.get(envelope.delivery_id)

    with pytest.raises(UnresolvableAssignmentError, match="not-in-the-lesson"):
        previews.preview(envelope.delivery_id)

    assert repository.writes == writes
    assert inbox.get(envelope.delivery_id) == stored
    assert [item.delivery_id for item in inbox.list()] == [envelope.delivery_id]


def test_repeated_previews_match_and_the_stored_envelope_is_the_same_object(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    previews, inbox, repository = service_holding(envelope)
    writes = repository.writes
    stored = inbox.get(envelope.delivery_id)
    listed = inbox.list()

    first = preview_to_dict(previews.preview(envelope.delivery_id))
    second = preview_to_dict(previews.preview(envelope.delivery_id))

    assert first == second
    assert repository.writes == writes
    assert inbox.get(envelope.delivery_id) is stored
    assert inbox.list() == listed


def test_preview_does_not_write_or_reach_activation(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment)
    previews, _inbox, repository = service_holding(envelope)
    writes = repository.writes
    previews.preview(envelope.delivery_id)
    assert repository.writes == writes

    tree = ast.parse(PREVIEW_SOURCE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "master_all_strings.lesson.resolver" in imported
    assert "master_all_strings.education.assignment_delivery_serialization" not in imported
    offending = sorted(
        name
        for name in imported
        for forbidden in FORBIDDEN_IMPORTS
        if name == forbidden or name.startswith(forbidden + ".")
    )
    assert offending == []


def test_the_preview_contract_rejects_a_document_it_would_not_emit(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    previews, _inbox, _repository = service_holding(envelope)
    preview = previews.preview(envelope.delivery_id)

    with pytest.raises(EducationContractError, match="preview_status"):
        replace(preview, preview_status="ACCEPTED")
    with pytest.raises(EducationContractError, match="schema_version"):
        replace(preview, schema_version="9.9.9")
    with pytest.raises(EducationContractError, match="schema_id"):
        replace(preview, schema_id="master_all_strings.lesson_delivery")
    with pytest.raises(EducationContractError, match="assignment_artifact_digest"):
        replace(preview, assignment_artifact_digest="not-a-digest")
    with pytest.raises(EducationContractError, match="canonical_event_count"):
        replace(preview, canonical_event_count=preview.canonical_event_count + 1)
    with pytest.raises(EducationContractError, match="playback_policy"):
        replace(preview, playback_policy="not-a-policy")  # type: ignore[arg-type]


def test_playback_and_spatial_summaries_reject_values_the_resolver_does_not_emit(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    previews, _inbox, _repository = service_holding(envelope)
    preview: LessonDeliveryPreviewV1 = previews.preview(envelope.delivery_id)
    playback = preview.playback_policy

    with pytest.raises(EducationContractError, match="loop_enabled"):
        replace(playback, loop_enabled="yes")  # type: ignore[arg-type]
    with pytest.raises(EducationContractError, match="tempo_bpm"):
        replace(playback, tempo_bpm=float("nan"))
    with pytest.raises(EducationContractError, match="open_string_preference"):
        replace(preview.spatial_policy, open_string_preference="required")
    with pytest.raises(EducationContractError, match="ticks_per_quarter"):
        replace(playback, ticks_per_quarter=True)  # type: ignore[arg-type]


def test_null_instruction_is_present_as_null() -> None:
    plain = deserialize_lesson_assignment(
        (EXAMPLES / "local_midi_basic.json").read_text(encoding="utf-8")
    )
    envelope = deliver(plain, "delivery-plain")
    previews, _inbox, _repository = service_holding(envelope)
    document = preview_to_dict(previews.preview(envelope.delivery_id))
    assert "instruction_objective" in document
    assert document["instruction_objective"] is None
    assert document["teacher_note"] is None
    playback = document["playback_policy"]
    assert isinstance(playback, dict)
    # The summary type is part of the result, not an internal playback plan.
    assert isinstance(
        previews.preview(envelope.delivery_id).playback_policy, PlaybackPolicySummaryV1
    )


def test_the_closed_schema_accepts_a_preview_and_rejects_drift(
    assignment: LessonAssignmentV1,
) -> None:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError

    schema_path = (
        REPO_ROOT / "resources" / "education" / "schema" / "lesson_delivery_preview_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    envelope = deliver(assignment)
    previews, _inbox, _repository = service_holding(envelope)
    document = preview_to_dict(previews.preview(envelope.delivery_id))
    validator.validate(document)

    extra = dict(document)
    extra["playable"] = True
    with pytest.raises(ValidationError):
        validator.validate(extra)

    missing = dict(document)
    del missing["teacher_note"]
    with pytest.raises(ValidationError):
        validator.validate(missing)

    wrong_version = dict(document)
    wrong_version["schema_version"] = "2.0.0"
    with pytest.raises(ValidationError):
        validator.validate(wrong_version)

    bad_digest = dict(document)
    bad_digest["assignment_behavior_digest"] = "sha256:not-hex"
    with pytest.raises(ValidationError):
        validator.validate(bad_digest)

    # The preview schema does not restate LessonAssignmentV1.
    assert "assignment" not in schema["properties"]
    assert schema["additionalProperties"] is False
