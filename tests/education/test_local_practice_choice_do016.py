"""Choosing a delivery for practice records that choice and nothing else.

The inbox already holds the envelope. A choice previews it again, compares the
digests the caller saw with the ones the envelope declares, and stores a closed
record. That record is not acceptance, playback, evaluation, or a guided session.
"""

from __future__ import annotations

import ast
import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1
from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    LessonDeliveryPreviewService,
    UnresolvableAssignmentError,
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
from master_all_strings.education.local_practice_choice import (
    CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
    LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
    LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
    ChoiceConflictError,
    LocalPracticeChoiceService,
    LocalPracticeChoiceV1,
    StalePreviewError,
    UnknownPracticeChoiceError,
    choice_to_dict,
)
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    LessonRoutingV1,
    TeacherOverrideV1,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
CHOICE_SOURCE = REPO_ROOT / "src" / "master_all_strings" / "education" / "local_practice_choice.py"
REPOSITORY_SOURCE = (
    REPO_ROOT / "src" / "master_all_strings" / "education" / "local_practice_choice_repository.py"
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
    "master_all_strings.lesson.resolver",
    "master_all_strings.education.assignment_delivery_serialization",
)
OTHER_DIGEST = "sha256:" + "cd" * 32


class _GuardingChoiceRepository(InMemoryLocalPracticeChoiceRepository):
    """Counts insert attempts. A refused choice must not call this."""

    def __init__(self) -> None:
        super().__init__()
        self.writes = 0

    def put_if_absent(self, choice: LocalPracticeChoiceV1) -> bool:
        self.writes += 1
        return super().put_if_absent(choice)


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


def holding(
    *envelopes: LessonDeliveryEnvelopeV1,
) -> tuple[LocalPracticeChoiceService, LessonDeliveryService, _GuardingChoiceRepository]:
    inbox = LessonDeliveryService(repository=InMemoryLessonDeliveryRepository())
    for envelope in envelopes:
        inbox.receive(envelope)
    choices = _GuardingChoiceRepository()
    service = LocalPracticeChoiceService(LessonDeliveryPreviewService(inbox), choices)
    return service, inbox, choices


def test_a_verified_delivery_can_be_chosen_and_read_back(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment, classroom_ref="class-7b")
    service, inbox, repository = holding(envelope)
    preview = LessonDeliveryPreviewService(inbox).preview(envelope.delivery_id)

    choice, created = service.choose(
        envelope.delivery_id,
        preview.assignment_artifact_digest,
        preview.assignment_behavior_digest,
    )
    document = choice_to_dict(choice)

    assert created is True
    assert choice.choice_status == CHOICE_STATUS_CHOSEN_FOR_PRACTICE
    assert document["schema_id"] == LOCAL_PRACTICE_CHOICE_SCHEMA_ID
    assert document["schema_version"] == LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION
    assert document["delivery_id"] == envelope.delivery_id
    assert document["assignment_id"] == preview.assignment_id
    assert document["content_id"] == preview.content_id
    assert document["assignment_artifact_digest"] == envelope.assignment_artifact_digest
    assert document["assignment_behavior_digest"] == envelope.assignment_behavior_digest
    for absent in (
        "sender_ref",
        "recipient_ref",
        "classroom_ref",
        "assignment",
        "accepted",
        "playable",
    ):
        assert absent not in document
    assert service.get(envelope.delivery_id) is choice
    assert inbox.get(envelope.delivery_id) is envelope
    assert LessonDeliveryPreviewService(inbox).preview(envelope.delivery_id) == preview


def test_an_identical_repeat_returns_the_same_record(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)
    first, created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    second, again = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )

    assert created is True
    assert again is False
    assert second is first
    assert repository.writes == 2
    assert repository.get(envelope.delivery_id) is first


def test_two_concurrent_identical_choices_store_one_record(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)
    start = threading.Barrier(2)
    results: list[tuple[LocalPracticeChoiceV1, bool]] = []
    lock = threading.Lock()

    def choose() -> None:
        start.wait()
        outcome = service.choose(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=choose) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 2
    assert {created for _choice, created in results} == {True, False}
    assert results[0][0] == results[1][0]
    assert repository.get(envelope.delivery_id) == results[0][0]


