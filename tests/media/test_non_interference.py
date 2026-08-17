"""Musical non-interference: media sidecar must not change MVP musical outputs."""

from __future__ import annotations

from master_all_strings.media.presentation import lesson_media_payload
from master_all_strings.mvp.application import MvpApplication


def test_half_steps_digests_stable_with_media_sidecar_present() -> None:
    app = MvpApplication()
    response = app.run_demo("half_steps_one_string")
    assert (
        response.behavior_digest
        == "sha256:075268cae2e858e93774a59ae3e2d7df8b5b73aaaa4c209069afbe006b1d4878"
    )
    assert (
        response.projection.projection_digest
        == "sha256:398f53a7a9ef4f623742d9e76d582ca196919e60821ed2b7e9a928ac15a5d1df"
    )
    assert (
        response.playback_plan.playback_digest
        == "sha256:f9b578ae35e3d436d027f71f1240e763f844163f561fc6b57f83c86bb05266fd"
    )
    # Media payload is independent of musical digests.
    media = lesson_media_payload("half_steps_one_string")
    assert media["available_count"] >= 1
    assert response.behavior_digest.startswith("sha256:")


def test_ascending_scale_unchanged_when_media_catalog_exists() -> None:
    app = MvpApplication()
    response = app.run_demo("ascending_scale")
    assert (
        response.behavior_digest
        == "sha256:9f86b56c92e9d8e32dbd55275a45b5c4b17e937bad8e4552cb262c73eefd32e9"
    )
    media = lesson_media_payload("ascending_scale")
    assert media["items"] == []
