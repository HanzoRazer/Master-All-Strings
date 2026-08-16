"""Localhost-only JSON facade over authoritative Python performance services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from master_all_strings.performance.capture_normalization import (
    append_events,
    build_raw_capture,
    close_capture,
    normalize_midi_event,
)
from master_all_strings.performance.contracts.capture import (
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import RuntimeIdentityV1, RuntimeKind
from master_all_strings.performance.contracts.session import MeterV1
from master_all_strings.performance.export import to_dict
from master_all_strings.performance.note_pairing import pair_midi_notes


@dataclass
class LocalPerformanceCaptureApi:
    capture: RawPerformanceCaptureV1 | None = None
    device_id: str | None = None
    repetitions: dict[str, int] = field(default_factory=dict)
    practice_onsets: dict[str, float] = field(default_factory=dict)

    def handle(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "arm":
            self.device_id = str(payload["device_id"])
            return {"status": "armed"}
        if action == "start":
            if not self.device_id:
                raise PerformanceContractError("MIDI input is not armed")
            session = str(uuid4())
            capture_id = str(uuid4())
            self.capture = build_raw_capture(
                capture_id=capture_id,
                session_id=session,
                runtime_identity=RuntimeIdentityV1(
                    "1.0.0", "web-midi", RuntimeKind.LIGHTWEIGHT, "1", "web-midi-v1", True
                ),
                source_identity=CaptureSourceV1(
                    "1.0.0", self.device_id, "browser", self.device_id, False
                ),
                started_at="2026-08-12T00:00:00Z",
                tempo_context=120,
                meter_context=MeterV1("1.0.0", 4, 4),
                provenance=(("clock_domain", "browser_performance_time"),),
            )
            self._reset_session_maps()
            return {
                "status": "capturing",
                "capture_id": capture_id,
                "performance_session_id": session,
            }
        if action == "message":
            return self._message(payload)
        if action in {"stop", "interrupt"}:
            return self._close(interrupted=action == "interrupt")
        raise PerformanceContractError(f"unknown performance action {action!r}")

    def _reset_session_maps(self) -> None:
        self.repetitions.clear()
        self.practice_onsets.clear()

    @staticmethod
    def _midi_event_type(status_kind: int, velocity: int) -> MidiEventType:
        # MIDI: note-on (0x90) with velocity 0 is a note-off by convention (Web MIDI).
        if status_kind == 0x80 or (status_kind == 0x90 and velocity == 0):
            return MidiEventType.NOTE_OFF
        return MidiEventType.NOTE_ON

    def _message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.capture is None or self.capture.is_closed:
            raise PerformanceContractError("no active capture")
        raw = tuple(int(v) for v in payload["raw_payload"])
        status = raw[0]
        kind = status & 0xF0
        if kind not in (0x80, 0x90) or len(raw) < 3:
            raise PerformanceContractError("DO-009 accepts MIDI note messages only")
        velocity = raw[2]
        event = normalize_midi_event(
            event_id=str(uuid4()),
            sequence_number=len(self.capture.events),
            event_type=self._midi_event_type(kind, velocity),
            capture_time_ns=int(payload["capture_time_ns"]),
            channel=status & 0x0F,
            source_port="browser",
            source_device=str(payload["device_id"]),
            note=raw[1],
            velocity=velocity,
            raw_payload=raw,
        )
        self.repetitions[event.event_id] = int(payload.get("repetition_index", 0))
        onset = payload.get("practice_position_seconds")
        if onset is not None:
            self.practice_onsets[event.event_id] = float(onset)
        self.capture = append_events(self.capture, (event,))
        return {"status": "capturing", "event_count": len(self.capture.events)}

    def _close(self, *, interrupted: bool) -> dict[str, Any]:
        if self.capture is None or self.capture.is_closed:
            raise PerformanceContractError("no active capture")
        from dataclasses import replace

        from master_all_strings.performance.contracts.capture import CaptureCompletionState

        self.capture = close_capture(
            self.capture,
            ended_at="2026-08-12T00:00:01Z",
            completion_state=CaptureCompletionState.INTERRUPTED
            if interrupted
            else CaptureCompletionState.COMPLETE,
        )
        paired = pair_midi_notes(
            self.capture,
            observed_id_factory=lambda _: str(uuid4()),
            repetition_resolver=lambda e: self.repetitions.get(e.event_id, 0),
        )
        observed = []
        for note in paired.observed_notes:
            onset = self.practice_onsets.get(note.note_on_event_id)
            if onset is None:
                observed.append(note)
            else:
                observed.append(replace(note, practice_onset_seconds=onset))
        result = {
            "status": self.capture.completion_state.value,
            "raw_capture": to_dict(self.capture),
            "observed_events": [to_dict(n) for n in observed],
            "unmatched_note_offs": [to_dict(n) for n in paired.unmatched_note_offs],
        }
        self._reset_session_maps()
        return result
