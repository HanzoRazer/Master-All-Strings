from master_all_strings.mvp.performance_api import LocalPerformanceCaptureApi


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
