"""Localhost lesson-media API tests."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from master_all_strings.mvp.local_server import serve_mvp_directory

ROOT = Path(__file__).resolve().parents[2]


def test_lesson_media_api_and_asset_serving() -> None:
    server, thread, url = serve_mvp_directory(
        ROOT / "web" / "mvp1",
        open_browser=False,
        port=0,
        media_root=ROOT / "resources" / "media",
    )
    try:
        base = url.rsplit("/", 1)[0]
        with urllib.request.urlopen(f"{base}/api/v1/lessons/half_steps_one_string/media") as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["available_count"] >= 1
        video = next(
            item for item in payload["items"] if item["media"]["media_type"] == "video"
        )
        assert video["public_url"].startswith("/media/assets/")
        with urllib.request.urlopen(f"{base}{video['public_url']}") as asset:
            data = asset.read()
        assert len(data) > 100
        # Path escape must 404
        try:
            urllib.request.urlopen(f"{base}/media/assets/../catalog/lesson_media_catalog_v1.json")
            raised = False
        except Exception:
            raised = True
        assert raised
    finally:
        server.shutdown()
        thread.join(timeout=2)
