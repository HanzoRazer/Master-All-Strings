"""Structural tests: renderer JS must not implement musical authority."""

from __future__ import annotations

from pathlib import Path

WEB = Path("web/mvp1")
FORBIDDEN = (
    "generate_candidates",
    "select_candidate",
    "score_fingering",
    "midi_to_fret",
    "fret_for_pitch",
    "tick_to_seconds",
    "tempo_map",
)


def test_renderer_sources_have_no_domain_helpers() -> None:
    for path in WEB.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{path} contains forbidden token {token!r}"


def test_transport_is_anchor_derived() -> None:
    text = (WEB / "transport.js").read_text(encoding="utf-8")
    assert "frame_delta" not in text
    assert "baseSeconds" in text
    assert "anchorWallMs" in text
