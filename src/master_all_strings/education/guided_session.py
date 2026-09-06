"""Guided practice session contracts (DO-015).

Education decides WHAT. The learner decides WHETHER. This module records WHEN /
NEXT: session progression, accepted-action execution state, and immutable
attempt history. It does not choose Educational next actions, score a
performance, recompute passages, or drive Transport.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum

from master_all_strings.education.contracts import (
    SUPPORTED_PRACTICE_RATES,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import (
    EducationContractError,
    require_identifier,
    require_nonnegative_int,
    require_schema_version,
    require_tuple,
    require_unique,
)
from master_all_strings.education.serialization import to_dict

__all__ = [
    "SESSION_POLICY_VERSION",
    "SESSION_SCHEMA_VERSION",
    "GuidedPracticeActionDisposition",
    "GuidedPracticeActionV1",
    "GuidedPracticeAttemptV1",
    "GuidedPracticeContextV1",
    "GuidedPracticeExecutionStatus",
    "GuidedPracticeSessionStatus",
    "GuidedPracticeSessionV1",
    "append_attempt",
    "compute_session_digest",
    "serialize_guided_practice_session",
    "session_with_digest",
]

SESSION_SCHEMA_VERSION = "1.0.0"
SESSION_POLICY_VERSION = "guided-practice-session-v1"

_DIGEST_EXCLUDED_SESSION_FIELDS = frozenset({"session_digest", "provenance"})
_MASTERY_FORBIDDEN = ("mastered", "perfect", "complete", "passed curriculum")

_PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


class GuidedPracticeSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    AWAITING_ACTION = "AWAITING_ACTION"
    AWAITING_ATTEMPT = "AWAITING_ATTEMPT"
    CLOSED = "CLOSED"
    TRANSITIONED = "TRANSITIONED"
    ABORTED = "ABORTED"


class GuidedPracticeActionDisposition(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class GuidedPracticeExecutionStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


def _forbid_mastery_wording(text: str, field_name: str) -> None:
    lowered = text.lower()
    for token in _MASTERY_FORBIDDEN:
        if token in lowered:
            raise EducationContractError(
                f"{field_name} must not represent CONTINUE as mastery ({token!r})"
            )


def _require_next_action(value: object, field_name: str) -> PracticeNextActionV1:
    if not isinstance(value, PracticeNextActionV1):
        raise EducationContractError(f"{field_name} must be a PracticeNextActionV1")
    _forbid_mastery_wording(value.action_type.value, f"{field_name}.action_type")
    _forbid_mastery_wording(value.message_key, f"{field_name}.message_key")
    return value


def _require_sha256_digest(value: str, field_name: str) -> None:
    require_identifier(value, field_name)
    if not value.startswith("sha256:"):
        raise EducationContractError(f"{field_name} must be a sha256: digest")


def _validate_execution_state(
    disposition: GuidedPracticeActionDisposition,
    execution: GuidedPracticeExecutionStatus,
    executed_action: PracticeNextActionV1 | None,
) -> None:
    if disposition is GuidedPracticeActionDisposition.PENDING:
        if execution is not GuidedPracticeExecutionStatus.NOT_REQUESTED:
            raise EducationContractError(
                "PENDING disposition requires execution_status NOT_REQUESTED"
            )
        if executed_action is not None:
            raise EducationContractError("PENDING disposition must not record executed_action")
        return
    if disposition is GuidedPracticeActionDisposition.DECLINED:
        if execution is not GuidedPracticeExecutionStatus.NOT_REQUESTED:
            raise EducationContractError(
                "DECLINED disposition requires execution_status NOT_REQUESTED"
            )
        if executed_action is not None:
            raise EducationContractError("DECLINED disposition must not record executed_action")
        return
    if execution is GuidedPracticeExecutionStatus.SUCCEEDED and executed_action is None:
        raise EducationContractError("SUCCEEDED requires executed_action")
    if execution is GuidedPracticeExecutionStatus.UNSUPPORTED and executed_action is not None:
        raise EducationContractError("UNSUPPORTED must not record executed_action")
    if execution is GuidedPracticeExecutionStatus.PENDING and executed_action is not None:
        raise EducationContractError("PENDING execution must not record executed_action")
    if execution is GuidedPracticeExecutionStatus.NOT_REQUESTED and executed_action is not None:
        raise EducationContractError("NOT_REQUESTED must not record executed_action")


@dataclass(frozen=True)
class GuidedPracticeContextV1:
    """Observed practice presentation state at the time of an attempt.

    Records rate and loop bounds. Does not compute Transport math or choose an
    Educational action.
    """

    schema_version: str
    playback_rate: float | None = None
    loop_start_tick: int | None = None
    loop_end_tick: int | None = None

    SCHEMA_VERSION = SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if self.playback_rate is not None:
            if float(self.playback_rate) not in SUPPORTED_PRACTICE_RATES:
                raise EducationContractError(
                    f"playback_rate must be one of {SUPPORTED_PRACTICE_RATES}"
                )
        if self.loop_start_tick is not None:
            require_nonnegative_int(self.loop_start_tick, "loop_start_tick")
        if self.loop_end_tick is not None:
            require_nonnegative_int(self.loop_end_tick, "loop_end_tick")
        start_present = self.loop_start_tick is not None
        end_present = self.loop_end_tick is not None
        if start_present != end_present:
            raise EducationContractError("loop bounds must be supplied together")
        if (
            self.loop_start_tick is not None
            and self.loop_end_tick is not None
            and self.loop_end_tick < self.loop_start_tick
        ):
            raise EducationContractError("loop_end_tick must not precede loop_start_tick")


@dataclass(frozen=True)
class GuidedPracticeActionV1:
    """One recommended Educational action plus learner and execution evidence.

    ``recommended_action`` is the primary DO-014 ``next_action``. Secondary
    Educational actions are advisory and are not recorded here. ``ACCEPTED``
    does not imply successful execution.
    """

    schema_version: str
    recommended_action: PracticeNextActionV1
    action_disposition: GuidedPracticeActionDisposition
    execution_status: GuidedPracticeExecutionStatus
    executed_action: PracticeNextActionV1 | None = None

    SCHEMA_VERSION = SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        object.__setattr__(
            self,
            "recommended_action",
            _require_next_action(self.recommended_action, "recommended_action"),
        )
        if not isinstance(self.action_disposition, GuidedPracticeActionDisposition):
            raise EducationContractError(
                "action_disposition must be a GuidedPracticeActionDisposition"
            )
        if not isinstance(self.execution_status, GuidedPracticeExecutionStatus):
            raise EducationContractError(
                "execution_status must be a GuidedPracticeExecutionStatus"
            )
        if self.executed_action is not None:
            object.__setattr__(
                self,
                "executed_action",
                _require_next_action(self.executed_action, "executed_action"),
            )
        _validate_execution_state(
            self.action_disposition,
            self.execution_status,
            self.executed_action,
        )


@dataclass(frozen=True)
class GuidedPracticeAttemptV1:
    """One evaluated attempt inside a guided practice session.

    Identity reuses the MAS chain. ``attempt_id`` is opaque and is never derived
    from pitches, lesson hashes, or timestamps.
    """

    schema_version: str
    attempt_id: str
    attempt_index: int
    assignment_id: str
    content_id: str
    canonical_revision_id: str
    performance_session_id: str
    evaluation_digest: str
    guidance_digest: str
    action: GuidedPracticeActionV1
    practice_context: GuidedPracticeContextV1

    SCHEMA_VERSION = SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.attempt_id, "attempt_id")
        require_nonnegative_int(self.attempt_index, "attempt_index")
        for name in (
            "assignment_id",
            "content_id",
            "canonical_revision_id",
            "performance_session_id",
        ):
            require_identifier(getattr(self, name), name)
        _require_sha256_digest(self.evaluation_digest, "evaluation_digest")
        _require_sha256_digest(self.guidance_digest, "guidance_digest")
        if not isinstance(self.action, GuidedPracticeActionV1):
            raise EducationContractError("action must be a GuidedPracticeActionV1")
        if not isinstance(self.practice_context, GuidedPracticeContextV1):
            raise EducationContractError("practice_context must be a GuidedPracticeContextV1")

    @property
    def recommended_action(self) -> PracticeNextActionV1:
        return self.action.recommended_action

    @property
    def action_disposition(self) -> GuidedPracticeActionDisposition:
        return self.action.action_disposition

    @property
    def execution_status(self) -> GuidedPracticeExecutionStatus:
        return self.action.execution_status

    @property
    def executed_action(self) -> PracticeNextActionV1 | None:
        return self.action.executed_action


@dataclass(frozen=True)
class GuidedPracticeSessionV1:
    """Portable guided-practice session record.

    A zero-attempt session is schema-valid so the contract can describe a new
    object. The Stage 2 service does not persist one: the first evaluated
    attempt creates the session.
    """

    schema_version: str
    policy_version: str
    session_id: str
    assignment_id: str
    content_id: str
    canonical_revision_id: str
    status: GuidedPracticeSessionStatus
    attempts: tuple[GuidedPracticeAttemptV1, ...]
    current_attempt_index: int | None
    session_digest: str
    provenance: tuple[tuple[str, str], ...] = ()

    SCHEMA_VERSION = SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.policy_version, "policy_version")
        require_identifier(self.session_id, "session_id")
        require_identifier(self.assignment_id, "assignment_id")
        require_identifier(self.content_id, "content_id")
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        if not isinstance(self.status, GuidedPracticeSessionStatus):
            raise EducationContractError("status must be a GuidedPracticeSessionStatus")
        require_tuple(self.attempts, "attempts")
        for attempt in self.attempts:
            if not isinstance(attempt, GuidedPracticeAttemptV1):
                raise EducationContractError("attempts must contain GuidedPracticeAttemptV1")
            if attempt.assignment_id != self.assignment_id:
                raise EducationContractError("attempt assignment_id does not match session")
            if attempt.content_id != self.content_id:
                raise EducationContractError("attempt content_id does not match session")
            if attempt.canonical_revision_id != self.canonical_revision_id:
                raise EducationContractError("attempt canonical_revision_id does not match session")
        indexes = tuple(attempt.attempt_index for attempt in self.attempts)
        if indexes != tuple(range(len(self.attempts))):
            raise EducationContractError("attempt_index values must be unique and monotonic from 0")
        require_unique([attempt.attempt_id for attempt in self.attempts], "attempt_id")
        require_unique(
            [attempt.performance_session_id for attempt in self.attempts],
            "performance_session_id",
        )
        if not self.attempts:
            if self.current_attempt_index is not None:
                raise EducationContractError(
                    "current_attempt_index must be null when attempts is empty"
                )
        else:
            if self.current_attempt_index != len(self.attempts) - 1:
                raise EducationContractError(
                    "current_attempt_index must reference the latest attempt"
                )
        _require_sha256_digest(self.session_digest, "session_digest")
        require_tuple(self.provenance, "provenance")
        for key, value in self.provenance:
            require_identifier(key, "provenance key")
            require_identifier(value, "provenance value")


def compute_session_digest(session: GuidedPracticeSessionV1) -> str:
    """Digest session identity, status, and attempts only.

    Provenance and the digest field itself are excluded so wall-clock audit
    fields cannot change the semantic hash.
    """

    if not isinstance(session, GuidedPracticeSessionV1):
        raise EducationContractError("expected a GuidedPracticeSessionV1")
    encoded = to_dict(session)
    for field_name in _DIGEST_EXCLUDED_SESSION_FIELDS:
        encoded.pop(field_name, None)
    payload = json.dumps(encoded, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def serialize_guided_practice_session(session: GuidedPracticeSessionV1) -> str:
    if not isinstance(session, GuidedPracticeSessionV1):
        raise EducationContractError("expected a GuidedPracticeSessionV1")
    return json.dumps(to_dict(session), indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def session_with_digest(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    """Return ``session`` with ``session_digest`` matching its semantic fields."""

    digest = compute_session_digest(session)
    if session.session_digest == digest:
        return session
    return replace(session, session_digest=digest)


def append_attempt(
    session: GuidedPracticeSessionV1,
    attempt: GuidedPracticeAttemptV1,
    *,
    status: GuidedPracticeSessionStatus | None = None,
) -> GuidedPracticeSessionV1:
    """Return a new session with ``attempt`` appended. Prior attempts are unchanged."""

    if not isinstance(session, GuidedPracticeSessionV1):
        raise EducationContractError("expected a GuidedPracticeSessionV1")
    if not isinstance(attempt, GuidedPracticeAttemptV1):
        raise EducationContractError("attempt must be a GuidedPracticeAttemptV1")
    expected_index = len(session.attempts)
    if attempt.attempt_index != expected_index:
        raise EducationContractError(
            f"attempt_index must be {expected_index}, got {attempt.attempt_index}"
        )
    next_status = status if status is not None else session.status
    return session_with_digest(
        replace(
            session,
            attempts=session.attempts + (attempt,),
            current_attempt_index=attempt.attempt_index,
            status=next_status,
            session_digest=_PLACEHOLDER_DIGEST,
        )
    )
