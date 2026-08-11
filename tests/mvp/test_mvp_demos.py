"""Demo library digest pins."""

from __future__ import annotations

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_manifest


def test_all_demos_match_manifest_digests(app: MvpApplication) -> None:
    for entry in load_demo_manifest():
        response = app.run_demo(entry.demo_id)
        assert entry.expected_behavior_digest == response.behavior_digest
        assert entry.expected_projection_digest == response.projection.projection_digest
        assert entry.audio_demo is True
        assert entry.expected_playback_digest == response.playback_plan.playback_digest
