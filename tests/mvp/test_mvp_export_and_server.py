"""Web export and localhost server coverage."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import (
    load_demo_manifest,
    resolve_demo_midi_path,
)
from master_all_strings.mvp.local_server import find_available_local_port, serve_mvp_directory
from master_all_strings.mvp.web_export import (
    export_demo_catalog,
    export_manifest_copy,
    export_playback_json,
    export_practice_json,
    export_projection_json,
)


def test_export_projection_and_catalog(app: MvpApplication, tmp_path: Path) -> None:
    response = app.run_demo("ascending_scale")
    out = tmp_path / "projection.json"
    export_projection_json(response, out)
    payload = out.read_text(encoding="utf-8")
    assert "fretboard_scroll" in payload
    assert response.projection.projection_digest in payload

    playback = tmp_path / "playback.json"
    export_playback_json(response, playback)
    assert response.playback_plan.playback_digest in playback.read_text(encoding="utf-8")

    practice = tmp_path / "practice.json"
    export_practice_json(response, practice)
    assert '"count_in_bars": 0' in practice.read_text(encoding="utf-8")

    catalog = tmp_path / "demos.json"
    export_demo_catalog(app.list_demos(), catalog)
    assert "ascending_scale" in catalog.read_text(encoding="utf-8")

    manifest_copy = tmp_path / "manifest_copy.json"
    export_manifest_copy(manifest_copy)
    assert "teacher_override" in manifest_copy.read_text(encoding="utf-8")


def test_list_demos_and_instruments(app: MvpApplication) -> None:
    demos = app.list_demos()
    assert any(item.demo_id == "open_strings" for item in demos)
    instruments = app.list_instruments()
    assert any(
        item.instrument_id == "guitar-standard-6" and not item.experimental
        for item in instruments
    )
    assert any(item.experimental for item in instruments)


def test_resolve_demo_midi_path() -> None:
    path = resolve_demo_midi_path("ascending_scale")
    assert path is not None
    assert path.is_file()
    assert resolve_demo_midi_path("teacher_override") is None


def test_manifest_entries_expose_summaries() -> None:
    entry = load_demo_manifest()[0]
    summary = entry.to_summary()
    assert summary.demo_id == entry.demo_id
    assert summary.title == entry.title


def test_local_server_serves_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    port = find_available_local_port()
    server, _thread, url = serve_mvp_directory(tmp_path, port=port, open_browser=False)
    try:
        with urlopen(url, timeout=2) as response:  # noqa: S310 - localhost test
            body = response.read().decode("utf-8")
        assert "ok" in body
    finally:
        server.shutdown()
