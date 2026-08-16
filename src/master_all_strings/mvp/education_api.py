"""Localhost-only JSON facade for Educational practice evaluation (DO-010)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeNextActionType,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.evaluation import PracticeEvaluator
from master_all_strings.education.messages import MESSAGE_CATALOG_V1
from master_all_strings.education.serialization import to_dict
from master_all_strings.education.session_history import PracticeSessionHistory
from master_all_strings.performance.alignment import align_performance
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
)

__all__ = ["LocalPracticeEvaluationApi", "GOLDEN_DEMO_ATTEMPTS"]

_REPO = Path(__file__).resolve().parents[3]
_GOLDEN_DIR = _REPO / "resources" / "education" / "examples" / "evaluation"


def _observed_from_dict(payload: dict[str, Any]) -> ObservedMidiNoteV1:
    status = ObservedMidiNoteStatus(str(payload["status"]))
    return ObservedMidiNoteV1(
        schema_version=str(payload.get("schema_version", "1.0.0")),
        observed_event_id=str(payload["observed_event_id"]),
        capture_id=str(payload["capture_id"]),
        note_on_event_id=str(payload["note_on_event_id"]),
        note_off_event_id=(
            None if payload.get("note_off_event_id") is None else str(payload["note_off_event_id"])
        ),
        midi_note=int(payload["midi_note"]),
        velocity=int(payload["velocity"]),
        channel=int(payload["channel"]),
        source_device=str(payload["source_device"]),
        note_on_time_ns=int(payload["note_on_time_ns"]),
        note_off_time_ns=(
            None if payload.get("note_off_time_ns") is None else int(payload["note_off_time_ns"])
        ),
        duration_ns=None if payload.get("duration_ns") is None else int(payload["duration_ns"]),
        source_string=(
            None if payload.get("source_string") is None else int(payload["source_string"])
        ),
        status=status,
        repetition_index=int(payload.get("repetition_index", 0)),
        practice_onset_seconds=(
            None
            if payload.get("practice_onset_seconds") is None
            else float(payload["practice_onset_seconds"])
        ),
        estimated_start_tick=(
            None
            if payload.get("estimated_start_tick") is None
            else int(payload["estimated_start_tick"])
        ),
    )


def _aligned_from_dict(payload: dict[str, Any]) -> AlignedPerformanceEventV1:
    return AlignedPerformanceEventV1(
        status=AlignmentStatus(str(payload["status"])),
        expected_event_id=(
            None if payload.get("expected_event_id") is None else str(payload["expected_event_id"])
        ),
        observed_event_id=(
            None if payload.get("observed_event_id") is None else str(payload["observed_event_id"])
        ),
        repetition_index=int(payload.get("repetition_index", 0)),
        timing_delta_ms=(
            None if payload.get("timing_delta_ms") is None else int(payload["timing_delta_ms"])
        ),
        pitch_delta_semitones=(
            None
            if payload.get("pitch_delta_semitones") is None
            else int(payload["pitch_delta_semitones"])
        ),
        expected_start_tick=(
            None
            if payload.get("expected_start_tick") is None
            else int(payload["expected_start_tick"])
        ),
        observed_estimated_tick=(
            None
            if payload.get("observed_estimated_tick") is None
            else int(payload["observed_estimated_tick"])
        ),
    )


def _tempo_from_dict(payload: dict[str, Any]) -> TempoChangeV1:
    if "microseconds_per_quarter" in payload:
        return TempoChangeV1(
            "1.0.0",
            int(payload["tick"]),
            int(payload["microseconds_per_quarter"]),
        )
    bpm = float(payload["tempo_bpm"])
    us = int(round(60_000_000 / bpm))
    return TempoChangeV1("1.0.0", int(payload.get("tick", 0)), us)


def _enrich(result_dict: dict[str, Any]) -> dict[str, Any]:
    messages = {
        finding["message_key"]: MESSAGE_CATALOG_V1[finding["message_key"]]
        for finding in result_dict["findings"]
        if finding["message_key"] in MESSAGE_CATALOG_V1
    }
    primary_key = result_dict["primary_next_action"]["message_key"]
    messages[primary_key] = MESSAGE_CATALOG_V1[primary_key]
    for action in result_dict["secondary_actions"]:
        messages[action["message_key"]] = MESSAGE_CATALOG_V1[action["message_key"]]
    return {
        "evaluation": result_dict,
        "messages": messages,
        "hardware_status": {
            "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
            "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
        },
    }


GOLDEN_DEMO_ATTEMPTS: tuple[tuple[str, PracticeNextActionType], ...] = (
    ("attempt1_slow_down.json", PracticeNextActionType.SLOW_DOWN),
    ("attempt2_isolate_passage.json", PracticeNextActionType.ISOLATE_PASSAGE),
    ("attempt3_continue.json", PracticeNextActionType.CONTINUE),
)


@dataclass
class LocalPracticeEvaluationApi:
    """In-memory Educational evaluation API for the localhost MVP shell."""

    history: PracticeSessionHistory = field(default_factory=PracticeSessionHistory)
    evaluator: PracticeEvaluator = field(init=False)
    last_result: dict[str, Any] | None = None
    last_applied_action: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.evaluator = PracticeEvaluator(
            policy=PracticeEvaluationPolicyV1.mvp_defaults(),
            history=self.history,
        )

    def handle(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "begin_lesson":
            self.history.begin_lesson(
                assignment_id=str(payload["assignment_id"]),
                content_id=str(payload["content_id"]),
            )
            self.last_result = None
            self.last_applied_action = None
            return {"status": "lesson_ready"}
        if action == "evaluate":
            return self._evaluate(payload)
        if action == "get":
            if self.last_result is None:
                raise EducationContractError("no evaluation recorded")
            return self.last_result
        if action == "session":
            return {
                "assignment_id": self.history.assignment_id,
                "content_id": self.history.content_id,
                "attempt_count": len(self.history.attempts),
                "last_digest": (
                    None
                    if self.last_result is None
                    else self.last_result["evaluation"]["evaluation_digest"]
                ),
            }
        if action == "apply_action":
            return self._apply_action(payload)
        if action == "golden_demo":
            return self._golden_demo()
        raise EducationContractError(f"unknown education action {action!r}")

    def _evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "aligned_events" in payload:
            alignment = PerformanceAlignmentResultV1(
                schema_version="1.0.0",
                assignment_id=str(payload["assignment_id"]),
                content_id=str(payload["content_id"]),
                performance_session_id=str(payload["performance_session_id"]),
                alignment_policy=PerformanceAlignmentPolicyV1(),
                aligned_events=tuple(
                    _aligned_from_dict(row) for row in payload["aligned_events"]
                ),
                unmatched_expected_ids=tuple(payload.get("unmatched_expected_ids", ())),
                unmatched_observed_ids=tuple(payload.get("unmatched_observed_ids", ())),
            )
        else:
            alignment = self._align_from_payload(payload)
        current_rate = float(payload.get("current_rate", 1.0))
        result = self.evaluator.evaluate(alignment, current_rate=current_rate)
        enriched = _enrich(to_dict(result))
        self.last_result = enriched
        return enriched

    def _align_from_payload(self, payload: dict[str, Any]) -> PerformanceAlignmentResultV1:
        expected = tuple(
            MusicalEvent(
                event_id=str(row["event_id"]),
                midi_note=int(row["midi_note"]),
                start_tick=int(row.get("onset_tick", row.get("start_tick", 0))),
                duration_ticks=int(row.get("duration_ticks", 480)),
                velocity=int(row.get("velocity", 80)),
            )
            for row in payload["expected_notes"]
        )
        observed = tuple(_observed_from_dict(row) for row in payload.get("observed_events", []))
        default_tempo = [{"tick": 0, "tempo_bpm": 120}]
        tempo_changes = tuple(
            _tempo_from_dict(row) for row in payload.get("tempo_changes", default_tempo)
        )
        timeline = payload.get("timeline") or {}
        ticks_per_quarter = int(
            payload.get("ticks_per_quarter") or timeline.get("ticks_per_quarter") or 480
        )
        return align_performance(
            assignment_id=str(payload["assignment_id"]),
            content_id=str(payload["content_id"]),
            performance_session_id=str(payload["performance_session_id"]),
            expected=expected,
            observed=observed,
            policy=PerformanceAlignmentPolicyV1(),
            ticks_per_quarter=ticks_per_quarter,
            tempo_changes=tempo_changes,
            repetition_count=int(payload.get("repetition_count", 1)),
        )

    def _apply_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        action_type = str(payload["action_type"])
        applied = {
            "action_type": action_type,
            "target_rate": payload.get("target_rate"),
            "focus_start_tick": payload.get("focus_start_tick"),
            "focus_end_tick": payload.get("focus_end_tick"),
            "message_key": payload.get("message_key"),
        }
        self.last_applied_action = applied
        return {"status": "applied", "action": applied}

    def _golden_demo(self) -> dict[str, Any]:
        """Developer/test facility: deterministic three-attempt action sequence."""

        self.history.clear()
        attempts: list[dict[str, Any]] = []
        for filename, expected_action in GOLDEN_DEMO_ATTEMPTS:
            path = _GOLDEN_DIR / filename
            fixture = json.loads(path.read_text(encoding="utf-8"))
            result = self._evaluate(fixture)
            action_value = result["evaluation"]["primary_next_action"]["action_type"]
            actual = PracticeNextActionType(action_value)
            if actual is not expected_action:
                raise EducationContractError(
                    f"golden demo {filename} expected {expected_action.value}, got {actual.value}"
                )
            attempts.append(
                {
                    "fixture": filename,
                    "primary_action": actual.value,
                    "digest": result["evaluation"]["evaluation_digest"],
                }
            )
        return {
            "status": "golden_demo_complete",
            "attempts": attempts,
            "sequence": [action.value for _, action in GOLDEN_DEMO_ATTEMPTS],
            "hardware_status": {
                "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
                "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
            },
        }
