"""A local decision to practice one received delivery.

The choice says this device will use that delivery for later practice. It does
not say a student accepted the lesson, and it does not start playback,
evaluation, or a guided session. Addressing on the delivery is not consulted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from master_all_strings.education.assignment_delivery import require_digest
from master_all_strings.education.assignment_delivery_preview import (
    LessonDeliveryPreviewService,
    LessonDeliveryPreviewV1,
)
from master_all_strings.education.errors import EducationContractError, require_schema_version
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
    LocalPracticeChoiceRepository,
)

__all__ = [
    "CHOICE_STATUS_CHOSEN_FOR_PRACTICE",
    "LOCAL_PRACTICE_CHOICE_SCHEMA_ID",
    "LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION",
    "ChoiceConflictError",
    "LocalPracticeChoiceService",
    "LocalPracticeChoiceV1",
    "StalePreviewError",
    "UnknownPracticeChoiceError",
    "choice_to_dict",
]

LOCAL_PRACTICE_CHOICE_SCHEMA_ID = "master_all_strings.local_practice_choice"
LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION = "1.0.0"
CHOICE_STATUS_CHOSEN_FOR_PRACTICE = "CHOSEN_FOR_PRACTICE"


class UnknownPracticeChoiceError(EducationContractError):
    """No choice is stored for this delivery."""


class StalePreviewError(EducationContractError):
    """The digests in hand are not the ones declared on the delivery."""


class ChoiceConflictError(EducationContractError):
    """A different choice is already stored for this delivery."""


@dataclass(frozen=True)
class LocalPracticeChoiceV1:
    """One device's choice of one received delivery.

    The status is fixed. A caller cannot store acceptance or completion here.
    The digests are the ones the envelope declared when the choice was made.
    """

    schema_id: str
    schema_version: str
    choice_status: str
    delivery_id: str
    assignment_id: str
    content_id: str
    assignment_artifact_digest: str
    assignment_behavior_digest: str

    def __post_init__(self) -> None:
        if self.schema_id != LOCAL_PRACTICE_CHOICE_SCHEMA_ID:
            raise EducationContractError(
                f"schema_id must be {LOCAL_PRACTICE_CHOICE_SCHEMA_ID!r}, got {self.schema_id!r}"
            )
        require_schema_version(self.schema_version, LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION)
        if self.choice_status != CHOICE_STATUS_CHOSEN_FOR_PRACTICE:
            raise EducationContractError(
                "choice_status must be 'CHOSEN_FOR_PRACTICE', "
                f"got {self.choice_status!r}"
            )
        if not isinstance(self.delivery_id, str) or not self.delivery_id.strip():
            raise EducationContractError("delivery_id must be a nonblank string")
        if not isinstance(self.assignment_id, str) or not self.assignment_id.strip():
            raise EducationContractError("assignment_id must be a nonblank string")
        if not isinstance(self.content_id, str) or not self.content_id.strip():
            raise EducationContractError("content_id must be a nonblank string")
        require_digest(self.assignment_artifact_digest, "assignment_artifact_digest")
        require_digest(self.assignment_behavior_digest, "assignment_behavior_digest")


def choice_to_dict(choice: LocalPracticeChoiceV1) -> dict[str, object]:
    """Plain data for the closed HTTP document.

    The pinned digests are copied off the choice. Nothing here recomputes them
    or reads the delivery again.
    """

    return {
        "schema_id": choice.schema_id,
        "schema_version": choice.schema_version,
        "choice_status": choice.choice_status,
        "delivery_id": choice.delivery_id,
        "assignment_id": choice.assignment_id,
        "content_id": choice.content_id,
        "assignment_artifact_digest": choice.assignment_artifact_digest,
        "assignment_behavior_digest": choice.assignment_behavior_digest,
    }


def _pins_match(stored: LocalPracticeChoiceV1, fresh: LocalPracticeChoiceV1) -> bool:
    return (
        stored.delivery_id == fresh.delivery_id
        and stored.assignment_id == fresh.assignment_id
        and stored.content_id == fresh.content_id
        and stored.assignment_artifact_digest == fresh.assignment_artifact_digest
        and stored.assignment_behavior_digest == fresh.assignment_behavior_digest
    )


def _choice_from_preview(preview: LessonDeliveryPreviewV1) -> LocalPracticeChoiceV1:
    return LocalPracticeChoiceV1(
        schema_id=LOCAL_PRACTICE_CHOICE_SCHEMA_ID,
        schema_version=LOCAL_PRACTICE_CHOICE_SCHEMA_VERSION,
        choice_status=CHOICE_STATUS_CHOSEN_FOR_PRACTICE,
        delivery_id=preview.delivery_id,
        assignment_id=preview.assignment_id,
        content_id=preview.content_id,
        assignment_artifact_digest=preview.assignment_artifact_digest,
        assignment_behavior_digest=preview.assignment_behavior_digest,
    )


@dataclass
class LocalPracticeChoiceService:
    """Record and read a local practice choice.

    ``choose`` previews first, compares the expected digests with the declared
    ones, and only then inserts. A stale request never reaches the repository.
    ``get`` previews again and returns the stored choice only when that preview
    still matches the pins. Neither method deletes or rewrites a choice, and
    neither writes a delivery.
    """

    previews: LessonDeliveryPreviewService
    repository: LocalPracticeChoiceRepository = field(
        default_factory=InMemoryLocalPracticeChoiceRepository
    )

    def choose(
        self,
        delivery_id: str,
        expected_assignment_artifact_digest: str,
        expected_assignment_behavior_digest: str,
    ) -> tuple[LocalPracticeChoiceV1, bool]:
        """Return the choice and whether this call stored it.

        The bool is True on the first insert and False when the stored choice
        already carries the same pins. A stored choice with different pins
        raises ``ChoiceConflictError`` and is left in place.
        """

        require_digest(
            expected_assignment_artifact_digest, "expected_assignment_artifact_digest"
        )
        require_digest(
            expected_assignment_behavior_digest, "expected_assignment_behavior_digest"
        )
        preview = self.previews.preview(delivery_id)
        if (
            expected_assignment_artifact_digest != preview.assignment_artifact_digest
            or expected_assignment_behavior_digest != preview.assignment_behavior_digest
        ):
            raise StalePreviewError("stale_preview")
        choice = _choice_from_preview(preview)
        if self.repository.put_if_absent(choice):
            return choice, True
        existing = self.repository.get(delivery_id)
        if existing is not None and _pins_match(existing, choice):
            return existing, False
        raise ChoiceConflictError("choice_conflict")

    def get(self, delivery_id: str) -> LocalPracticeChoiceV1:
        """Return the stored choice when the delivery still supports it.

        The stored record is not modified. A missing choice, a missing
        delivery, a failed digest, a pin mismatch, and an assignment that no
        longer resolves are all raised and leave the repository as it was.
        """

        stored = self.repository.get(delivery_id)
        if stored is None:
            raise UnknownPracticeChoiceError(
                f"unknown practice choice for delivery_id {delivery_id!r}"
            )
        fresh = _choice_from_preview(self.previews.preview(delivery_id))
        if not _pins_match(stored, fresh):
            raise StalePreviewError("stale_preview")
        return stored
