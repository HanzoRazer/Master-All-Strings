"""Export MVP projection artifacts for the local web renderer."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from master_all_strings.mvp.demo_library import load_demo_manifest
from master_all_strings.mvp.models import MvpLessonSummaryV1, MvpProjectionResponseV1
from master_all_strings.mvp.playback.serialization import serialize_lesson_playback_plan
from master_all_strings.mvp.projection.serialization import serialize_fretboard_projection

if TYPE_CHECKING:  # pragma: no cover - typing only
    from master_all_strings.mvp.application import MvpApplication

__all__ = [
    "atomic_write_text",
    "export_demo_catalog",
    "export_instrument_catalog",
    "export_playback_json",
    "export_practice_json",
    "export_projection_json",
    "export_web_fixtures",
]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def export_projection_json(
    response: MvpProjectionResponseV1,
    output_path: Path,
    *,
    demo_id: str | None = None,
) -> Path:
    payload = {
        "status": response.status.value,
        # Stable identity for the UI to key on. Titles are display text and must
        # never be used to correlate a payload with its catalog entry.
        "demo_id": demo_id,
        "summary_title": response.summary_title,
        "instrument_id": response.instrument_id,
        "behavior_digest": response.behavior_digest,
        "warnings": list(response.warnings),
        "unsupported_features": list(response.unsupported_features),
        "projection": json.loads(serialize_fretboard_projection(response.projection)),
    }
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path


def export_playback_json(response: MvpProjectionResponseV1, output_path: Path) -> Path:
    atomic_write_text(output_path, serialize_lesson_playback_plan(response.playback_plan))
    return output_path


def export_practice_json(response: MvpProjectionResponseV1, output_path: Path) -> Path:
    payload = asdict(response.practice_policy)
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path


def export_demo_catalog(summaries: tuple[MvpLessonSummaryV1, ...], output_path: Path) -> Path:
    payload = {
        "demos": [
            {
                "demo_id": item.demo_id,
                "title": item.title,
                "description": item.description,
                "instrument_profile_id": item.instrument_profile_id,
                "demonstrates": list(item.demonstrates),
                "known_limitations": list(item.known_limitations),
            }
            for item in summaries
        ]
    }
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path


def export_instrument_catalog(app: MvpApplication, output_path: Path) -> Path:
    payload = [
        {
            "instrument_id": item.instrument_id,
            "display_name": item.display_name,
            "experimental": item.experimental,
        }
        for item in app.list_instruments()
    ]
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path


def export_web_fixtures(app: MvpApplication, web_root: Path) -> int:
    """Write the checked-in static-UI fixture set. Returns the file count.

    This is the single definition of what ``web/mvp1`` carries in git, so the
    drift test and ``scripts/run_mvp1.py --refresh-fixtures`` cannot diverge.
    Ad-hoc CLI runs write elsewhere and never touch these files.
    """

    export_demo_catalog(app.list_demos(), web_root / "demos.json")
    export_instrument_catalog(app, web_root / "instruments.json")
    written = 2
    # Prefetch every bundled demo so the static UI can switch without a backend.
    for summary in app.list_demos():
        response = app.run_demo(
            summary.demo_id,
            instrument_profile_id=summary.instrument_profile_id,
        )
        export_projection_json(
            response,
            web_root / "projections" / f"{summary.demo_id}.json",
            demo_id=summary.demo_id,
        )
        export_playback_json(
            response,
            web_root / "playback" / f"{summary.demo_id}.json",
        )
        export_practice_json(
            response,
            web_root / "practice" / f"{summary.demo_id}.json",
        )
        written += 3
    return written


def export_manifest_copy(output_path: Path) -> Path:
    entries = load_demo_manifest()
    payload = {
        "demos": [
            {
                "demo_id": e.demo_id,
                "title": e.title,
                "description": e.description,
                "instrument_profile_id": e.instrument_profile_id,
                "demonstrates": list(e.demonstrates),
                "known_limitations": list(e.known_limitations),
            }
            for e in entries
        ]
    }
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path
