"""Whole-object validation for LessonAssignmentV1."""

from __future__ import annotations

from collections.abc import Mapping

from master_all_strings.instruments import InstrumentProfile

from .errors import LessonValidationError, TeacherOverrideError
from .models import LessonAssignmentV1, TeacherOverrideV1
from .overrides import validate_teacher_override

__all__ = ["validate_assignment"]


def validate_assignment(
    assignment: LessonAssignmentV1,
    *,
    instrument_profiles: Mapping[str, InstrumentProfile] | None = None,
    validate_overrides_physically: bool = True,
) -> None:
    """Validate structural invariants and optional physical override validity.

    Raises:
        LessonValidationError: on structural failures.
        TeacherOverrideError: on invalid teacher overrides when physical validation
            is enabled and an instrument profile is available.
    """

    if not isinstance(assignment, LessonAssignmentV1):
        raise LessonValidationError(
            "expected LessonAssignmentV1",
            code="invalid_assignment",
        )

    # Model construction already enforces most invariants; this function is the
    # explicit whole-object gate used by importers, deserializers, and the MVP path.
    event_ids = {event.event_id for event in assignment.musical_content.events}
    for override in assignment.teacher_overrides:
        if override.event_id not in event_ids:
            raise TeacherOverrideError(
                f"override references unknown event_id {override.event_id!r}",
                code="override_unknown_event",
            )

    profiles = instrument_profiles or {}
    profile_id = assignment.spatial_guidance.instrument_profile_id
    if profile_id not in profiles:
        # Structural validation may run before a profile catalog is available.
        # When a catalog is provided, unknown instruments fail closed.
        if instrument_profiles is not None:
            raise LessonValidationError(
                f"unknown instrument_profile_id: {profile_id!r}",
                code="unknown_instrument",
            )
        return

    if not validate_overrides_physically:
        return

    profile = profiles[profile_id]
    for override in assignment.teacher_overrides:
        event = next(
            item for item in assignment.musical_content.events if item.event_id == override.event_id
        )
        validate_teacher_override(override, event=event, instrument=profile)


def require_override_event(
    override: TeacherOverrideV1,
    *,
    event_ids: set[str],
) -> None:
    """Reject overrides that do not reference a known event."""

    if override.event_id not in event_ids:
        raise TeacherOverrideError(
            f"override references unknown event_id {override.event_id!r}",
            code="override_unknown_event",
        )
