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

AUDIO_FORBIDDEN = (
    "string_id",
    "fret_number",
    "selection_origin",
    "generate_candidates",
    "tempo_bpm",
    "ticks_per_quarter",
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


def test_browser_audio_has_no_spatial_or_tempo_authority() -> None:
    for filename in ("audio.js", "audio_scheduler.js"):
        text = (WEB / filename).read_text(encoding="utf-8")
        for token in AUDIO_FORBIDDEN:
            assert token not in text, f"{filename} contains forbidden token {token!r}"


def test_browser_never_converts_ticks_or_tempo() -> None:
    for path in WEB.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert "microseconds_per_quarter" not in text
        assert "ticks_per_quarter" not in text


def test_zone_renderer_contains_no_zone_or_tritone_calculation() -> None:
    text = (WEB / "renderer.js").read_text(encoding="utf-8")
    for forbidden in ("% 2", "%2", "+ 6", "+6", "midi_note %", "interval_semitones"):
        assert forbidden not in text
    assert "zone_id" in text
    assert "semantic_roles" in text


def test_official_zone_palette_is_presentation_css_only() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8").lower()
    for color in ("#1a4d8f", "#d4860f", "#c41e3a", "#2e8b57"):
        assert color in css
