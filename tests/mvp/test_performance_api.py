from master_all_strings.mvp.performance_api import LocalPerformanceCaptureApi
from master_all_strings.performance.contracts.capture import MidiEventType


def test_local_api_preserves_raw_and_pairs_in_python():
    api = LocalPerformanceCaptureApi()
    api.handle("arm", {"device_id": "d"})
    api.handle("start", {})
    api.handle(
        "message",
        {
            "capture_time_ns": 1,
            "raw_payload": [144, 60, 90],
            "device_id": "d",
            "repetition_index": 2,
            "practice_position_seconds": 1.25,
        },
    )
    api.handle(
        "message",
        {
            "capture_time_ns": 2,
            "raw_payload": [128, 60, 0],
            "device_id": "d",
            "repetition_index": 2,
        },
    )
    result = api.handle("stop", {})
    assert result["status"] == "complete" and result["observed_events"][0]["repetition_index"] == 2
    assert result["observed_events"][0]["practice_onset_seconds"] == 1.25


def test_note_on_velocity_zero_is_classified_as_note_off():
    api = LocalPerformanceCaptureApi()
    api.handle("arm", {"device_id": "d"})
    api.handle("start", {})
    api.handle(
        "message",
        {
            "capture_time_ns": 1,
            "raw_payload": [0x90, 60, 90],
            "device_id": "d",
            "practice_position_seconds": 0.5,
        },
    )
    api.handle(
        "message",
        {
            "capture_time_ns": 2,
            "raw_payload": [0x90, 60, 0],
            "device_id": "d",
        },
    )
    result = api.handle("stop", {})
    events = result["raw_capture"]["events"]
    assert events[0]["event_type"] == MidiEventType.NOTE_ON.value
    assert events[1]["event_type"] == MidiEventType.NOTE_OFF.value
    assert len(result["observed_events"]) == 1
    assert result["observed_events"][0]["practice_onset_seconds"] == 0.5


def test_session_maps_reset_on_start_and_after_close():
    api = LocalPerformanceCaptureApi()
    api.handle("arm", {"device_id": "d"})
    api.handle("start", {})
    api.handle(
        "message",
        {
            "capture_time_ns": 1,
            "raw_payload": [0x90, 60, 90],
            "device_id": "d",
            "repetition_index": 7,
            "practice_position_seconds": 3.0,
        },
    )
    assert api.repetitions and api.practice_onsets
    api.handle("stop", {})
    assert api.repetitions == {}
    assert api.practice_onsets == {}

    api.handle("start", {})
    assert api.repetitions == {}
    assert api.practice_onsets == {}
    api.handle(
        "message",
        {
            "capture_time_ns": 1,
            "raw_payload": [0x90, 64, 80],
            "device_id": "d",
            "repetition_index": 1,
            "practice_position_seconds": 0.1,
        },
    )
    api.handle(
        "message",
        {
            "capture_time_ns": 2,
            "raw_payload": [0x80, 64, 0],
            "device_id": "d",
            "repetition_index": 1,
        },
    )
    result = api.handle("stop", {})
    assert result["observed_events"][0]["repetition_index"] == 1
    assert result["observed_events"][0]["practice_onset_seconds"] == 0.1
