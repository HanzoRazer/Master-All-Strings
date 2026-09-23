"""The inbox: what it stores, what it refuses, and what it leaves alone.

The service is the only place that decides whether a delivery may be kept, so
these tests are about the decisions rather than the storage. The one that
matters most is the negative case: a refused delivery must leave the inbox
byte-identical to what it was, because a half-received lesson is worse than a
rejected one.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1
from master_all_strings.education.assignment_delivery_repository import (
    InMemoryLessonDeliveryRepository,
)
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import (
    DuplicateDeliveryError,
    LessonDeliveryNotFoundError,
    LessonDeliveryService,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def other_assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_loop.json").read_text("utf-8"))


def delivery(
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


@pytest.fixture
def service() -> LessonDeliveryService:
    return LessonDeliveryService()


def test_a_delivery_is_received_and_recovered(
    service: LessonDeliveryService, assignment: LessonAssignmentV1
) -> None:
    envelope = delivery(assignment)
    assert service.receive(envelope) == envelope
    assert service.get("delivery-001") == envelope
    assert service.get("delivery-001").assignment == assignment


def test_an_unknown_delivery_is_not_found(service: LessonDeliveryService) -> None:
    with pytest.raises(LessonDeliveryNotFoundError, match="delivery-404"):
        service.get("delivery-404")


def test_listing_is_ordered_by_delivery_id_not_arrival(
    service: LessonDeliveryService, assignment: LessonAssignmentV1
) -> None:
    for delivery_id in ("delivery-003", "delivery-001", "delivery-002"):
        service.receive(delivery(assignment, delivery_id))
    assert [item.delivery_id for item in service.list()] == [
        "delivery-001",
        "delivery-002",
        "delivery-003",
    ]


def test_listing_filters_by_recipient(
    service: LessonDeliveryService, assignment: LessonAssignmentV1
) -> None:
    service.receive(delivery(assignment, "delivery-001", recipient_ref="student-bo"))
    service.receive(delivery(assignment, "delivery-002", recipient_ref="student-dee"))
    service.receive(delivery(assignment, "delivery-003", recipient_ref="student-bo"))
    listed = service.list(recipient_ref="student-bo")
    assert [item.delivery_id for item in listed] == ["delivery-001", "delivery-003"]
    assert {item.recipient_ref for item in listed} == {"student-bo"}


def test_listing_carries_summaries_not_lessons(
    service: LessonDeliveryService, assignment: LessonAssignmentV1
) -> None:
    service.receive(delivery(assignment))
    (summary,) = service.list()
    assert summary.assignment_id == assignment.assignment_id
    assert summary.content_id == assignment.content_id
    assert not hasattr(summary, "assignment")


def test_one_lesson_may_be_delivered_to_several_students(
    service: LessonDeliveryService, assignment: LessonAssignmentV1
) -> None:
    # The reason addressing lives outside the assignment: two students, one
    # identical artifact, two deliveries.
    first = service.receive(delivery(assignment, "delivery-001", recipient_ref="student-bo"))
    second = service.receive(delivery(assignment, "delivery-002", recipient_ref="student-dee"))
    assert first.assignment == second.assignment
    assert first.assignment_artifact_digest == second.assignment_artifact_digest
    assert first.assignment_behavior_digest == second.assignment_behavior_digest
    assert first.recipient_ref != second.recipient_ref


def test_a_repeated_delivery_id_is_a_conflict(
    service: LessonDeliveryService,
    assignment: LessonAssignmentV1,
    other_assignment: LessonAssignmentV1,
) -> None:
    # Not treated as a retry: idempotent resend is a property of whatever
    # protocol carries deliveries, and inventing it here would let a second
    # lesson quietly replace the first under one identity.
    service.receive(delivery(assignment))
    with pytest.raises(DuplicateDeliveryError, match="delivery-001"):
        service.receive(delivery(other_assignment, "delivery-001"))
    assert service.get("delivery-001").assignment == assignment


@pytest.mark.parametrize(
    "field", ["assignment_artifact_digest", "assignment_behavior_digest"]
)
def test_a_delivery_whose_digests_do_not_recompute_is_refused(
    service: LessonDeliveryService, assignment: LessonAssignmentV1, field: str
) -> None:
    tampered = replace(delivery(assignment), **{field: "sha256:" + "0" * 64})
    with pytest.raises(EducationContractError, match=field):
        service.receive(tampered)


def test_a_refused_delivery_leaves_the_inbox_untouched(
    service: LessonDeliveryService,
    assignment: LessonAssignmentV1,
    other_assignment: LessonAssignmentV1,
) -> None:
    service.receive(delivery(assignment, "delivery-001"))
    before = service.list()

    swapped = replace(delivery(assignment, "delivery-002"), assignment=other_assignment)
    with pytest.raises(EducationContractError):
        service.receive(swapped)
    with pytest.raises(DuplicateDeliveryError):
        service.receive(delivery(other_assignment, "delivery-001"))

    assert service.list() == before
    assert service.get("delivery-001").assignment == assignment
    with pytest.raises(LessonDeliveryNotFoundError):
        service.get("delivery-002")


def test_the_repository_is_replaceable(assignment: LessonAssignmentV1) -> None:
    # The service owns the rules; the repository owns storage. A durable
    # implementation arriving later must not have to re-derive the rules.
    store = InMemoryLessonDeliveryRepository()
    service = LessonDeliveryService(repository=store)
    service.receive(delivery(assignment))
    assert store.contains("delivery-001")
    assert store.get("delivery-001") is not None
    assert store.list()[0].delivery_id == "delivery-001"
    assert store.list(recipient_ref="nobody") == ()


def test_the_store_claims_an_identity_in_one_step(
    assignment: LessonAssignmentV1, other_assignment: LessonAssignmentV1
) -> None:
    # Uniqueness is decided where the write happens. Two callers cannot both
    # be told they stored a delivery, and the first one stays.
    store = InMemoryLessonDeliveryRepository()
    assert store.put_if_absent(delivery(assignment)) is True
    assert store.put_if_absent(delivery(other_assignment)) is False
    assert store.get("delivery-001").assignment == assignment


def test_the_repository_offers_no_unconditional_write() -> None:
    # A caller that could write unconditionally could also lose a race it did
    # not know it was in.
    assert not hasattr(InMemoryLessonDeliveryRepository(), "put")


def test_concurrent_receives_of_one_id_produce_one_delivery(
    assignment: LessonAssignmentV1, other_assignment: LessonAssignmentV1
) -> None:
    import threading

    service = LessonDeliveryService()
    envelopes = [delivery(assignment), delivery(other_assignment)]
    start = threading.Barrier(len(envelopes))
    outcomes: list[str] = []
    lock = threading.Lock()

    def receive(envelope: LessonDeliveryEnvelopeV1) -> None:
        start.wait(timeout=10)
        try:
            service.receive(envelope)
            with lock:
                outcomes.append("received")
        except DuplicateDeliveryError:
            with lock:
                outcomes.append("duplicate")

    threads = [threading.Thread(target=receive, args=(item,)) for item in envelopes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["duplicate", "received"]
    assert len(service.list()) == 1
