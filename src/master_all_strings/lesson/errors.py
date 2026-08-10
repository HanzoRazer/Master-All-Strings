"""Domain errors for the lesson-assignment boundary."""

from __future__ import annotations


class LessonAssignmentError(ValueError):
    """Base error for lesson-assignment contract failures."""


class LessonValidationError(LessonAssignmentError):
    """Raised when an assignment fails structural or semantic validation."""

    def __init__(self, reason: str, *, code: str = "validation_failed") -> None:
        self.reason = reason
        self.code = code
        super().__init__(f"[{code}] {reason}")


class LessonSchemaError(LessonAssignmentError):
    """Raised for unsupported or malformed schema versions."""

    def __init__(self, reason: str, *, code: str = "unsupported_schema") -> None:
        self.reason = reason
        self.code = code
        super().__init__(f"[{code}] {reason}")


class TeacherOverrideError(LessonValidationError):
    """Raised when a teacher override is invalid or physically impossible."""

    def __init__(self, reason: str, *, code: str = "invalid_override") -> None:
        super().__init__(reason, code=code)
