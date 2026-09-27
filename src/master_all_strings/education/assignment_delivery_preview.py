"""Read-only preview of one received lesson delivery.

Stage 1 stores an envelope and hands that envelope back. A preview is the next
question a student device is allowed to ask: given a delivery I already hold,
what lesson is inside it? The answer is a bounded summary. It is not the
student accepting the lesson, starting it, playing it, or finishing it, and
nothing in this module writes any of those facts down.

The musical reading comes from ``resolve_lesson_assignment`` and from nowhere
else. Both digests pinned on the envelope are checked again before that call.
They are the sender's claim about what was stored; recomputing them here is
what makes the claim evidence at the moment of inspection, which is a different
moment from receipt.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.education.assignment_delivery import (
    LessonDeliveryEnvelopeV1,
    require_digest,
    validate_delivery_integrity,
)
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.errors import (
    EducationContractError,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_positive_int,
    require_schema_version,
    require_unique,
)
from master_all_strings.lesson.enums import OpenStringPreference
from master_all_strings.lesson.errors import LessonAssignmentError
from master_all_strings.lesson.resolver import (
    PlaybackRequestV1,
    ResolvedLessonV1,
    SpatialSelectionRequestV1,
    resolve_lesson_assignment,
)

__all__ = [
    "LESSON_DELIVERY_PREVIEW_SCHEMA_ID",
    "LESSON_DELIVERY_PREVIEW_SCHEMA_VERSION",
    "PREVIEW_STATUS_READY",
    "DeliveryIntegrityError",
    "LessonDeliveryPreviewService",
    "LessonDeliveryPreviewV1",
    "PlaybackPolicySummaryV1",
    "SpatialPolicyIntentV1",
    "UnresolvableAssignmentError",
    "preview_to_dict",
]

LESSON_DELIVERY_PREVIEW_SCHEMA_ID = "master_all_strings.lesson_delivery_preview"
LESSON_DELIVERY_PREVIEW_SCHEMA_VERSION = "1.0.0"
PREVIEW_STATUS_READY = "READY"

_OPEN_STRING_PREFERENCES = frozenset(item.value for item in OpenStringPreference)


class DeliveryIntegrityError(EducationContractError):
    """The stored envelope's declared digests do not match its assignment."""


class UnresolvableAssignmentError(EducationContractError):
    """The carried assignment cannot be read as canonical lesson inputs."""


@dataclass(frozen=True)
class PlaybackPolicySummaryV1:
    """The resolver's playback request, flattened for a closed document.

    This is the request the resolver already built. It is not a playback plan,
    and it does not say a device can sound the lesson.
    """

    tempo_bpm: float | None
    start_tick: int | None
    end_tick: int | None
    loop_enabled: bool
    count_in_bars: int | None
    ticks_per_quarter: int
    source_tempo_bpm: float | None

    def __post_init__(self) -> None:
        _require_optional_int(self.start_tick, "start_tick")
        _require_optional_int(self.end_tick, "end_tick")
        _require_optional_int(self.count_in_bars, "count_in_bars")
        if not isinstance(self.loop_enabled, bool):
            raise EducationContractError("loop_enabled must be a boolean")
        require_positive_int(self.ticks_per_quarter, "ticks_per_quarter")
        _require_optional_bpm(self.tempo_bpm, "tempo_bpm")
        _require_optional_bpm(self.source_tempo_bpm, "source_tempo_bpm")


@dataclass(frozen=True)
class SpatialPolicyIntentV1:
    """The resolver's spatial intent. Positions are not selected here."""

    instrument_profile_id: str
    fingering_policy_id: str
    preferred_fret_min: int | None
    preferred_fret_max: int | None
    open_string_preference: str

    def __post_init__(self) -> None:
        require_identifier(self.instrument_profile_id, "instrument_profile_id")
        require_identifier(self.fingering_policy_id, "fingering_policy_id")
        _require_optional_int(self.preferred_fret_min, "preferred_fret_min")
        _require_optional_int(self.preferred_fret_max, "preferred_fret_max")
        if self.open_string_preference not in _OPEN_STRING_PREFERENCES:
            raise EducationContractError(
                "open_string_preference must be one of "
                f"{sorted(_OPEN_STRING_PREFERENCES)}, got {self.open_string_preference!r}"
            )


