"""DO-010 MVP education API and golden demo."""

from __future__ import annotations

from master_all_strings.mvp.education_api import LocalPracticeEvaluationApi


def test_golden_demo_sequence() -> None:
    api = LocalPracticeEvaluationApi()
    result = api.handle("golden_demo", {})
    assert result["sequence"] == ["slow_down", "isolate_passage", "continue"]
    assert result["hardware_status"]["midi_input"] == "UNVERIFIED_PHYSICAL_MIDI_INPUT"
    assert result["hardware_status"]["audio_output"] == "UNVERIFIED_AUDIO_OUTPUT"


def test_evaluate_aligned_payload_and_apply_action() -> None:
    api = LocalPracticeEvaluationApi()
    api.handle(
        "begin_lesson",
        {"assignment_id": "a1", "content_id": "c1"},
    )
    result = api.handle(
        "evaluate",
        {
            "assignment_id": "a1",
            "content_id": "c1",
            "performance_session_id": "p1",
            "aligned_events": [
                {
                    "status": "matched_exact_pitch",
                    "expected_event_id": "ev-1",
                    "observed_event_id": "obs-1",
                    "repetition_index": 0,
                    "timing_delta_ms": 0,
                    "pitch_delta_semitones": 0,
                    "expected_start_tick": 0,
                }
            ],
        },
    )
    assert result["evaluation"]["primary_next_action"]["action_type"] == "continue"
    assert "action.continue" in result["messages"]
    applied = api.handle(
        "apply_action",
        result["evaluation"]["primary_next_action"],
    )
    assert applied["status"] == "applied"
    session = api.handle("session", {})
    assert session["attempt_count"] == 1
    assert api.handle("get", {})["evaluation"]["evaluation_digest"].startswith("sha256:")


def test_evaluate_from_expected_and_observed_notes() -> None:
    api = LocalPracticeEvaluationApi()
    result = api.handle(
        "evaluate",
        {
            "assignment_id": "a1",
            "content_id": "c1",
            "performance_session_id": "p2",
            "timeline": {"ticks_per_quarter": 480},
            "tempo_changes": [{"tick": 0, "tempo_bpm": 120}],
            "expected_notes": [
                {
                    "event_id": "ev-1",
                    "midi_note": 60,
                    "onset_tick": 0,
                    "duration_ticks": 480,
                },
                {
                    "event_id": "ev-2",
                    "midi_note": 62,
                    "onset_tick": 480,
                    "duration_ticks": 480,
                },
            ],
            "observed_events": [
                {
                    "schema_version": "1.0.0",
                    "observed_event_id": "o1",
                    "capture_id": "c",
                    "note_on_event_id": "on1",
                    "note_off_event_id": "off1",
                    "midi_note": 60,
                    "velocity": 90,
                    "channel": 0,
                    "source_device": "d",
                    "note_on_time_ns": 1,
                    "note_off_time_ns": 2,
                    "duration_ns": 1,
                    "source_string": None,
                    "status": "complete",
                    "repetition_index": 0,
                    "practice_onset_seconds": 0.0,
                    "estimated_start_tick": 0,
                },
                {
                    "schema_version": "1.0.0",
                    "observed_event_id": "o2",
                    "capture_id": "c",
                    "note_on_event_id": "on2",
                    "note_off_event_id": "off2",
                    "midi_note": 63,
                    "velocity": 90,
                    "channel": 0,
                    "source_device": "d",
                    "note_on_time_ns": 3,
                    "note_off_time_ns": 4,
                    "duration_ns": 1,
                    "source_string": None,
                    "status": "complete",
                    "repetition_index": 0,
                    "practice_onset_seconds": 0.5,
                    "estimated_start_tick": 480,
                },
            ],
        },
    )
    types = {f["finding_type"] for f in result["evaluation"]["findings"]}
    assert "pitch_difference" in types
