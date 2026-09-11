"""Localhost JSON facade for guided-practice sessions (DO-015 Stage 4).

Transport/adaptation only. Every lifecycle transition is delegated to the
Stage 2 service. This module does not choose Educational actions, mint
identities, or execute Transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from master_all_strings.education.contracts import (
    PracticeAttemptSummaryV1,
    PracticeEvaluationResultV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.guidance import (
    TeachingGuidanceItemV1,
    TeachingGuidanceProjectionV1,
)
from master_all_strings.education.guided_session import (
    GuidedPracticeActionDisposition,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionV1,
)
from master_all_strings.education.guided_session_service import (
    append_evaluated_attempt,
    create_from_first_evaluated_attempt,
    record_action_disposition,
    record_action_execution,
    transition_session,
)
from master_all_strings.education.serialization import to_dict

__all__ = [
    "GUIDED_SESSION_API_PREFIX",
    "GuidedSessionNotFoundError",
    "GuidedSessionRequestError",
    "InMemoryGuidedPracticeSessionRepository",
    "LocalGuidedPracticeSessionApi",
]

GUIDED_SESSION_API_PREFIX = "/api/education/guided-sessions"


class GuidedSessionRequestError(EducationContractError):
    """Malformed guided-session API request."""


class GuidedSessionNotFoundError(EducationContractError):
    """Unknown guided-session identity."""


@dataclass
class InMemoryGuidedPracticeSessionRepository:
    """Dumb in-memory store. Does not implement lifecycle transitions."""

    _sessions: dict[str, GuidedPracticeSessionV1] = field(default_factory=dict)

    def get(self, session_id: str) -> GuidedPracticeSessionV1 | None:
        return self._sessions.get(session_id)

    def put(self, session: GuidedPracticeSessionV1) -> None:
        self._sessions[session.session_id] = session


def _pairs(value: object, field_name: str) -> tuple[tuple[str, str], ...]:
    if isinstance(value, dict):
        return tuple(sorted((str(key), str(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        pairs: list[tuple[str, str]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise GuidedSessionRequestError(f"{field_name} must contain pairs")
            pairs.append((str(item[0]), str(item[1])))
        return tuple(pairs)
    raise GuidedSessionRequestError(f"{field_name} must be a mapping or pair list")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise GuidedSessionRequestError("expected an integer")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GuidedSessionRequestError("expected a number")
    return float(value)


def _require_mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GuidedSessionRequestError(f"{field_name} must be an object")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise GuidedSessionRequestError(f"{field_name} must be an array")
    return tuple(str(item) for item in value)


def _next_action_from_dict(payload: object, field_name: str = "action") -> PracticeNextActionV1:
    data = _require_mapping(payload, field_name)
    try:
        action_type = PracticeNextActionType(str(data["action_type"]))
        return PracticeNextActionV1(
            schema_version=str(data.get("schema_version", PracticeNextActionV1.SCHEMA_VERSION)),
            action_type=action_type,
            reason_finding_ids=_string_tuple(data.get("reason_finding_ids"), "reason_finding_ids"),
            message_key=str(data["message_key"]),
            target_rate=_optional_float(data.get("target_rate")),
            focus_start_tick=_optional_int(data.get("focus_start_tick")),
            focus_end_tick=_optional_int(data.get("focus_end_tick")),
            teaching_aid=None if data.get("teaching_aid") is None else str(data["teaching_aid"]),
        )
    except EducationContractError as exc:
        raise GuidedSessionRequestError(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise GuidedSessionRequestError(f"{field_name} is incomplete or malformed") from exc


def _finding_from_dict(payload: object) -> PracticeFindingV1:
    data = _require_mapping(payload, "finding")
    return PracticeFindingV1(
        schema_version=str(data.get("schema_version", PracticeFindingV1.SCHEMA_VERSION)),
        finding_id=str(data["finding_id"]),
        finding_type=PracticeFindingType(str(data["finding_type"])),
        severity=PracticeFindingSeverity(str(data["severity"])),
        evidence_refs=_string_tuple(data.get("evidence_refs"), "evidence_refs"),
        message_key=str(data["message_key"]),
        expected_event_refs=_string_tuple(data.get("expected_event_refs"), "expected_event_refs"),
        repetition_index=_optional_int(data.get("repetition_index")),
        focus_start_tick=_optional_int(data.get("focus_start_tick")),
        focus_end_tick=_optional_int(data.get("focus_end_tick")),
        observed_value=_optional_float(data.get("observed_value")),
        threshold_value=_optional_float(data.get("threshold_value")),
        metadata=_pairs(data.get("metadata", {}), "metadata"),
    )


def _focus_from_dict(payload: object) -> PracticeFocusRangeV1:
    data = _require_mapping(payload, "focus_range")
    return PracticeFocusRangeV1(
        int(data["start_tick"]),
        int(data["end_tick"]),
        _string_tuple(data.get("finding_ids"), "finding_ids"),
    )


def _summary_from_dict(payload: object) -> PracticeAttemptSummaryV1:
    data = _require_mapping(payload, "summary")
    return PracticeAttemptSummaryV1(
        schema_version=str(data.get("schema_version", PracticeAttemptSummaryV1.SCHEMA_VERSION)),
        performance_session_id=str(data["performance_session_id"]),
        expected_event_count=int(data["expected_event_count"]),
        observed_event_count=int(data["observed_event_count"]),
        matched_count=int(data["matched_count"]),
        missing_count=int(data["missing_count"]),
        extra_count=int(data["extra_count"]),
        pitch_finding_count=int(data["pitch_finding_count"]),
        timing_finding_count=int(data["timing_finding_count"]),
        actionable_finding_count=int(data["actionable_finding_count"]),
        repetition_count=int(data["repetition_count"]),
        focus_ranges=tuple(_focus_from_dict(item) for item in data.get("focus_ranges", ())),
        primary_action=_next_action_from_dict(data["primary_action"], "primary_action"),
        secondary_actions=tuple(
            _next_action_from_dict(item, "secondary_action")
            for item in data.get("secondary_actions", ())
        ),
    )


def evaluation_from_payload(payload: object) -> PracticeEvaluationResultV1:
    data = _require_mapping(payload, "evaluation")
    try:
        schema_version = str(
            data.get("schema_version", PracticeEvaluationResultV1.SCHEMA_VERSION)
        )
        return PracticeEvaluationResultV1(
            schema_version=schema_version,
            assignment_id=str(data["assignment_id"]),
            content_id=str(data["content_id"]),
            performance_session_id=str(data["performance_session_id"]),
            evaluation_policy_id=str(data["evaluation_policy_id"]),
            evaluation_policy_version=str(data["evaluation_policy_version"]),
            findings=tuple(_finding_from_dict(item) for item in data.get("findings", ())),
            summary=_summary_from_dict(data["summary"]),
            primary_next_action=_next_action_from_dict(
                data["primary_next_action"],
                "primary_next_action",
            ),
            secondary_actions=tuple(
                _next_action_from_dict(item, "secondary_action")
                for item in data.get("secondary_actions", ())
            ),
            provenance=_pairs(data.get("provenance", {}), "provenance"),
            evaluation_digest=str(data["evaluation_digest"]),
        )
    except EducationContractError as exc:
        raise GuidedSessionRequestError(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise GuidedSessionRequestError("evaluation is incomplete or malformed") from exc


def _guidance_item_from_dict(payload: object) -> TeachingGuidanceItemV1:
    data = _require_mapping(payload, "guidance_item")
    return TeachingGuidanceItemV1(
        schema_version=str(data.get("schema_version", TeachingGuidanceItemV1.SCHEMA_VERSION)),
        finding_id=str(data["finding_id"]),
        finding_type=PracticeFindingType(str(data["finding_type"])),
        severity=PracticeFindingSeverity(str(data["severity"])),
        evidence_refs=_string_tuple(data.get("evidence_refs"), "evidence_refs"),
        message_key=str(data["message_key"]),
        canonical_event_id=(
            None if data.get("canonical_event_id") is None else str(data["canonical_event_id"])
        ),
        observed_value=_optional_float(data.get("observed_value")),
        threshold_value=_optional_float(data.get("threshold_value")),
        zone_context=None if data.get("zone_context") is None else str(data["zone_context"]),
    )


def guidance_from_payload(payload: object) -> TeachingGuidanceProjectionV1:
    data = _require_mapping(payload, "guidance")
    try:
        return TeachingGuidanceProjectionV1(
            schema_version=str(
                data.get("schema_version", TeachingGuidanceProjectionV1.SCHEMA_VERSION)
            ),
            canonical_revision_id=str(data["canonical_revision_id"]),
            performance_session_id=str(data["performance_session_id"]),
            evaluation_digest=str(data["evaluation_digest"]),
            policy_version=str(data["policy_version"]),
            items=tuple(_guidance_item_from_dict(item) for item in data.get("items", ())),
            next_action=_next_action_from_dict(data["next_action"], "next_action"),
            guidance_digest=str(data["guidance_digest"]),
            provenance=_pairs(data.get("provenance", {}), "provenance"),
        )
    except EducationContractError as exc:
        raise GuidedSessionRequestError(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise GuidedSessionRequestError("guidance is incomplete or malformed") from exc


def _require_session_id(payload: dict[str, Any]) -> str:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise GuidedSessionRequestError("session_id is required")
    return session_id


def _require_attempt_id(payload: dict[str, Any]) -> str:
    attempt_id = payload.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise GuidedSessionRequestError("attempt_id is required")
    return attempt_id


@dataclass
class LocalGuidedPracticeSessionApi:
    """In-memory guided-session API. Lifecycle authority stays in Stage 2."""

    store: InMemoryGuidedPracticeSessionRepository = field(
        default_factory=InMemoryGuidedPracticeSessionRepository
    )

    def create(self, payload: dict[str, Any]) -> GuidedPracticeSessionV1:
        session_id = _require_session_id(payload)
        attempt_id = _require_attempt_id(payload)
        if self.store.get(session_id) is not None:
            raise EducationContractError("session_id already exists")
        evaluation = evaluation_from_payload(payload.get("evaluation"))
        guidance = guidance_from_payload(payload.get("guidance"))
        session = create_from_first_evaluated_attempt(
            evaluation,
            guidance,
            session_id=session_id,
            attempt_id=attempt_id,
        )
        self.store.put(session)
        return session

    def get(self, session_id: str) -> GuidedPracticeSessionV1:
        session = self.store.get(session_id)
        if session is None:
            raise GuidedSessionNotFoundError(f"unknown session_id {session_id!r}")
        return session

    def record_disposition(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> GuidedPracticeSessionV1:
        session = self.get(session_id)
        try:
            disposition = GuidedPracticeActionDisposition(str(payload["disposition"]))
        except (KeyError, ValueError) as exc:
            raise GuidedSessionRequestError("disposition must be ACCEPTED or DECLINED") from exc
        updated = record_action_disposition(session, disposition)
        self.store.put(updated)
        return updated

    def record_execution(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> GuidedPracticeSessionV1:
        session = self.get(session_id)
        try:
            execution_status = GuidedPracticeExecutionStatus(str(payload["execution_status"]))
        except (KeyError, ValueError) as exc:
            raise GuidedSessionRequestError(
                "execution_status must be SUCCEEDED, FAILED, or UNSUPPORTED"
            ) from exc
        executed_action = None
        if "executed_action" in payload and payload["executed_action"] is not None:
            executed_action = _next_action_from_dict(payload["executed_action"], "executed_action")
        updated = record_action_execution(
            session,
            execution_status,
            executed_action=executed_action,
        )
        self.store.put(updated)
        return updated

    def append(self, session_id: str, payload: dict[str, Any]) -> GuidedPracticeSessionV1:
        session = self.get(session_id)
        attempt_id = _require_attempt_id(payload)
        evaluation = evaluation_from_payload(payload.get("evaluation"))
        guidance = guidance_from_payload(payload.get("guidance"))
        updated = append_evaluated_attempt(
            session,
            evaluation,
            guidance,
            attempt_id=attempt_id,
        )
        self.store.put(updated)
        return updated

    def transition(self, session_id: str, payload: dict[str, Any]) -> GuidedPracticeSessionV1:
        session = self.get(session_id)
        try:
            next_assignment_id = str(payload["next_assignment_id"])
            next_content_id = str(payload["next_content_id"])
        except (KeyError, TypeError) as exc:
            raise GuidedSessionRequestError(
                "transition requires next_assignment_id and next_content_id"
            ) from exc
        reason = payload.get("reason")
        if reason is None:
            updated = transition_session(
                session,
                next_assignment_id=next_assignment_id,
                next_content_id=next_content_id,
            )
        else:
            updated = transition_session(
                session,
                next_assignment_id=next_assignment_id,
                next_content_id=next_content_id,
                reason=str(reason),
            )
        self.store.put(updated)
        return updated

    def handle_http(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Map HTTP method/path onto Stage 2 operations."""

        try:
            status, session = self._dispatch(method, path, payload or {})
        except GuidedSessionNotFoundError as exc:
            return 404, {"error": str(exc)}
        except GuidedSessionRequestError as exc:
            return 400, {"error": str(exc)}
        except EducationContractError as exc:
            return 409, {"error": str(exc)}
        except (KeyError, TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}
        return status, to_dict(session)

    def _dispatch(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> tuple[int, GuidedPracticeSessionV1]:
        if not path.startswith(GUIDED_SESSION_API_PREFIX):
            raise GuidedSessionRequestError("not a guided-session path")
        rest = path[len(GUIDED_SESSION_API_PREFIX) :].strip("/")
        parts = [part for part in rest.split("/") if part]
        verb = method.upper()
        if verb == "POST" and parts == []:
            return 201, self.create(payload)
        if not parts:
            raise GuidedSessionRequestError("guided-session path is incomplete")
        if parts[-1] in {"close", "begin-next", "begin_next_attempt", "close_session"}:
            raise GuidedSessionRequestError("close and begin-next are not API operations")
        session_id = parts[0]
        if verb == "GET" and len(parts) == 1:
            return 200, self.get(session_id)
        if verb == "POST" and len(parts) == 2 and parts[1] == "disposition":
            return 200, self.record_disposition(session_id, payload)
        if verb == "POST" and len(parts) == 2 and parts[1] == "execution":
            return 200, self.record_execution(session_id, payload)
        if verb == "POST" and len(parts) == 2 and parts[1] == "attempts":
            return 200, self.append(session_id, payload)
        if verb == "POST" and len(parts) == 2 and parts[1] == "transition":
            return 200, self.transition(session_id, payload)
        raise GuidedSessionRequestError(f"unknown guided-session route {method} {path}")
