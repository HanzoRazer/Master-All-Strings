#!/usr/bin/env python3
"""Launch Master All Strings MVP-1F headlessly or with a localhost browser UI."""

from __future__ import annotations

import argparse
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
from master_all_strings.mvp.performance_api import LocalPerformanceCaptureApi  # noqa: E402
from master_all_strings.mvp.web_export import (  # noqa: E402
    export_playback_json,
    export_practice_json,
    export_projection_json,
    export_web_fixtures,
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
        default=_REPO_ROOT / "web" / "mvp1" / "runtime" / "projection.json",
        help="Projection JSON output path (default: gitignored web/mvp1/runtime/)",
    )
    parser.add_argument(
        "--refresh-fixtures",
        action="store_true",
        help=(
            "Regenerate the checked-in demo exports under web/mvp1/ "
            "(demos.json, instruments.json, projections/). Off by default so "
            "ordinary runs never dirty tracked fixtures."
        ),
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

    export_projection_json(response, args.output, demo_id=args.lesson)
    export_playback_json(response, args.output.with_name("playback.json"))
    export_practice_json(response, args.output.with_name("practice.json"))
    if args.refresh_fixtures:
        written = export_web_fixtures(app, _REPO_ROOT / "web" / "mvp1")
        print(f"refreshed {written} checked-in fixture files under web/mvp1/")

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
        # Point the UI straight at this run's export when it lands inside the
        # served tree; otherwise the UI opens its checked-in default demo.
        path = "/index.html"
        try:
            relative = args.output.resolve().relative_to(web_root.resolve())
        except ValueError:
            print(
                f"note: {args.output} is outside {web_root}; "
                "the browser will show the default demo instead",
                file=sys.stderr,
            )
        else:
            path = f"/index.html?projection={relative.as_posix()}"
        server, _thread, url = serve_mvp_directory(
            web_root,
            port=args.port,
            open_browser=args.open_browser and not args.no_browser,
            path=path,
            performance_api=LocalPerformanceCaptureApi(),
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
