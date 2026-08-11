#!/usr/bin/env python3
"""Build and verify the local DO-008 three-repository integration stack."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

EXPECTED_STRING_MASTER_SHA = "5d7af1d0efcd026c8cdf861c8a0f8467d77ee03e"
EXPECTED_SG_AGENTD_SHA = "ae7a58fff0f0cc136ee22434282899ceb811a5d3"


def _sha(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--string-master", type=Path, required=True)
    parser.add_argument("--sg-agentd", type=Path, required=True)
    parser.add_argument("--web-output", type=Path, required=True)
    parser.add_argument("--evidence-bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    mas_root = Path(__file__).resolve().parents[1]
    string_root = args.string_master.resolve()
    agentd_root = args.sg_agentd.resolve()
    repository_shas = {
        "string_master": _sha(string_root),
        "sg_agentd": _sha(agentd_root),
        "master_all_strings_base": _sha(mas_root),
    }
    if repository_shas["string_master"] != EXPECTED_STRING_MASTER_SHA:
        raise SystemExit("String Master is not at the tested DO-008 authority SHA")
    if repository_shas["sg_agentd"] != EXPECTED_SG_AGENTD_SHA:
        raise SystemExit("sg-agentd is not at the tested DO-008 assembly SHA")

    sys.path[0:0] = [
        str(mas_root / "src"),
        str(agentd_root),
        str(string_root / "src"),
    ]

    from sg_agentd.services.generation import generate_clip  # type: ignore[import-untyped]
    from zt_band.engine import generate_accompaniment  # type: ignore[import-untyped]
    from zt_band.zone_semantic_bridge import zone_event_id  # type: ignore[import-untyped]

    from master_all_strings.core.musical_events import MusicalEvent
    from master_all_strings.core.score.tempo import TempoChangeV1
    from master_all_strings.core.spatial_mapping import (
        generate_candidates,
        instrument_profile_from_mapping,
    )
    from master_all_strings.integrations.zone_harmony import (
        apply_zone_semantics_to_projection,
        correlate_zone_semantics,
        load_zone_semantics_from_bundle,
    )
    from master_all_strings.mvp.models import MvpLoadStatus, MvpProjectionResponseV1
    from master_all_strings.mvp.playback import build_lesson_playback_plan
    from master_all_strings.mvp.practice import build_practice_session_policy
    from master_all_strings.mvp.projection.builder import (
        SelectedNoteInput,
        build_fretboard_scroll_projection,
    )
    from master_all_strings.mvp.projection.models import SelectionOrigin
    from master_all_strings.mvp.teaching_aids import build_one_string_teaching_projection
    from master_all_strings.mvp.web_export import (
        export_playback_json,
        export_practice_json,
        export_projection_json,
    )

    # The Cmaj7 -> Fmaj7 boundary exposes an authoritative tritone anchor, while
    # the repeated Fmaj7 voicing exposes the half-step crossing teaching case.
    chords = ["Cmaj7", "Fmaj7", "G7"]
    tempo_bpm = 96
    with tempfile.TemporaryDirectory() as temporary:
        generated = generate_clip(
            request_id="do008-stack-proof",
            chord_symbols=chords,
            tempo_bpm=tempo_bpm,
            tritone_seed=17,
            output_dir=temporary,
        )
        bundle_dir = Path(generated["bundle_dir"])
        semantics = load_zone_semantics_from_bundle(bundle_dir)
        if semantics is None:
            raise SystemExit("sg-agentd did not emit Zone semantics")

        comp_events, bass_events = generate_accompaniment(
            chords,
            tempo_bpm=tempo_bpm,
            tritone_seed=17,
        )
        event_rows = [
            (zone_event_id("comp", index), event)
            for index, event in enumerate(comp_events)
        ] + [
            (zone_event_id("bass", index), event)
            for index, event in enumerate(bass_events)
        ]
        canonical_events = tuple(
            MusicalEvent(
                event_id=event_id,
                midi_note=event.midi_note,
                start_tick=round(event.start_beats * 480),
                duration_ticks=max(1, round(event.duration_beats * 480)),
                velocity=event.velocity,
            )
            for event_id, event in event_rows
        )
        correlated = correlate_zone_semantics(canonical_events, semantics)

        instrument_path = mas_root / "resources/instruments/examples/guitar-standard-6.json"
        instrument = instrument_profile_from_mapping(
            json.loads(instrument_path.read_text(encoding="utf-8"))
        )
        selected_notes = []
        normal_candidate_rows = []
        for event in canonical_events:
            candidates = generate_candidates(event, instrument)
            normal_candidate_rows.append(tuple(asdict(candidate) for candidate in candidates))
            if candidates:
                selected_notes.append(
                    SelectedNoteInput(
                        event,
                        position=candidates[0],
                        selection_origin=SelectionOrigin.AUTOMATIC,
                    )
                )
            else:
                selected_notes.append(
                    SelectedNoteInput(event, unresolved_reason="no_playable_position")
                )

        tempo_map = (
            TempoChangeV1(
                schema_version="1.0.0",
                tick=0,
                microseconds_per_quarter=round(60_000_000 / tempo_bpm),
            ),
        )
        plain_projection = build_fretboard_scroll_projection(
            assignment_id="do008-stack-proof",
            content_id="do008_zone_harmony",
            title="DO-008 Zone Harmony",
            description="Three-repository Zone semantic integration proof",
            objective="Hear, see, slow, loop, and inspect Zone relationships",
            teacher_note="Reference Synth; Zone semantics originate in String Master",
            ticks_per_quarter=480,
            tempo_map=tempo_map,
            instrument=instrument,
            selection_policy="enumeration_v1",
            selected_notes=selected_notes,
        )
        decorated_projection = apply_zone_semantics_to_projection(plain_projection, correlated)
        plain_spatial = tuple(
            (note.event_id, note.string_id, note.fret_number, note.onset_tick)
            for note in plain_projection.notes
        )
        decorated_spatial = tuple(
            (note.event_id, note.string_id, note.fret_number, note.onset_tick)
            for note in decorated_projection.notes
        )
        if plain_spatial != decorated_spatial:
            raise SystemExit("Zone semantics changed the normal MSME spatial result")

        teaching = tuple(
            build_one_string_teaching_projection(
                canonical_events,
                instrument,
                string_id=string.string_id,
            )
            for string in sorted(instrument.strings, key=lambda item: item.display_order)
        )
        playback = build_lesson_playback_plan(
            assignment_id="do008-stack-proof",
            content_id="do008_zone_harmony",
            events=canonical_events,
            ticks_per_quarter=480,
            tempo_changes=tempo_map,
        )
        practice = build_practice_session_policy(
            assignment_id="do008-stack-proof",
            content_id="do008_zone_harmony",
            lesson_end_tick=playback.timeline.total_ticks,
            loop_enabled=True,
            loop_start_tick=0,
            loop_end_tick=playback.timeline.total_ticks,
            count_in_bars=1,
            target_repetitions=3,
        )
        response = MvpProjectionResponseV1(
            status=MvpLoadStatus.READY,
            summary_title="DO-008 Zone Harmony",
            instrument_id=instrument.instrument_id,
            behavior_digest=generated["zone_semantics_sha256"],
            projection=decorated_projection,
            playback_plan=playback,
            practice_policy=practice,
            one_string_teaching=teaching,
        )
        args.web_output.mkdir(parents=True, exist_ok=True)
        export_projection_json(response, args.web_output / "projection.json", demo_id="do008")
        export_playback_json(response, args.web_output / "playback.json")
        export_practice_json(response, args.web_output / "practice.json")

        if args.evidence_bundle.exists():
            shutil.rmtree(args.evidence_bundle)
        args.evidence_bundle.mkdir(parents=True)
        shutil.copy2(bundle_dir / "zone_semantics.json", args.evidence_bundle)
        source_manifest = json.loads(
            (bundle_dir / "clip.bundle.json").read_text(encoding="utf-8")
        )
        semantic_entry = source_manifest["extensions"]["zone_semantics"]
        evidence_manifest = {
            "schema_id": "do008_semantic_evidence_bundle",
            "schema_version": "1.0",
            "artifacts": [],
            "extensions": {"zone_semantics": semantic_entry},
        }
        (args.evidence_bundle / "clip.bundle.json").write_text(
            json.dumps(evidence_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (args.evidence_bundle / "canonical_events.json").write_text(
            json.dumps([asdict(event) for event in canonical_events], indent=2) + "\n",
            encoding="utf-8",
        )

        semantic_roles = {
            role.value for event in semantics.events for role in event.semantic_roles
        }
        report = {
            "dev_order": "DO-008",
            "repository_shas": repository_shas,
            "string_master_expected_sha": EXPECTED_STRING_MASTER_SHA,
            "sg_agentd_expected_sha": EXPECTED_SG_AGENTD_SHA,
            "source_bundle_id": semantics.provenance.source_bundle_id,
            "semantic_artifact_sha256": generated["zone_semantics_sha256"],
            "bundle_manifest_sha256": generated["bundle_manifest_sha256"],
            "event_count": len(canonical_events),
            "semantic_event_count": len(semantics.events),
            "normal_spatial_result_unchanged": plain_spatial == decorated_spatial,
            "msme_candidate_event_count": len(normal_candidate_rows),
            "zone_ids": sorted({event.zone_id.value for event in semantics.events}),
            "semantic_roles": sorted(semantic_roles),
            "one_string_projection_count": len(teaching),
            "one_string_unplayable_count": sum(
                event.status.value == "unplayable"
                for projection in teaching
                for event in projection.events
            ),
            "count_in_policy": "preserved; audible count-in deferred",
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
