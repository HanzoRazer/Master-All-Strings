"""Deterministic serialization for Educational Engine contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from master_all_strings.education.contracts import PracticeEvaluationResultV1
from master_all_strings.education.errors import EducationContractError

__all__ = [
    "compute_evaluation_digest",
    "serialize_evaluation_result",
    "to_dict",
    "to_json",
]

_MAPPING_FIELDS = frozenset({"metadata", "provenance"})


def _encode(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name), f.name) for f in fields(value)}
    if isinstance(value, tuple):
        if field_name in _MAPPING_FIELDS:
            return {str(k): str(v) for k, v in sorted(value)}
        return [_encode(item) for item in value]
    return value


def to_dict(record: Any) -> dict[str, Any]:
    if not is_dataclass(record) or isinstance(record, type):
        raise EducationContractError("to_dict requires a contract dataclass instance")
    return {f.name: _encode(getattr(record, f.name), f.name) for f in fields(record)}


def to_json(record: Any) -> str:
    return json.dumps(to_dict(record), indent=2, sort_keys=False) + "\n"


def serialize_evaluation_result(result: PracticeEvaluationResultV1) -> str:
    if not isinstance(result, PracticeEvaluationResultV1):
        raise EducationContractError("expected a PracticeEvaluationResultV1")
    return to_json(result)


def compute_evaluation_digest(
    *,
    assignment_id: str,
    content_id: str,
    performance_session_id: str,
    evaluation_policy_id: str,
    evaluation_policy_version: str,
    findings: Any,
    summary: Any,
    primary_next_action: Any,
    secondary_actions: Any,
    provenance: Any,
) -> str:
    """Digest interpretation semantics only — excludes wall clock and UI state."""

    payload = {
        "assignment_id": assignment_id,
        "content_id": content_id,
        "evaluation_policy_id": evaluation_policy_id,
        "evaluation_policy_version": evaluation_policy_version,
        "findings": [to_dict(item) for item in findings],
        "performance_session_id": performance_session_id,
        "primary_next_action": to_dict(primary_next_action),
        "provenance": {str(k): str(v) for k, v in sorted(provenance)},
        "secondary_actions": [to_dict(item) for item in secondary_actions],
        "summary": to_dict(summary),
    }
    # Summary embeds actions; digest uses a summary payload without nested action
    # duplication by hashing the canonical field set above after stripping digest.
    summary_dict = to_dict(summary)
    summary_dict.pop("primary_action", None)
    summary_dict.pop("secondary_actions", None)
    payload["summary"] = summary_dict
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
