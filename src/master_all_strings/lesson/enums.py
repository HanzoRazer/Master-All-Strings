"""Enumerations for LessonAssignmentV1."""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AssessmentMode",
    "LessonContentFormat",
    "LessonSourceType",
    "OpenStringPreference",
    "TeacherOverrideStatus",
]


class LessonContentFormat(StrEnum):
    """Active musical content format carried by an assignment."""

    CANONICAL_EVENTS = "canonical_events"


class LessonSourceType(StrEnum):
    """Provenance classification for how an assignment was created."""

    MIDI_IMPORT = "midi_import"
    BUNDLED = "bundled"
    TEACHER = "teacher"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class OpenStringPreference(StrEnum):
    """Soft open-string instructional preference (not screen policy)."""

    ALLOW = "allow"
    PREFER = "prefer"
    AVOID = "avoid"
    EXCLUDE = "exclude"


class TeacherOverrideStatus(StrEnum):
    """Validation status for a teacher override after physical checks."""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN_EVENT = "unknown_event"
    PHYSICALLY_IMPOSSIBLE = "physically_impossible"


class AssessmentMode(StrEnum):
    """Preserve-only assessment enablement mode for future stages."""

    DISABLED = "disabled"
    ENABLED = "enabled"
