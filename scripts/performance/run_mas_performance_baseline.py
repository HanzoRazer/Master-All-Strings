#!/usr/bin/env python3
"""Run every MAS-PERF-001 benchmark and write one baseline.

Numbers taken on different days, by different commands, on a machine doing
different things are not a baseline -- they are anecdotes with decimal points.
This runs the approved benchmarks in one pass, captures what the machine was,
and writes a single evidence file that a later comparison can be made against.

It runs benchmarks. It does not edit product files, and it asserts that the
working tree is unchanged by its own run.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BROWSER_BENCH_DIR = REPO_ROOT / "web" / "mvp1" / "tests" / "performance"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "performance" / "MAS_RUNTIME_PERFORMANCE_BASELINE.json"

EVIDENCE_SCHEMA_VERSION = "1.0.0"

NODE_BENCHMARKS = (
    ("audio_scheduler", "audio_scheduler_bench.mjs"),
    ("fretboard_renderer", "renderer_frame_bench.mjs"),
    ("score_views", "score_view_bench.mjs"),
)


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def environment_metadata() -> dict[str, Any]:
    """What the machine was. A measurement without this is not comparable."""

    node_version = ""
    try:
        node_version = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, check=False, timeout=60
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        node_version = "NOT_AVAILABLE"
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "NOT_AVAILABLE",
        "python_version": platform.python_version(),
        "node_version": node_version or "NOT_AVAILABLE",
        "repository_sha": _git("rev-parse", "HEAD") or "NOT_AVAILABLE",
        "working_tree_clean": _git("status", "--porcelain") == "",
        # Node has no Linux CI here. Saying otherwise would imply coverage
        # this repository does not have.
        "node_measurement_platform": platform.system(),
        "linux_node_measurement": "NOT_PRESENT",
    }


def run_node_benchmark(script: str, quick: bool) -> dict[str, Any]:
    started = time.perf_counter_ns()
    result = subprocess.run(
        ["node", script],
        cwd=BROWSER_BENCH_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=3600,
    )
    elapsed_s = (time.perf_counter_ns() - started) / 1_000_000_000
    if result.returncode != 0:
        return {"status": "FAILED", "stderr": result.stderr[-2000:], "elapsed_s": elapsed_s}
    payload = json.loads(result.stdout)
    payload["status"] = "OK"
    payload["elapsed_s"] = elapsed_s
    payload["quick"] = quick
    return payload


def run_python_benchmarks(quick: bool) -> dict[str, Any]:
    """The Python lookups, at the full workload sizes."""

    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(REPO_ROOT / "tests" / "performance"))
    from test_python_runtime_benchmarks import (  # noqa: PLC0415
        build_catalog,
        build_provenance,
        sample,
    )

    from master_all_strings.mvp.demo_library import load_demo_manifest  # noqa: PLC0415

    sizes = (100, 1000) if quick else (100, 1000, 10000)
    iterations = 20 if quick else 50

    def catalog_measurements(size: int) -> dict[str, Any]:
        catalog = build_catalog(size)
        last = f"bench-media-{size - 1:05d}"
        resolved = catalog.media_for_lesson("bench-lesson")
        return {
            "get_first": sample(
                lambda catalog=catalog: catalog.get("bench-media-00000"), iterations=iterations
            ),
            "get_last": sample(
                lambda catalog=catalog, last=last: catalog.get(last), iterations=iterations
            ),
            "contains_missing": sample(
                lambda catalog=catalog: catalog.contains("bench-media-missing"),
                iterations=iterations,
            ),
            "media_for_lesson": sample(
                lambda catalog=catalog: catalog.media_for_lesson("bench-lesson"),
                iterations=iterations,
            ),
            "media_records": size,
            "references_resolved": len(resolved),
        }

    def provenance_measurements(size: int) -> dict[str, Any]:
        provenance = build_provenance(size)
        last_event = f"bench-canonical-{size - 1:05d}"
        return {
            "first": sample(
                lambda provenance=provenance: provenance.for_event("bench-canonical-00000"),
                iterations=iterations,
            ),
            "last": sample(
                lambda provenance=provenance, last_event=last_event: provenance.for_event(
                    last_event
                ),
                iterations=iterations,
            ),
            "missing": sample(
                lambda provenance=provenance: provenance.for_event("bench-canonical-missing"),
                iterations=iterations,
            ),
            "entries": size,
        }

    catalog_results = {str(size): catalog_measurements(size) for size in sizes}
    provenance_results = {str(size): provenance_measurements(size) for size in sizes}

    return {
        "status": "OK",
        "media_catalog": {"risk": "M6", "measurements": catalog_results},
        "provenance": {"risk": "M8", "measurements": provenance_results},
        "demo_manifest": {
            "risk": "M7",
            "measurements": {
                "load_demo_manifest": sample(
                    load_demo_manifest, iterations=10 if quick else 30, warmup=3
                )
            },
        },
    }


def run_media_benchmark(quick: bool) -> dict[str, Any]:
    script = REPO_ROOT / "scripts" / "performance" / "benchmark_local_media.py"
    args = [sys.executable, str(script), "--iterations", "3" if quick else "5"]
    if quick:
        args += ["--max-mb", "10"]
    result = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", check=False, timeout=3600
    )
    if result.returncode != 0:
        return {"status": "FAILED", "stderr": result.stderr[-2000:]}
    payload = json.loads(result.stdout)
    payload["status"] = "OK"
    return payload


def workload_digests() -> dict[str, str]:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "performance"))
    from generate_benchmark_lesson import (  # noqa: PLC0415
        WORKLOAD_SIZES,
        WORKLOAD_VERSION,
        build_benchmark_workload,
        workload_digest,
    )

    digests = {
        str(size): workload_digest(build_benchmark_workload(size)) for size in WORKLOAD_SIZES
    }
    digests["workload_version"] = WORKLOAD_VERSION
    return digests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="fewer iterations and smaller media; never overwrites the baseline",
    )
    parser.add_argument("--workload", type=int, help="run one workload size only (Python side)")
    args = parser.parse_args(argv)

    if args.quick and args.output == DEFAULT_OUTPUT:
        # A developer smoke run must not quietly become the authoritative
        # record; its numbers were taken with the sampling turned down.
        args.output = REPO_ROOT / "docs" / "performance" / "quick-baseline.local.json"

    before = _git("status", "--porcelain")
    measurements: dict[str, Any] = {}
    for name, script in NODE_BENCHMARKS:
        print(f"running {name} ...", file=sys.stderr)
        measurements[name] = run_node_benchmark(script, args.quick)
    print("running python lookups ...", file=sys.stderr)
    measurements["python_runtime"] = run_python_benchmarks(args.quick)
    print("running local media serving ...", file=sys.stderr)
    measurements["local_media"] = run_media_benchmark(args.quick)

    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "order": "MAS-PERF-001",
        "purpose": "measurement only; no runtime behaviour changed",
        "environment": environment_metadata(),
        "workloads": workload_digests(),
        "measurements": measurements,
        "limitations": [
            "Node benchmarks run against the in-repo DOM stub: they measure "
            "JavaScript traversal and style-write counts, not style "
            "recalculation, layout or paint.",
            "querySelectorAll over a real SVG tree and innerHTML parsing are "
            "not measured; the score-view figures cover the JavaScript around "
            "them.",
            "Node has no Linux CI in this repository, so Node figures are "
            "Windows-only.",
            "Timings were taken on a developer machine, not an isolated host.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    after = _git("status", "--porcelain")
    changed = sorted(set(after.splitlines()) - set(before.splitlines()))
    unexpected = [line for line in changed if "docs/performance/" not in line]
    if unexpected:
        # A profiling run that edits the product is the failure this tranche
        # exists to avoid.
        print("FAIL benchmarks changed files outside docs/performance:", file=sys.stderr)
        for line in unexpected:
            print(f"     {line}", file=sys.stderr)
        return 1

    print(f"wrote {args.output}")
    failures = [name for name, payload in measurements.items() if payload.get("status") != "OK"]
    if failures:
        print(f"FAIL benchmarks did not complete: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
