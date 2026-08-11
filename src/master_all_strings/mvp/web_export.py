"""Export MVP projection artifacts for the local web renderer."""

from __future__ import annotations

import json
import os
from pathlib import Path

from master_all_strings.mvp.demo_library import load_demo_manifest
from master_all_strings.mvp.models import MvpLessonSummaryV1, MvpProjectionResponseV1
from master_all_strings.mvp.projection.serialization import serialize_fretboard_projection

__all__ = ["atomic_write_text", "export_demo_catalog", "export_projection_json"]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def export_projection_json(response: MvpProjectionResponseV1, output_path: Path) -> Path:
    payload = {
        "status": response.status.value,
        "summary_title": response.summary_title,
        "instrument_id": response.instrument_id,
        "behavior_digest": response.behavior_digest,
        "warnings": list(response.warnings),
        "unsupported_features": list(response.unsupported_features),
        "projection": json.loads(serialize_fretboard_projection(response.projection)),
    }
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
