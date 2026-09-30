"""Prepare one chosen delivery for a later local practice screen.

Choosing a delivery records that this device will use it. Preparing it asks
the existing lesson pipeline for the projection, playback plan, practice
policy, and score that a practice screen will read. It does not play the
lesson, open a session, or store the result.

The service lives here, under ``mvp/``, because it composes product
artifacts. Education keeps the choice and the delivery and does not import
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from master_all_strings.education.assignment_delivery import (
    LessonDeliveryEnvelopeV1,
    validate_delivery_integrity,
)
from master_all_strings.education.assignment_delivery_preview import DeliveryIntegrityError
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.local_practice_choice import (
    LocalPracticeChoiceService,
    LocalPracticeChoiceV1,
    StalePreviewError,
)
from master_all_strings.lesson.serialization import to_dict
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import LessonLoadError, UnknownInstrumentError
from master_all_strings.mvp.models import MvpProjectionResponseV1
from master_all_strings.mvp.web_export import (
    playback_export_payload,
    practice_export_payload,
    projection_export_payload,
    score_export_payload,
)

__all__ = [
    "LOCAL_PRACTICE_PREPARATION_SCHEMA_ID",
    "LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION",
    "PREPARATION_STATUS_PREPARED",
    "LocalPracticePreparationService",
    "LocalPracticePreparationV1",
    "PreparationFailure",
    "UnpreparableAssignmentError",
    "UnsupportedInstrumentError",
    "preparation_to_dict",
    "shared_application",
]

LOCAL_PRACTICE_PREPARATION_SCHEMA_ID = "master_all_strings.local_practice_preparation"
LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION = "1.0.0"
PREPARATION_STATUS_PREPARED = "PREPARED"


class UnsupportedInstrumentError(Exception):
    """The assignment's declared instrument profile is not available."""


class UnpreparableAssignmentError(Exception):
    """The assignment resolved for preview and then failed a known check."""


class PreparationFailure(Exception):
    """The pipeline, the serializer, or the bundle itself did not hold together.

    The message is for logs. An HTTP caller receives a fixed sentence instead,
    because this failure is ours and its text is not a contract.
    """


