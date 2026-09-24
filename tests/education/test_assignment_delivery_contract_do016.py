"""The delivery envelope's own rules, before anything is stored or sent.

The envelope exists so that addressing a lesson never edits it. These tests
hold that line from two directions: what the contract refuses to be built from,
and what it refuses to leave unchecked once built.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.education.assignment_delivery import (
    LESSON_DELIVERY_SCHEMA_ID,
    LESSON_DELIVERY_SCHEMA_VERSION,
    LessonDeliveryEnvelopeV1,
    LessonDeliverySummaryV1,
    validate_delivery_integrity,
)
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.errors import EducationContractError
from master_all_strings.lesson.models import LessonAssignmentV1, LessonRoutingV1
from master_all_strings.lesson.serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


@pytest.fixture
def envelope(assignment: LessonAssignmentV1) -> LessonDeliveryEnvelopeV1:
    return envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )


# --- A. what a valid envelope is ----------------------------------------------


def test_a_minimal_envelope_addresses_an_assignment(
    envelope: LessonDeliveryEnvelopeV1, assignment: LessonAssignmentV1
) -> None:
    assert envelope.schema_id == LESSON_DELIVERY_SCHEMA_ID
    assert envelope.schema_version == LESSON_DELIVERY_SCHEMA_VERSION
    assert envelope.assignment == assignment
    assert envelope.classroom_ref is None
    validate_delivery_integrity(envelope)


def test_the_envelope_mirrors_the_assignments_identity(
    envelope: LessonDeliveryEnvelopeV1, assignment: LessonAssignmentV1
) -> None:
    assert envelope.assignment_id == assignment.assignment_id
    assert envelope.content_id == assignment.content_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("delivery_id", ""),
        ("delivery_id", "   "),
        ("delivery_id", " delivery-001"),
        ("sender_ref", ""),
        ("recipient_ref", ""),
        ("classroom_ref", ""),
        ("assignment_artifact_digest", ""),
        ("assignment_behavior_digest", ""),
    ],
)
def test_an_empty_or_padded_reference_is_refused(
    envelope: LessonDeliveryEnvelopeV1, field: str, value: str
) -> None:
    with pytest.raises(EducationContractError, match=field):
        replace(envelope, **{field: value})


def test_a_null_classroom_is_allowed(envelope: LessonDeliveryEnvelopeV1) -> None:
    assert replace(envelope, classroom_ref=None).classroom_ref is None
    assert replace(envelope, classroom_ref="class-7b").classroom_ref == "class-7b"


def test_an_unknown_schema_id_is_refused_before_anything_else(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    with pytest.raises(EducationContractError, match="schema_id"):
        replace(envelope, schema_id="master_all_strings.something_else")


def test_an_unknown_schema_version_is_refused(envelope: LessonDeliveryEnvelopeV1) -> None:
    with pytest.raises(EducationContractError, match="schema_version"):
        replace(envelope, schema_version="2.0.0")


def test_the_assignment_must_be_a_lesson_assignment(envelope: LessonDeliveryEnvelopeV1) -> None:
    with pytest.raises(EducationContractError, match="assignment"):
        replace(envelope, assignment={"schema_id": "master_all_strings.lesson_assignment"})


# --- the digest format, shared with the schema ---------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "sha256:XYZ" + "a" * 61,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "sha256:",
        "sha1:" + "a" * 64,
        "a" * 64,
        " sha256:" + "a" * 64,
    ],
)
def test_a_value_the_schema_calls_invalid_cannot_be_constructed(
    envelope: LessonDeliveryEnvelopeV1, value: str
) -> None:
    # A public dataclass accepting what its own schema rejects is a contract
    # disagreeing with itself, and the disagreement surfaces at whichever
    # boundary checks second -- here, only once a digest failed to recompute.
    with pytest.raises(EducationContractError, match="assignment_artifact_digest"):
        replace(envelope, assignment_artifact_digest=value)
    with pytest.raises(EducationContractError, match="assignment_behavior_digest"):
        replace(envelope, assignment_behavior_digest=value)


def test_a_well_formed_digest_is_accepted(envelope: LessonDeliveryEnvelopeV1) -> None:
    # Well formed, and wrong for this assignment: the format check and the
    # recompute check answer different questions, and both still run.
    other = "sha256:" + "0" * 64
    rebuilt = replace(envelope, assignment_artifact_digest=other)
    assert rebuilt.assignment_artifact_digest == other
    with pytest.raises(EducationContractError, match="does not match"):
        validate_delivery_integrity(rebuilt)


def test_the_contract_and_the_schema_use_one_pattern() -> None:
    # Written once in the code, asserted equal to the schema here, so the two
    # cannot drift into disagreeing again.
    import json

    schema = json.loads(
        (
            REPO_ROOT
            / "resources"
            / "education"
            / "schema"
            / "lesson_delivery_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    from master_all_strings.education.assignment_delivery import _DIGEST

    assert schema["$defs"]["digest"]["pattern"] == _DIGEST.pattern


# --- B. the two digests are evidence, not decoration ---------------------------


def test_correct_digests_pass(envelope: LessonDeliveryEnvelopeV1) -> None:
    assert validate_delivery_integrity(envelope) is None


def test_a_wrong_artifact_digest_is_refused(envelope: LessonDeliveryEnvelopeV1) -> None:
    wrong = replace(envelope, assignment_artifact_digest="sha256:" + "0" * 64)
    with pytest.raises(EducationContractError, match="assignment_artifact_digest"):
        validate_delivery_integrity(wrong)


def test_a_wrong_behavior_digest_is_refused(envelope: LessonDeliveryEnvelopeV1) -> None:
    wrong = replace(envelope, assignment_behavior_digest="sha256:" + "0" * 64)
    with pytest.raises(EducationContractError, match="assignment_behavior_digest"):
        validate_delivery_integrity(wrong)


def test_an_assignment_swapped_after_the_digests_were_taken_is_refused(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    # The digests travel with the envelope; the assignment is what arrived.
    # Recomputing is the only thing that ties one to the other.
    other = deserialize_lesson_assignment((EXAMPLES / "local_midi_loop.json").read_text("utf-8"))
    with pytest.raises(EducationContractError, match="assignment_artifact_digest"):
        validate_delivery_integrity(replace(envelope, assignment=other))


def test_routing_changes_the_artifact_digest_and_not_the_behavior_digest(
    assignment: LessonAssignmentV1,
) -> None:
    # The premise the two digests rest on, asserted rather than assumed: this
    # is what lets delivery say "the artifact differs" and "the lesson does
    # not" as two separate facts.
    rerouted = replace(assignment, routing=LessonRoutingV1(classroom_id="class-7b"))
    assert compute_assignment_artifact_digest(rerouted) != compute_assignment_artifact_digest(
        assignment
    )
    assert compute_lesson_behavior_digest(rerouted) == compute_lesson_behavior_digest(assignment)


# --- C. delivery metadata is not lesson content --------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("delivery_id", "delivery-002"),
        ("sender_ref", "teacher-chen"),
        ("recipient_ref", "student-dee"),
        ("classroom_ref", "class-9a"),
    ],
)
def test_changing_where_a_lesson_goes_does_not_change_the_lesson(
    envelope: LessonDeliveryEnvelopeV1, field: str, value: str
) -> None:
    redirected = replace(envelope, **{field: value})
    assert redirected.assignment == envelope.assignment
    assert redirected.assignment_artifact_digest == envelope.assignment_artifact_digest
    assert redirected.assignment_behavior_digest == envelope.assignment_behavior_digest
    validate_delivery_integrity(redirected)


def test_an_assignments_own_routing_survives_delivery_untouched() -> None:
    # LessonRoutingV1 is inert metadata inside the assignment. Delivery neither
    # obeys it nor rewrites it to agree with the envelope.
    routed = deserialize_lesson_assignment((EXAMPLES / "routing_populated.json").read_text("utf-8"))
    assert routed.routing is not None
    envelope = envelope_for(
        routed,
        delivery_id="delivery-003",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
        classroom_ref="class-7b",
    )
    validate_delivery_integrity(envelope)
    assert envelope.assignment.routing == routed.routing
    assert envelope.recipient_ref != (routed.routing.recipient_device_id or "")


# --- D. summaries carry addressing, not lessons --------------------------------


def test_a_summary_names_the_assignment_without_carrying_it(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    summary = LessonDeliverySummaryV1.of(envelope)
    assert summary.delivery_id == envelope.delivery_id
    assert summary.assignment_id == envelope.assignment_id
    assert summary.content_id == envelope.content_id
    assert summary.assignment_artifact_digest == envelope.assignment_artifact_digest
    # Listing an inbox must not be a way to transfer every lesson in it.
    assert not hasattr(summary, "assignment")