def test_two_recipients_of_one_assignment_choose_independently(
    assignment: LessonAssignmentV1,
) -> None:
    first = deliver(assignment, "delivery-001", recipient_ref="student-bo")
    second = deliver(assignment, "delivery-002", recipient_ref="student-dee")
    service, _inbox, _repository = holding(first, second)

    left, _created = service.choose(
        first.delivery_id,
        first.assignment_artifact_digest,
        first.assignment_behavior_digest,
    )
    right, _created = service.choose(
        second.delivery_id,
        second.assignment_artifact_digest,
        second.assignment_behavior_digest,
    )

    assert left.delivery_id != right.delivery_id
    assert left.assignment_id == right.assignment_id
    assert left.assignment_artifact_digest == right.assignment_artifact_digest
    assert left.assignment_behavior_digest == right.assignment_behavior_digest
    assert "recipient_ref" not in choice_to_dict(left)
    assert service.get("delivery-001").delivery_id == "delivery-001"
    assert service.get("delivery-002").delivery_id == "delivery-002"


@pytest.mark.parametrize(
    "field_name",
    ["assignment_artifact_digest", "assignment_behavior_digest"],
)
def test_a_tampered_stored_digest_fails_before_any_choice_write(
    assignment: LessonAssignmentV1, field_name: str
) -> None:
    envelope = deliver(assignment)
    service, inbox, repository = holding(envelope)
    inbox.repository._deliveries[envelope.delivery_id] = replace(
        envelope, **{field_name: OTHER_DIGEST}
    )

    with pytest.raises(DeliveryIntegrityError):
        service.choose(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert repository.writes == 0
    assert repository.get(envelope.delivery_id) is None


@pytest.mark.parametrize(
    ("artifact", "behavior"),
    [
        (OTHER_DIGEST, None),
        (None, OTHER_DIGEST),
    ],
)
def test_a_stale_expected_digest_does_not_write(
    assignment: LessonAssignmentV1, artifact: str | None, behavior: str | None
) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)

    with pytest.raises(StalePreviewError):
        service.choose(
            envelope.delivery_id,
            artifact or envelope.assignment_artifact_digest,
            behavior or envelope.assignment_behavior_digest,
        )
    assert repository.writes == 0
    assert repository.get(envelope.delivery_id) is None


