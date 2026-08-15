"""In-memory current-session practice attempt history (no persistence)."""

from __future__ import annotations

from dataclasses import dataclass, field

from master_all_strings.education.contracts import PracticeEvaluationResultV1
from master_all_strings.education.errors import EducationContractError

__all__ = ["PracticeSessionHistory"]


@dataclass
class PracticeSessionHistory:
    """Session-local attempt list for the active lesson runtime."""

    assignment_id: str | None = None
    content_id: str | None = None
    attempts: list[PracticeEvaluationResultV1] = field(default_factory=list)

    def begin_lesson(self, *, assignment_id: str, content_id: str) -> None:
        self.assignment_id = assignment_id
        self.content_id = content_id
        self.attempts.clear()

    def record(self, result: PracticeEvaluationResultV1) -> None:
        if not isinstance(result, PracticeEvaluationResultV1):
            raise EducationContractError("result must be a PracticeEvaluationResultV1")
        if self.assignment_id is None:
            self.assignment_id = result.assignment_id
            self.content_id = result.content_id
        if result.assignment_id != self.assignment_id:
            raise EducationContractError("attempt assignment_id does not match session")
        if result.content_id != self.content_id:
            raise EducationContractError("attempt content_id does not match session")
        self.attempts.append(result)

    def clear(self) -> None:
        self.attempts.clear()
        self.assignment_id = None
        self.content_id = None