@dataclass(frozen=True)
class LocalPracticePreparationV1:
    """One prepared bundle. Nothing here is stored."""

    schema_id: str
    schema_version: str
    preparation_status: str
    delivery_id: str
    assignment_id: str
    content_id: str
    assignment_artifact_digest: str
    assignment_behavior_digest: str
    projection: dict[str, Any]
    playback: dict[str, Any]
    practice: dict[str, Any]
    score: dict[str, Any]

    def __post_init__(self) -> None:
        if self.schema_id != LOCAL_PRACTICE_PREPARATION_SCHEMA_ID:
            raise PreparationFailure("preparation schema_id is not the closed contract")
        if self.schema_version != LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION:
            raise PreparationFailure("preparation schema_version is not the closed contract")
        if self.preparation_status != PREPARATION_STATUS_PREPARED:
            raise PreparationFailure("preparation_status is not PREPARED")
        for name, value in (
            ("delivery_id", self.delivery_id),
            ("assignment_id", self.assignment_id),
            ("content_id", self.content_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise PreparationFailure(f"{name} must be a nonblank string")
        if set(self.score) != {"canonical_revision", "tab", "notation"}:
            raise PreparationFailure("score must contain exactly the three artifacts")


def preparation_to_dict(preparation: LocalPracticePreparationV1) -> dict[str, Any]:
    """The closed JSON document. Nested artifacts are already encoded."""

    return {
        "schema_id": preparation.schema_id,
        "schema_version": preparation.schema_version,
        "preparation_status": preparation.preparation_status,
        "delivery_id": preparation.delivery_id,
        "assignment_id": preparation.assignment_id,
        "content_id": preparation.content_id,
        "assignment_artifact_digest": preparation.assignment_artifact_digest,
        "assignment_behavior_digest": preparation.assignment_behavior_digest,
        "projection": preparation.projection,
        "playback": preparation.playback,
        "practice": preparation.practice,
        "score": preparation.score,
    }


def _pins_match(envelope: LessonDeliveryEnvelopeV1, choice: LocalPracticeChoiceV1) -> bool:
    """Exact equality of the identities and the declared pins.

    The declared pins are compared, not recomputed. Integrity was already
    rechecked on this envelope; recomputing them again here would blur a
    corrupt record into a stale one.
    """

    return (
        envelope.delivery_id == choice.delivery_id
        and envelope.assignment_id == choice.assignment_id
        and envelope.content_id == choice.content_id
        and envelope.assignment_artifact_digest == choice.assignment_artifact_digest
        and envelope.assignment_behavior_digest == choice.assignment_behavior_digest
    )


def _strings(items: list[Any], key: str) -> list[str]:
    found: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise PreparationFailure("event row is not an object")
        value = item.get(key)
        if not isinstance(value, str):
            raise PreparationFailure("event id is not a string")
        found.append(value)
    return found


def _same_ids(expected: list[str], actual: list[str], label: str) -> None:
    """The same event ids, whatever order the artifact stores them in.

    Length is part of the check so a duplicated row cannot hide a missing
    one. It is not a demand that each onset have one row: simultaneous notes
    are distinct events, and a rest is not an event.
    """

    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise PreparationFailure(f"{label} event references do not match the assignment")


def _notation_note_ids(notation: dict[str, Any]) -> list[str]:
    payload = notation.get("payload")
    if not isinstance(payload, dict):
        raise PreparationFailure("notation payload is missing")
    measures = payload.get("measures")
    if not isinstance(measures, list):
        raise PreparationFailure("notation measures are missing")
    note_ids: list[str] = []
    for measure in measures:
        if not isinstance(measure, dict):
            raise PreparationFailure("notation measure is not an object")
        events = measure.get("events")
        if not isinstance(events, list):
            raise PreparationFailure("notation measure events are missing")
        for event in events:
            if not isinstance(event, dict):
                raise PreparationFailure("notation event is not an object")
            cited = event.get("canonical_event_id")
            if cited is None:
                # A rest is derived. It has no canonical event, and a note
                # that lost its citation is not a rest.
                if event.get("event_kind") != "rest":
                    raise PreparationFailure(
                        "notation event without a canonical id is not a rest"
                    )
                continue
            if not isinstance(cited, str):
                raise PreparationFailure("notation canonical_event_id must be a string")
            note_ids.append(cited)
    return note_ids


def _cited_revision(artifact: dict[str, Any], revision_id: str, label: str) -> None:
    payload = artifact.get("payload")
    if not isinstance(payload, dict):
        raise PreparationFailure(f"{label} payload is missing")
    if artifact.get("canonical_revision_id") != revision_id:
        raise PreparationFailure(f"{label} does not cite the exported revision")
    if payload.get("canonical_revision_id") != revision_id:
        raise PreparationFailure(f"{label} payload does not cite the exported revision")


def _check_bundle(
    envelope: LessonDeliveryEnvelopeV1,
    response: MvpProjectionResponseV1,
    projection: dict[str, Any],
    playback: dict[str, Any],
    practice: dict[str, Any],
    score: dict[str, Any],
) -> None:
    declared = envelope.assignment.spatial_guidance.instrument_profile_id
    if response.behavior_digest != envelope.assignment_behavior_digest:
        raise PreparationFailure("prepared behavior digest does not match the declared pin")
    if projection.get("behavior_digest") != envelope.assignment_behavior_digest:
        raise PreparationFailure("projection behavior digest does not match the declared pin")
    if response.instrument_id != declared or projection.get("instrument_id") != declared:
        raise PreparationFailure("prepared instrument does not match the declared profile")
    inner = projection.get("projection")
    if not isinstance(inner, dict):
        raise PreparationFailure("projection payload is missing")
    instrument = inner.get("instrument")
    if not isinstance(instrument, dict) or instrument.get("instrument_id") != declared:
        raise PreparationFailure("projection instrument does not match the declared profile")

    assignment_id = envelope.assignment_id
    content_id = envelope.content_id
    if inner.get("assignment_id") != assignment_id or inner.get("content_id") != content_id:
        raise PreparationFailure("projection identity does not match the delivery")
    if (
        playback.get("assignment_id") != assignment_id
        or playback.get("content_id") != content_id
    ):
        raise PreparationFailure("playback identity does not match the delivery")
    policy = practice.get("policy")
    if not isinstance(policy, dict):
        raise PreparationFailure("practice policy is missing")
    if policy.get("assignment_id") != assignment_id or policy.get("content_id") != content_id:
        raise PreparationFailure("practice identity does not match the delivery")

    revision = score.get("canonical_revision")
    tab = score.get("tab")
    notation = score.get("notation")
    if (
        not isinstance(revision, dict)
        or not isinstance(tab, dict)
        or not isinstance(notation, dict)
    ):
        raise PreparationFailure("score artifacts are incomplete")
    revision_id = revision.get("revision_id")
    if not isinstance(revision_id, str) or not revision_id:
        raise PreparationFailure("canonical revision has no revision_id")
    _cited_revision(tab, revision_id, "tab")
    _cited_revision(notation, revision_id, "notation")

    assignment_ids = [event.event_id for event in envelope.assignment.musical_content.events]
    notes = inner.get("notes")
    playback_events = playback.get("events")
    revision_events = revision.get("events")
    tab_payload = tab.get("payload")
    tab_events = tab_payload.get("events") if isinstance(tab_payload, dict) else None
    if not isinstance(notes, list) or not isinstance(playback_events, list):
        raise PreparationFailure("projection or playback events are missing")
    if not isinstance(revision_events, list) or not isinstance(tab_events, list):
        raise PreparationFailure("score events are missing")
    _same_ids(assignment_ids, _strings(notes, "event_id"), "projection")
    _same_ids(assignment_ids, _strings(playback_events, "event_id"), "playback")
    _same_ids(assignment_ids, _strings(revision_events, "event_id"), "revision")
    _same_ids(assignment_ids, _strings(tab_events, "canonical_event_id"), "tab")
    _same_ids(assignment_ids, _notation_note_ids(notation), "notation")


def _bundle(
    envelope: LessonDeliveryEnvelopeV1,
    response: MvpProjectionResponseV1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    projection = projection_export_payload(response, demo_id=None)
    playback = playback_export_payload(response)
    practice = practice_export_payload(response)
    score = score_export_payload(response)
    if score is None:
        raise PreparationFailure("preparation produced no score bundle")
    _check_bundle(envelope, response, projection, playback, practice, score)
    return projection, playback, practice, score


_shared_application: MvpApplication | None = None


def shared_application() -> MvpApplication:
    """The process-wide instrument catalog. Preparations themselves are not cached."""

    global _shared_application
    if _shared_application is None:
        _shared_application = MvpApplication()
    return _shared_application


@dataclass
class LocalPracticePreparationService:
    """Turn one verified choice into a practice bundle.

    ``get`` on the choice service previews again. The envelope is then read
    once more and held: a delivery that changes between those two reads is a
    different delivery, and the builders do not go back for a third copy.
    """

    deliveries: LessonDeliveryService
    choices: LocalPracticeChoiceService
    application: MvpApplication

    def prepare(
        self,
        delivery_id: str,
        expected_assignment_artifact_digest: str,
        expected_assignment_behavior_digest: str,
    ) -> LocalPracticePreparationV1:
        choice = self.choices.get(delivery_id)
        if (
            expected_assignment_artifact_digest != choice.assignment_artifact_digest
            or expected_assignment_behavior_digest != choice.assignment_behavior_digest
        ):
            raise StalePreviewError("stale_preview")
        envelope = self.deliveries.get(delivery_id)
        try:
            validate_delivery_integrity(envelope)
        except EducationContractError as exc:
            raise DeliveryIntegrityError(str(exc)) from exc
        if not _pins_match(envelope, choice):
            raise StalePreviewError("stale_preview")
        try:
            # No instrument override. The assignment declares the profile.
            response = self.application.run_assignment_json(to_dict(envelope.assignment))
        except UnknownInstrumentError as exc:
            raise UnsupportedInstrumentError("unsupported_instrument") from exc
        except LessonLoadError as exc:
            raise UnpreparableAssignmentError("unpreparable_assignment") from exc
        except Exception as exc:
            raise PreparationFailure("preparation failed") from exc
        try:
            projection, playback, practice, score = _bundle(envelope, response)
        except PreparationFailure:
            raise
        except Exception as exc:
            raise PreparationFailure("preparation failed") from exc
        return LocalPracticePreparationV1(
            schema_id=LOCAL_PRACTICE_PREPARATION_SCHEMA_ID,
            schema_version=LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION,
            preparation_status=PREPARATION_STATUS_PREPARED,
            delivery_id=choice.delivery_id,
            assignment_id=choice.assignment_id,
            content_id=choice.content_id,
            assignment_artifact_digest=choice.assignment_artifact_digest,
            assignment_behavior_digest=choice.assignment_behavior_digest,
            projection=projection,
            playback=playback,
            practice=practice,
            score=score,
        )