def test_an_unresolvable_assignment_stores_no_choice(assignment: LessonAssignmentV1) -> None:
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
    service, _inbox, repository = holding(envelope)

    with pytest.raises(UnresolvableAssignmentError):
        service.choose(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert repository.writes == 0


def test_an_unknown_delivery_stores_no_choice(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)

    with pytest.raises(LessonDeliveryNotFoundError):
        service.choose(
            "missing",
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert repository.writes == 0


def test_reading_an_unchosen_delivery_names_the_missing_choice(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)

    with pytest.raises(UnknownPracticeChoiceError) as caught:
        service.get(envelope.delivery_id)
    assert str(caught.value) == "unknown practice choice for delivery_id 'delivery-001'"
    assert repository.writes == 0


def test_a_different_pinned_choice_conflicts_and_keeps_the_original(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)
    planted = LocalPracticeChoiceV1(
        schema_id=LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
        schema_version=LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
        choice_status=CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
        delivery_id=envelope.delivery_id,
        assignment_id="other-assignment",
        content_id="other-content",
        assignment_artifact_digest=OTHER_DIGEST,
        assignment_behavior_digest=OTHER_DIGEST,
    )
    assert repository.put_if_absent(planted) is True

    with pytest.raises(ChoiceConflictError):
        service.choose(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    assert repository.get(envelope.delivery_id) is planted


def test_get_fails_closed_when_the_delivery_changes_after_the_choice(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, inbox, repository = holding(envelope)
    choice, _created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    rerouted = envelope_for(
        replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b")),
        delivery_id=envelope.delivery_id,
        sender_ref=envelope.sender_ref,
        recipient_ref=envelope.recipient_ref,
    )
    inbox.repository._deliveries[envelope.delivery_id] = rerouted

    with pytest.raises(StalePreviewError):
        service.get(envelope.delivery_id)
    assert repository.get(envelope.delivery_id) is choice


def test_get_fails_closed_when_the_delivery_is_removed_or_unresolvable(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, inbox, repository = holding(envelope)
    choice, _created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
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
        sender_ref=envelope.sender_ref,
        recipient_ref=envelope.recipient_ref,
    )
    inbox.repository._deliveries[envelope.delivery_id] = broken
    with pytest.raises(UnresolvableAssignmentError):
        service.get(envelope.delivery_id)
    assert repository.get(envelope.delivery_id) is choice

    del inbox.repository._deliveries[envelope.delivery_id]
    with pytest.raises(LessonDeliveryNotFoundError):
        service.get(envelope.delivery_id)
    assert repository.get(envelope.delivery_id) is choice


def test_get_fails_closed_when_a_stored_digest_stops_verifying(
    assignment: LessonAssignmentV1,
) -> None:
    envelope = deliver(assignment)
    service, inbox, repository = holding(envelope)
    choice, _created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    inbox.repository._deliveries[envelope.delivery_id] = replace(
        envelope, assignment_artifact_digest=OTHER_DIGEST
    )

    with pytest.raises(DeliveryIntegrityError):
        service.get(envelope.delivery_id)
    assert repository.get(envelope.delivery_id) is choice


def test_choice_does_not_import_activation_or_reparse_the_lesson() -> None:
    for path in (CHOICE_SOURCE, REPOSITORY_SOURCE):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        forbidden = [name for name in imported if name in FORBIDDEN_IMPORTS]
        assert forbidden == []
        assert "uuid" not in source.lower()
    choice_imports = [
        node.module
        for node in ast.walk(ast.parse(CHOICE_SOURCE.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    ]
    assert "master_all_strings.education.assignment_delivery_preview" in choice_imports


def test_the_contract_rejects_a_caller_supplied_status() -> None:
    kwargs = {
        "schema_id": LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
        "schema_version": LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
        "choice_status": CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
        "delivery_id": "delivery-001",
        "assignment_id": "assignment-001",
        "content_id": "content-001",
        "assignment_artifact_digest": OTHER_DIGEST,
        "assignment_behavior_digest": OTHER_DIGEST,
    }
    with pytest.raises(EducationContractError, match="choice_status"):
        LocalPracticeChoiceV1(**{**kwargs, "choice_status": "ACCEPTED"})
    with pytest.raises(EducationContractError, match="schema_version"):
        LocalPracticeChoiceV1(**{**kwargs, "schema_version": "9.9.9"})
    with pytest.raises(EducationContractError, match="schema_id"):
        LocalPracticeChoiceV1(**{**kwargs, "schema_id": "master_all_strings.lesson_delivery"})
    with pytest.raises(EducationContractError, match="assignment_artifact_digest"):
        LocalPracticeChoiceV1(**{**kwargs, "assignment_artifact_digest": "sha256:nope"})


def test_the_closed_schema_accepts_a_choice_and_rejects_drift(
    assignment: LessonAssignmentV1,
) -> None:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError

    schema_path = (
        REPO_ROOT / "resources" / "education" / "schema" / "local_practice_choice_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    envelope = deliver(assignment)
    service, _inbox, _repository = holding(envelope)
    choice, _created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    document = choice_to_dict(choice)
    validator.validate(document)
    assert schema["additionalProperties"] is False
    assert "assignment" not in schema["properties"]

    extra = dict(document)
    extra["accepted"] = True
    with pytest.raises(ValidationError):
        validator.validate(extra)

    missing = dict(document)
    del missing["assignment_behavior_digest"]
    with pytest.raises(ValidationError):
        validator.validate(missing)

    wrong_version = dict(document)
    wrong_version["schema_version"] = "2.0.0"
    with pytest.raises(ValidationError):
        validator.validate(wrong_version)

    false_status = dict(document)
    false_status["choice_status"] = "ACCEPTED"
    with pytest.raises(ValidationError):
        validator.validate(false_status)

    bad_digest = dict(document)
    bad_digest["assignment_artifact_digest"] = "sha256:NOPE"
    with pytest.raises(ValidationError):
        validator.validate(bad_digest)


def test_put_if_absent_does_not_replace(assignment: LessonAssignmentV1) -> None:
    envelope = deliver(assignment)
    service, _inbox, repository = holding(envelope)
    choice, created = service.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    assert created is True
    other = replace(choice, assignment_id="other-assignment")
    assert repository.put_if_absent(other) is False
    assert repository.get(envelope.delivery_id) is choice
