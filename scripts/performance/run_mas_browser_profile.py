#!/usr/bin/env python3
"""MAS-PERF-002R: profile the renderer and score views in a headed Chrome.

Serves ``web/mvp1`` with cross-origin isolation headers, launches Chrome with a
throwaway profile and a DevTools port, runs
``web/mvp1/tests/performance/browser_render_profile.mjs`` against it, and turns
what that returns into ``docs/performance/MAS_BROWSER_RENDER_PROFILE_EVIDENCE.json``.

The page reports raw observations only. Everything derived -- summaries, frame
deltas, where each long task sits relative to the sampled frames -- is computed
here from those raw numbers, so the evidence cannot disagree with itself.

Verdicts are not computed. They are judgements, added to the evidence by hand
after a run and checked by ``tests/performance/test_browser_render_profile_evidence.py``;
re-running this deliberately drops them, so stale verdicts cannot survive new
numbers.

Stops, writing nothing authoritative, if the Python, Node and page digests of
any workload disagree, or if the run changes a file outside docs/performance.

    python scripts/performance/run_mas_browser_profile.py
    python scripts/performance/run_mas_browser_profile.py --sizes 100 --output /tmp/smoke.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import functools
import http.server
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web" / "mvp1"
DRIVER = WEB_ROOT / "tests" / "performance" / "browser_render_profile.mjs"
GENERATOR = REPO_ROOT / "scripts" / "performance" / "generate_benchmark_lesson.py"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "performance" / "MAS_BROWSER_RENDER_PROFILE_EVIDENCE.json"

sys.path.insert(0, str(GENERATOR.parent))
from generate_benchmark_lesson import (  # noqa: E402
    WORKLOAD_SIZES,
    WORKLOAD_VERSION,
    build_benchmark_workload,
    workload_digest,
)

EVIDENCE_SCHEMA_VERSION = "1.0.0"
RUNNER_VERSION = "1.0.0"
WARMUPS = 5
SAMPLES = 20

CHROME_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/usr/bin/google-chrome"),
)

CHROME_FLAGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--window-position=0,0",
    "--window-size=1280,900",
    "--remote-debugging-port=0",
)

PLACEMENTS = (
    "before_window",
    "after_window",
    "crosses_window_start",
    "crosses_window_end",
    "inside_delta",
    "spans_deltas",
    "UNKNOWN_TIMING",
)


# --- summaries and placement: pure, and tested -------------------------------


def percentile(samples: list[float], p: float) -> float:
    """Nearest rank, the definition ``benchmark-fixtures.js`` uses."""

    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    rank = min(len(ordered) - 1, math.ceil((p / 100) * len(ordered)) - 1)
    return ordered[max(0, rank)]


def summarize(samples: list[float]) -> dict[str, Any]:
    return {
        "count": len(samples),
        "median_ms": percentile(samples, 50),
        "p95_ms": percentile(samples, 95),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


def frame_deltas(timestamps: list[float]) -> list[float]:
    return [later - earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)]


def place_long_task(
    start: float | None, duration: float | None, frames: list[float]
) -> dict[str, Any]:
    """Where a long task sits against the retained frame timestamps.

    Only a task wholly inside one retained delta is attributed to that delta.
    A task that starts before the first retained frame, or ends after the last,
    is outside or crossing the window, and is never assigned to a delta.
    """

    if start is None or duration is None or len(frames) < 2:
        return {"placement": "UNKNOWN_TIMING"}
    end = start + duration
    first, last = frames[0], frames[-1]
    if end <= first:
        return {"placement": "before_window"}
    if start >= last:
        return {"placement": "after_window"}
    if start < first:
        return {"placement": "crosses_window_start"}
    if end > last:
        return {"placement": "crosses_window_end"}
    start_delta = max(i for i in range(len(frames) - 1) if frames[i] <= start)
    end_delta = min(i for i in range(len(frames) - 1) if end <= frames[i + 1])
    if start_delta == end_delta:
        return {"placement": "inside_delta", "delta_index": start_delta}
    return {"placement": "spans_deltas", "delta_indices": [start_delta, end_delta]}


def attribution_status(attribution: list[dict[str, Any]] | None) -> str:
    if not attribution:
        return "missing"
    names = {item.get("name") for item in attribution}
    containers = {
        item.get(key)
        for item in attribution
        for key in ("container_type", "container_name", "container_id", "container_src")
    } - {None, ""}
    if names <= {"unknown", None} and not containers:
        return "unknown"
    return "attributed"


def series_block(values: list[float]) -> dict[str, Any]:
    return {"samples_ms": values, "summary": summarize(values)}


def operation_block(raw: dict[str, Any], clocks: dict[str, str]) -> dict[str, Any]:
    """Raw series from the page, each with its clock and its summary."""

    series = {}
    for name, values in raw["series"].items():
        if name not in clocks:
            continue
        series[name] = {"clock": clocks[name], **series_block(values)}
    return {"warmups_discarded": raw["warmups_discarded"], "series": series}


def frame_window_block(raw: dict[str, Any], time_origin_ms: float | None) -> dict[str, Any]:
    frames = raw["frame_timestamps_ms"]
    deltas = frame_deltas(frames)
    tasks = []
    for task in raw["long_tasks"]:
        tasks.append(
            {
                **task,
                "time_origin_ms": time_origin_ms,
                "time_origin": "performance.timeOrigin of the profile page",
                "attribution_status": attribution_status(task.get("attribution")),
                **place_long_task(task.get("start_time_ms"), task.get("duration_ms"), frames),
            }
        )
    return {
        "warmups_discarded": raw["warmups_discarded"],
        "clock": "requestAnimationFrame timestamp",
        "time_origin_ms": time_origin_ms,
        "frame_timestamps_ms": frames,
        "discarded_timestamps_ms": raw["discarded_timestamps_ms"],
        "frame_deltas": series_block(deltas),
        "render_frame_js": {"clock": "performance.now", **series_block(raw["js_ms"])},
        "observed_interval_ms": [raw["observed_from_ms"], raw["observed_to_ms"]],
        "long_tasks": tasks,
    }


MOUNT_CLOCKS = {
    "string_build_ms": "performance.now around renderTabSvg/renderNotationSvg",
    "innerhtml_replace_ms": "performance.now around container.innerHTML = svg",
    "style_layout_ms": "performance.now around a forced getBoundingClientRect after the replace",
}
ACTIVE_CLOCKS = {
    "active_update_ms": "performance.now around applyActiveEventIds",
    "style_layout_ms": "performance.now around a forced getBoundingClientRect after the update",
}
SELECTOR_CLOCKS = {"selector_ms": "performance.now around root.querySelectorAll"}
FRAME_CLOCKS = {
    "js_ms": "performance.now around renderFrame",
    "style_layout_ms": "performance.now around a forced getBoundingClientRect after renderFrame",
}


def build_operations(run: dict[str, Any]) -> dict[str, Any]:
    score = run["score"]["operations"]
    fretboard = run["fretboard"]["operations"]
    time_origin = run["fretboard"]["environment"].get("time_origin_ms")
    operations: dict[str, Any] = {}
    for key in ("m5_tab_mount", "m5_notation_mount"):
        raw = score[key]
        operations[key] = {
            "risk": "M5",
            "kind": "cold_mount",
            "view": raw["view"],
            "svg_characters": raw["svg_characters"],
            "elements_in_tree": raw["elements_in_tree"],
            "event_groups_in_tree": raw["event_groups_in_tree"],
            **operation_block(raw, MOUNT_CLOCKS),
        }
    for key in ("m4_tab_active", "m4_notation_active"):
        raw = score[key]
        operations[key] = {
            "risk": "M4",
            "kind": "active_update",
            "view": raw["view"],
            "selector": raw["selector"],
            "active_ids_per_update": raw["active_ids_per_update"],
            "active_update": operation_block(raw["active_update"], ACTIVE_CLOCKS),
            "selector_only": {
                **operation_block(raw["selector_only"], SELECTOR_CLOCKS),
                "matched": raw["selector_only"]["series"]["matched"][0],
            },
        }
    operations["m2_render_frame"] = {
        "risk": "M2",
        "kind": "frame_step",
        "notes_rendered": run["fretboard"]["notes_rendered"],
        **operation_block(fretboard["m2_render_frame"], FRAME_CLOCKS),
    }
    operations["m2_frame_window"] = {
        "risk": "M2",
        "kind": "frame_window",
        "run": 1,
        **frame_window_block(fretboard["m2_frame_window"], time_origin),
    }
    return operations


def reduce_memory(memory: dict[str, Any]) -> dict[str, Any]:
    def delta(after: dict[str, Any], before: dict[str, Any], key: str) -> float | None:
        if after.get(key) is None or before.get(key) is None:
            return None
        return float(after[key]) - float(before[key])

    out: dict[str, Any] = {}
    for group, readings in memory.items():
        before_key, after_key = list(readings)
        before, after = readings[before_key], readings[after_key]
        out[group] = {
            **readings,
            "js_heap_used_delta_bytes": delta(after, before, "js_heap_used_bytes"),
            "dom_nodes_delta": delta(after, before, "dom_nodes"),
        }
    status = (
        "MEASURED"
        if all(
            out[group]["js_heap_used_delta_bytes"] is not None
            and out[group]["dom_nodes_delta"] is not None
            for group in out
        )
        else "NOT_MEASURED"
    )
    return {"status": status, **out}


# --- workloads ---------------------------------------------------------------


def workload_identities(raw: dict[str, Any], sizes: list[int]) -> dict[str, Any]:
    identities: dict[str, Any] = {}
    for size in sizes:
        key = str(size)
        python_digest = workload_digest(build_benchmark_workload(size))
        check = subprocess.run(
            [sys.executable, str(GENERATOR), "--events", key, "--check"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        run = raw["runs"][key]
        page = {
            "score": run["score"]["workload"]["digest"],
            "fretboard": run["fretboard"]["workload"]["digest"],
        }
        if key in raw.get("frame_window_repeat", {}):
            page["fretboard_window_repeat"] = raw["frame_window_repeat"][key]["workload"]["digest"]
        trace = raw.get("traces", {}).get(key, {})
        if "workload" in trace:
            page["traced"] = trace["workload"]["digest"]
        node_digest = raw["node_workloads"][key]["digest"]
        digests = {python_digest, node_digest, *page.values()}
        identities[key] = {
            "workload_version": WORKLOAD_VERSION,
            "event_count": size,
            "python_digest": python_digest,
            "generator_check_output": check,
            "node_digest": node_digest,
            "page_digests": page,
            "agree": len(digests) == 1 and check.endswith(python_digest),
        }
    return identities


# --- environment -------------------------------------------------------------


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _git(*args: str) -> str:
    return _run(["git", "-C", str(REPO_ROOT), *args])


def _windows_query(expression: str) -> str:
    if platform.system() != "Windows":
        return ""
    return _run(["powershell", "-NoProfile", "-Command", expression])


def environment_metadata(raw: dict[str, Any], chrome: Path) -> dict[str, Any]:
    page_env = raw["runs"][next(iter(raw["runs"]))]["fretboard"]["environment"]
    cpu = _windows_query("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
    refresh = _windows_query(
        "(Get-CimInstance Win32_VideoController | Where-Object CurrentRefreshRate "
        "| Select-Object -First 1).CurrentRefreshRate"
    )
    head = _git("rev-parse", "HEAD")
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu": cpu or platform.processor() or "NOT_AVAILABLE",
        "logical_cpus": os.cpu_count(),
        "python_version": platform.python_version(),
        "node_version": _run(["node", "--version"]) or "NOT_AVAILABLE",
        "browser": {**raw["browser"], "executable": str(chrome), "headed": True},
        "viewport": page_env["viewport"],
        "device_scale_factor": page_env["device_pixel_ratio"],
        "display_refresh_rate_hz": int(refresh) if refresh.isdigit() else "NOT_AVAILABLE",
        "display_refresh_rate_source": "Win32_VideoController.CurrentRefreshRate"
        if refresh.isdigit()
        else None,
        "cross_origin_isolated": page_env["cross_origin_isolated"],
        "visibility_state": page_env["visibility_state"],
        "has_focus": page_env["has_focus"],
        "longtask_supported": page_env["longtask_supported"],
        "fretboard_viewport_width_px": page_env["fretboard_viewport_width_px"],
        "repository_sha": head or "NOT_AVAILABLE",
        "base_sha": _git("merge-base", "HEAD", "origin/main") or "NOT_AVAILABLE",
        "working_tree_clean": _git("status", "--porcelain") == "",
        "captured_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "host_note": "developer machine, not an isolated host",
    }


# --- serving and launching ---------------------------------------------------


class _IsolatedHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".html": "text/html",
        ".json": "application/json",
    }

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(_IsolatedHandler, directory=str(WEB_ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def find_chrome(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit("Chrome not found; pass --chrome")


def launch_chrome(chrome: Path, profile: Path) -> tuple[subprocess.Popen[bytes], int]:
    process = subprocess.Popen(
        [str(chrome), *CHROME_FLAGS, f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if port_file.is_file():
            first = port_file.read_text(encoding="utf-8").splitlines()[:1]
            if first and first[0].isdigit():
                return process, int(first[0])
        time.sleep(0.2)
    process.kill()
    raise SystemExit("Chrome did not open a DevTools port")


def collect(chrome: Path, sizes: list[int]) -> tuple[dict[str, Any], list[str]]:
    server, base_url = serve()
    profile = Path(tempfile.mkdtemp(prefix="mas-perf-002r-chrome-"))
    process, port = launch_chrome(chrome, profile)
    driver = [
        "node",
        str(DRIVER),
        "--port",
        str(port),
        "--base-url",
        base_url,
        "--sizes",
        ",".join(map(str, sizes)),
    ]
    try:
        completed = subprocess.run(driver, capture_output=True, text=True, timeout=3600)
        sys.stderr.write(completed.stderr)
        if completed.returncode != 0:
            raise SystemExit(f"driver failed with exit {completed.returncode}")
        return json.loads(completed.stdout), driver
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


# --- evidence ----------------------------------------------------------------


def build_evidence(raw: dict[str, Any], sizes: list[int], chrome: Path) -> dict[str, Any]:
    operations = {str(size): build_operations(raw["runs"][str(size)]) for size in sizes}
    frame_windows: dict[str, Any] = {
        key: {"run_1": ops["m2_frame_window"]} for key, ops in operations.items()
    }
    for key, repeat in raw.get("frame_window_repeat", {}).items():
        frame_windows[key]["run_2"] = {
            "run": 2,
            **frame_window_block(
                repeat["operations"]["m2_frame_window"],
                repeat["environment"].get("time_origin_ms"),
            ),
        }
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "order": "MAS-PERF-002R",
        "purpose": "measurement only; no runtime behaviour changed",
        "supersedes": {
            "order": "MAS-PERF-002",
            "reported_head": "707527e0c8d1dcb00fb714dbbf574b0cc9ae4d51",
            "disposition": "UNRECOVERABLE_SUPERSEDED",
            "note": "Never pushed and not recoverable. Its reported numbers were planning "
            "leads only; every measurement here was produced anew by MAS-PERF-002R.",
        },
        "environment": environment_metadata(raw, chrome),
        "collection": {
            "runner_version": RUNNER_VERSION,
            "harness_version": raw["runs"][str(sizes[0])]["fretboard"]["environment"][
                "harness_version"
            ],
            "driver_version": raw["driver_version"],
            "commands": [
                "python scripts/performance/run_mas_browser_profile.py",
                "node web/mvp1/tests/performance/browser_render_profile.mjs "
                "--port <DevTools port> --base-url <served web/mvp1 root> "
                f"--sizes {','.join(map(str, sizes))}",
            ],
            "chrome_flags": list(CHROME_FLAGS),
            "served_with": ["Cross-Origin-Opener-Policy: same-origin",
                            "Cross-Origin-Embedder-Policy: require-corp"],
            "page": raw["page_url"],
            "warmups_discarded": WARMUPS,
            "samples_retained": SAMPLES,
            "each_sample_in_its_own_animation_frame": True,
            "clocks": {
                "js": "performance.now() around one synchronous product call",
                "style_layout": "performance.now() around a layout read forced immediately "
                "after the call; its own measurement, never a remainder",
                "frames": "requestAnimationFrame timestamps and the deltas between them",
                "long_tasks": "PerformanceObserver 'longtask' entries, stored whole",
                "trace": "DevTools trace on a separate page load; never mixed with samples",
            },
            "derived_values": "No duration is computed by subtracting one clock from "
            "another. Summaries and placements are computed by the runner from raw samples.",
            "page_errors": raw.get("page_errors", []),
        },
        "workloads": workload_identities(raw, sizes),
        "operations": operations,
        "frame_windows": frame_windows,
        "traces": raw.get("traces", {}),
        "memory": {
            str(size): reduce_memory(raw["runs"][str(size)]["memory"]) for size in sizes
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chrome", help="Chrome executable; found automatically if omitted")
    parser.add_argument("--sizes", help="comma-separated subset, for a smoke run")
    parser.add_argument("--raw-out", type=Path, help="also keep the driver's raw output here")
    parser.add_argument("--from-raw", type=Path, help="rebuild evidence from a kept raw output")
    args = parser.parse_args(argv)

    sizes = [int(size) for size in args.sizes.split(",")] if args.sizes else list(WORKLOAD_SIZES)
    if sizes != list(WORKLOAD_SIZES) and args.output == DEFAULT_OUTPUT:
        raise SystemExit("a subset run must not overwrite the evidence; pass --output")

    chrome = find_chrome(args.chrome)
    before = _git("status", "--porcelain")
    if args.from_raw:
        raw = json.loads(args.from_raw.read_text(encoding="utf-8"))
    else:
        raw, _ = collect(chrome, sizes)
        if args.raw_out:
            args.raw_out.write_text(json.dumps(raw), encoding="utf-8")

    evidence = build_evidence(raw, sizes, chrome)
    disagreements = [key for key, value in evidence["workloads"].items() if not value["agree"]]
    if disagreements:
        print(f"FAIL workload digests disagree at {', '.join(disagreements)}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    after = _git("status", "--porcelain")
    changed = sorted(set(after.splitlines()) - set(before.splitlines()))
    unexpected = [line for line in changed if "docs/performance/" not in line]
    if unexpected:
        print("FAIL the profile changed files outside docs/performance:", file=sys.stderr)
        for line in unexpected:
            print(f"     {line}", file=sys.stderr)
        return 1
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
