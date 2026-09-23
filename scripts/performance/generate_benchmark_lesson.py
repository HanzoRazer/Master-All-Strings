#!/usr/bin/env python3
"""Deterministic benchmark workloads for MAS-PERF-001.

One event count in, one identical workload out, every time. Measurements
compared across runs, machines or months are only comparable if the input is
the same, so nothing here reads a clock, a random source or the filesystem.

The grammar is written once, here, and mirrored in
``web/mvp1/tests/performance/benchmark-fixtures.js`` for the Node benchmarks.
A test asserts the two produce the same digest for the same count -- otherwise
the two halves of this tranche would be measuring different lessons while
reporting one number each.

All times are integer milliseconds and all pitches integer MIDI notes. Floats
would invite the two implementations to disagree in the last bit and turn a
determinism test into a tolerance argument.

This is not a product fixture. A ten-thousand-event lesson is not a demo, and
nothing generated here belongs in the demo manifest or the browser catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

__all__ = [
    "WORKLOAD_SIZES",
    "WORKLOAD_VERSION",
    "build_benchmark_events",
    "build_benchmark_workload",
    "workload_digest",
]

#: Bump when the grammar changes. Recorded beside every measurement, because a
#: number measured against a different workload is a different number.
WORKLOAD_VERSION = "1.0.0"

#: The shared vocabulary. Later work says "at 1,000" and means this.
WORKLOAD_SIZES = (100, 1000, 10000)

_STRINGS = 6
_STEP_MS = 250
_MIN_DURATION_MS = 200


def build_benchmark_events(count: int) -> list[dict[str, Any]]:
    """``count`` events on a six-string instrument, spaced and fretted by rule.

    Uniform enough to be reproducible, varied enough that the renderer and the
    score views do real work: notes land on every string, durations differ, and
    some events overlap their neighbours the way a chord or a ring-out does.
    """

    if count < 0:
        raise ValueError("count must not be negative")
    events = []
    for index in range(count):
        string_index = index % _STRINGS
        fret = (index * 7) % 13
        onset_ms = index * _STEP_MS
        duration_ms = _MIN_DURATION_MS + (index % 4) * 50
        events.append(
            {
                "event_id": f"bench-ev-{index:05d}",
                "canonical_event_id": f"bench-canonical-{index:05d}",
                "onset_ms": onset_ms,
                "release_ms": onset_ms + duration_ms,
                "midi_note": 40 + string_index * 5 + fret,
                "string_index": string_index,
                "fret": fret,
                "velocity": 64 + (index % 8) * 4,
            }
        )
    return events


def build_benchmark_workload(count: int) -> dict[str, Any]:
    """The events plus the metadata that makes a measurement citable."""

    events = build_benchmark_events(count)
    return {
        "workload_version": WORKLOAD_VERSION,
        "event_count": count,
        "total_ms": events[-1]["release_ms"] if events else 0,
        "strings": _STRINGS,
        "events": events,
    }


def _canonical(workload: dict[str, Any]) -> bytes:
    return json.dumps(workload, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )


def workload_digest(workload: dict[str, Any]) -> str:
    """Identity of a workload, recorded with every measurement taken on it."""

    return "sha256:" + hashlib.sha256(_canonical(workload)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=1000, help="event count to generate")
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the digest only; generate nothing on disk",
    )
    parser.add_argument("--output", help="write the workload JSON here instead of stdout")
    args = parser.parse_args(argv)

    workload = build_benchmark_workload(args.events)
    digest = workload_digest(workload)
    if args.check:
        print(f"workload {args.events}: {digest}")
        return 0
    text = json.dumps(workload, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {args.output} ({digest})")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
