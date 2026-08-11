#!/usr/bin/env python3
"""Launch Master All Strings MVP-1F headlessly or with a localhost browser UI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from master_all_strings.mvp.application import MvpApplication  # noqa: E402
from master_all_strings.mvp.errors import MvpError, format_mvp_error  # noqa: E402
from master_all_strings.mvp.local_server import serve_mvp_directory  # noqa: E402
from master_all_strings.mvp.web_export import (  # noqa: E402
    export_demo_catalog,
    export_projection_json,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Master All Strings MVP-1")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--lesson", help="Bundled demo id")
    source.add_argument("--midi", type=Path, help="Path to a supported MIDI file")
    parser.add_argument(
        "--instrument",
        default="guitar-standard-6",
        help="Instrument profile id (default: guitar-standard-6)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "web" / "mvp1" / "projection.json",
        help="Projection JSON output path",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Serve web/mvp1 on localhost and open a browser",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="With --open, serve but do not launch a browser",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Optional localhost port for --open",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app = MvpApplication()
    try:
        if args.lesson:
            response = app.run_demo(args.lesson, instrument_profile_id=args.instrument)
        else:
            midi_path: Path = args.midi
            response = app.run_midi(
                midi_path.read_bytes(),
                instrument_profile_id=args.instrument,
                assignment_id=f"midi-{midi_path.stem}",
                source_name=midi_path.name,
                title=midi_path.stem,
            )
    except MvpError as exc:
        print(format_mvp_error(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Unable to load lesson: {exc}", file=sys.stderr)
        return 1

    export_projection_json(response, args.output)
    catalog_path = args.output.parent / "demos.json"
    export_demo_catalog(app.list_demos(), catalog_path)
    instruments_path = args.output.parent / "instruments.json"
    instruments_path.write_text(
        json.dumps(
            [
                {
                    "instrument_id": item.instrument_id,
                    "display_name": item.display_name,
                    "experimental": item.experimental,
                }
                for item in app.list_instruments()
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Prefetch every bundled demo so the static UI can switch without a backend.
    projections_dir = args.output.parent / "projections"
    projections_dir.mkdir(parents=True, exist_ok=True)
    for summary in app.list_demos():
        demo_response = app.run_demo(
            summary.demo_id,
            instrument_profile_id=summary.instrument_profile_id,
        )
        export_projection_json(
            demo_response,
            projections_dir / f"{summary.demo_id}.json",
        )

    print(f"title: {response.summary_title}")
    print(f"instrument: {response.instrument_id}")
    print(f"behavior_digest: {response.behavior_digest}")
    print(f"projection_digest: {response.projection.projection_digest}")
    print(f"wrote: {args.output}")
    if response.warnings:
        print("warnings:")
        for warning in response.warnings:
            print(f"  - {warning}")

    if args.open_browser or args.no_browser:
        web_root = _REPO_ROOT / "web" / "mvp1"
        server, _thread, url = serve_mvp_directory(
            web_root,
            port=args.port,
            open_browser=args.open_browser and not args.no_browser,
        )
        print(f"serving: {url}")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            server.shutdown()
            print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
