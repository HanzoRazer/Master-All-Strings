"""Export MVP projection artifacts for the local web renderer."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from master_all_strings.core.projections.serialization import (
    projection_to_json,
)
from master_all_strings.core.score.serialization import revision_to_dict
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.mvp.demo_library import load_demo_manifest
from master_all_strings.mvp.models import MvpLessonSummaryV1, MvpProjectionResponseV1
from master_all_strings.mvp.playback.serialization import serialize_lesson_playback_plan
from master_all_strings.mvp.practice import loop_ticks_to_seconds
from master_all_strings.mvp.projection.serialization import serialize_fretboard_projection
from master_all_strings.presentation.contracts import PRESENTATION_SCHEMA_VERSION
from master_all_strings.presentation.timeline import (
    anchors_to_payload,
    build_timeline_anchors,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from master_all_strings.mvp.application import MvpApplication

__all__ = [
    "atomic_write_text",
    "export_score_projections",
    "projection_timeline_anchors",
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
    # Platform-default newline translation is deliberate here. Git stores these
    # files with LF and a Windows checkout smudges them to CRLF, so an exporter
    # that always wrote LF would disagree with its own checked-in fixtures on
    # Windows and break the drift guard. Making the bytes platform-independent
    # is a .gitattributes concern, which D21 puts outside this tranche.
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def projection_timeline_anchors(projection: object) -> list[dict[str, float | int]]:
    """Derive the browser's tick-to-second anchor table for one projection.

    Emitted beside the projection rather than inside it. ``FretboardScrollProjectionV1``
    and its digest are deliberately untouched: adding a field there would move
    ``behavior_digest`` and break the frozen DO-008 and DO-009 evidence for a
    presentation concern that carries no musical content.
    """

    timeline = projection.timeline  # type: ignore[attr-defined]
    tempo_changes = tuple(
        TempoChangeV1(
            schema_version=TempoChangeV1.SCHEMA_VERSION,
            tick=change.tick,
            microseconds_per_quarter=change.microseconds_per_quarter,
        )
        for change in projection.tempo_changes  # type: ignore[attr-defined]
    )
    return anchors_to_payload(
        build_timeline_anchors(
            ticks_per_quarter=timeline.ticks_per_quarter,
            tempo_changes=tempo_changes,
            total_ticks=timeline.total_ticks,
        )
    )


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
        "teaching_aids": {
            "one_string": [asdict(item) for item in response.one_string_teaching],
        },
        "projection": json.loads(serialize_fretboard_projection(response.projection)),
        # DO-012: Musical Core authors the tick-to-second mapping; the browser
        # only interpolates within it, so no tick converter lives in JavaScript.
        #
        # The version sits beside the table rather than on every entry: repeating
        # it per anchor would be noise, but omitting it entirely left the leanest
        # contract in the tranche as the only one a reader could not identify.
        # If the meaning of an anchor ever changes, this is what says so.
        "timeline_anchors_schema_version": PRESENTATION_SCHEMA_VERSION,
        "timeline_anchors": projection_timeline_anchors(response.projection),
    }
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path


def export_playback_json(response: MvpProjectionResponseV1, output_path: Path) -> Path:
    atomic_write_text(output_path, serialize_lesson_playback_plan(response.playback_plan))
    return output_path


def export_practice_json(response: MvpProjectionResponseV1, output_path: Path) -> Path:
    loop_start_seconds, loop_end_seconds = loop_ticks_to_seconds(
        response.practice_policy.loop,
        ticks_per_quarter=response.playback_plan.timeline.ticks_per_quarter,
        tempo_changes=response.playback_plan.timeline.tempo_changes,
    )
    payload = {
        "policy": asdict(response.practice_policy),
        "runtime": {
            "loop_start_seconds": loop_start_seconds,
            "loop_end_seconds": loop_end_seconds,
        },
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
                "audio_demo": item.audio_demo,
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
        # Score artifacts live in a per-lesson directory beside the existing flat
        # exports, which stay exactly where their consumers expect them.
        written += len(
            export_score_projections(response, web_root / "projections" / summary.demo_id)
        )
    return written


def export_score_projections(
    response: MvpProjectionResponseV1, lesson_dir: Path
) -> tuple[Path, ...]:
    """Write one lesson's canonical revision and its two score projections.

    The revision is exported, not merely computed. A projection citing a
    revision id nothing stores is decoration: the citation has to be resolvable
    against something a reader can open, which is what this directory is for.

    Returns an empty tuple when the response carries no score bundle, so callers
    that predate DO-013 keep working.
    """

    bundle = response.score
    if bundle is None:
        return ()

    revision_path = lesson_dir / "canonical_revision.json"
    tab_path = lesson_dir / "tab.json"
    notation_path = lesson_dir / "notation.json"

    revision_json = json.dumps(
        revision_to_dict(bundle.revision), indent=2, ensure_ascii=False
    )
    atomic_write_text(revision_path, revision_json + "\n")
    # Each projection is written inside its envelope, so the file carries the
    # revision citation and the digest alongside the payload rather than leaving a
    # reader to recompute either.
    atomic_write_text(tab_path, projection_to_json(bundle.tab))
    atomic_write_text(notation_path, projection_to_json(bundle.notation))
    return (revision_path, tab_path, notation_path)


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
                "audio_demo": e.audio_demo,
                "known_limitations": list(e.known_limitations),
            }
            for e in entries
        ]
    }
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return output_path