@dataclass(frozen=True)
class LessonDeliveryPreviewV1:
    """One inspection of one delivery. Success is only ``READY``.

    A failure is not a preview with a different status. Callers either receive
    this document or an error, never a mixture of the two.
    """

    schema_id: str
    schema_version: str
    preview_status: str
    delivery_id: str
    assignment_id: str
    content_id: str
    assignment_artifact_digest: str
    assignment_behavior_digest: str
    title: str
    canonical_event_count: int
    canonical_event_ids: tuple[str, ...]
    playback_policy: PlaybackPolicySummaryV1
    spatial_policy: SpatialPolicyIntentV1
    meter_change_count: int
    instruction_objective: str | None
    teacher_note: str | None

    def __post_init__(self) -> None:
        if self.schema_id != LESSON_DELIVERY_PREVIEW_SCHEMA_ID:
            raise EducationContractError(
                f"schema_id must be {LESSON_DELIVERY_PREVIEW_SCHEMA_ID!r}, got {self.schema_id!r}"
            )
        require_schema_version(self.schema_version, LESSON_DELIVERY_PREVIEW_SCHEMA_VERSION)
        if self.preview_status != PREVIEW_STATUS_READY:
            raise EducationContractError(
                f"preview_status must be {PREVIEW_STATUS_READY!r}, got {self.preview_status!r}"
            )
        require_identifier(self.delivery_id, "delivery_id")
        require_identifier(self.assignment_id, "assignment_id")
        require_identifier(self.content_id, "content_id")
        require_digest(self.assignment_artifact_digest, "assignment_artifact_digest")
        require_digest(self.assignment_behavior_digest, "assignment_behavior_digest")
        require_identifier(self.title, "title")
        require_positive_int(self.canonical_event_count, "canonical_event_count")
        if not isinstance(self.canonical_event_ids, tuple):
            raise EducationContractError("canonical_event_ids must be a tuple")
        if self.canonical_event_count != len(self.canonical_event_ids):
            raise EducationContractError(
                "canonical_event_count must equal the number of canonical_event_ids"
            )
        for event_id in self.canonical_event_ids:
            require_identifier(event_id, "canonical_event_ids")
        require_unique(self.canonical_event_ids, "canonical_event_ids")
        if not isinstance(self.playback_policy, PlaybackPolicySummaryV1):
            raise EducationContractError("playback_policy must be a PlaybackPolicySummaryV1")
        if not isinstance(self.spatial_policy, SpatialPolicyIntentV1):
            raise EducationContractError("spatial_policy must be a SpatialPolicyIntentV1")
        require_nonnegative_int(self.meter_change_count, "meter_change_count")
        require_optional_identifier(self.instruction_objective, "instruction_objective")
        require_optional_identifier(self.teacher_note, "teacher_note")


@dataclass
class LessonDeliveryPreviewService:
    """Inspect one stored delivery. The inbox is not modified."""

    deliveries: LessonDeliveryService

    def preview(self, delivery_id: str) -> LessonDeliveryPreviewV1:
        """Recheck both digests, then resolve. Neither step writes."""

        envelope = self.deliveries.get(delivery_id)
        try:
            validate_delivery_integrity(envelope)
        except EducationContractError as exc:
            # Named as its own error so the HTTP boundary can answer 409
            # without treating a corrupt stored record as a malformed request.
            raise DeliveryIntegrityError(str(exc)) from exc
        try:
            resolved = resolve_lesson_assignment(envelope.assignment)
        except LessonAssignmentError as exc:
            raise UnresolvableAssignmentError(str(exc)) from exc
        return _preview_of(envelope, resolved)


def preview_to_dict(preview: LessonDeliveryPreviewV1) -> dict[str, object]:
    """Plain data for the closed HTTP document.

    Keys are always present, including instructional fields that are null.
    Absence would be a second shape, and a closed schema cannot describe two.
    The declared digests are copied off the preview, which copied them off the
    stored envelope. Nothing here recomputes or replaces them.
    """

    playback = preview.playback_policy
    spatial = preview.spatial_policy
    return {
        "schema_id": preview.schema_id,
        "schema_version": preview.schema_version,
        "preview_status": preview.preview_status,
        "delivery_id": preview.delivery_id,
        "assignment_id": preview.assignment_id,
        "content_id": preview.content_id,
        "assignment_artifact_digest": preview.assignment_artifact_digest,
        "assignment_behavior_digest": preview.assignment_behavior_digest,
        "title": preview.title,
        "canonical_event_count": preview.canonical_event_count,
        "canonical_event_ids": list(preview.canonical_event_ids),
        "playback_policy": {
            "tempo_bpm": playback.tempo_bpm,
            "start_tick": playback.start_tick,
            "end_tick": playback.end_tick,
            "loop_enabled": playback.loop_enabled,
            "count_in_bars": playback.count_in_bars,
            "ticks_per_quarter": playback.ticks_per_quarter,
            "source_tempo_bpm": playback.source_tempo_bpm,
        },
        "spatial_policy": {
            "instrument_profile_id": spatial.instrument_profile_id,
            "fingering_policy_id": spatial.fingering_policy_id,
            "preferred_fret_min": spatial.preferred_fret_min,
            "preferred_fret_max": spatial.preferred_fret_max,
            "open_string_preference": spatial.open_string_preference,
        },
        "meter_change_count": preview.meter_change_count,
        "instruction_objective": preview.instruction_objective,
        "teacher_note": preview.teacher_note,
    }


def _preview_of(
    envelope: LessonDeliveryEnvelopeV1, resolved: ResolvedLessonV1
) -> LessonDeliveryPreviewV1:
    event_ids = tuple(event.event_id for event in resolved.events)
    return LessonDeliveryPreviewV1(
        schema_id=LESSON_DELIVERY_PREVIEW_SCHEMA_ID,
        schema_version=LESSON_DELIVERY_PREVIEW_SCHEMA_VERSION,
        preview_status=PREVIEW_STATUS_READY,
        delivery_id=envelope.delivery_id,
        assignment_id=resolved.assignment_id,
        content_id=resolved.content_id,
        assignment_artifact_digest=envelope.assignment_artifact_digest,
        assignment_behavior_digest=envelope.assignment_behavior_digest,
        title=resolved.title,
        canonical_event_count=len(event_ids),
        canonical_event_ids=event_ids,
        playback_policy=_playback_summary(resolved),
        spatial_policy=_spatial_intent(resolved),
        meter_change_count=len(resolved.meter_changes),
        instruction_objective=resolved.instruction_objective,
        teacher_note=resolved.teacher_note,
    )


def _playback_summary(resolved: ResolvedLessonV1) -> PlaybackPolicySummaryV1:
    playback: PlaybackRequestV1 = resolved.playback
    return PlaybackPolicySummaryV1(
        tempo_bpm=playback.tempo_bpm,
        start_tick=playback.start_tick,
        end_tick=playback.end_tick,
        loop_enabled=playback.loop_enabled,
        count_in_bars=playback.count_in_bars,
        ticks_per_quarter=playback.ticks_per_quarter,
        source_tempo_bpm=playback.source_tempo_bpm,
    )


def _spatial_intent(resolved: ResolvedLessonV1) -> SpatialPolicyIntentV1:
    spatial: SpatialSelectionRequestV1 = resolved.spatial
    return SpatialPolicyIntentV1(
        instrument_profile_id=spatial.instrument_profile_id,
        fingering_policy_id=spatial.fingering_policy_id,
        preferred_fret_min=spatial.preferred_fret_min,
        preferred_fret_max=spatial.preferred_fret_max,
        open_string_preference=spatial.open_string_preference.value,
    )


def _require_optional_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    require_nonnegative_int(value, field_name)


def _require_optional_bpm(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EducationContractError(f"{field_name} must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise EducationContractError(f"{field_name} must be finite")
