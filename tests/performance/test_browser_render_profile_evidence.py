"""MAS-PERF-002R: the browser profile has to keep meaning what it says.

These check the record, never the runtime. They hold the evidence to its own
rules -- the workload it names is the workload that was measured, every series
has the samples it claims, summaries recompute from those samples, clocks stay
apart, long tasks are placed honestly against the sampled frames, missing data
says it is missing, and every verdict points at evidence that exists and agrees
with the report.

Nothing here asserts a timing. A millisecond threshold would make a busy laptop
fail the build.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_DOCS = REPO_ROOT / "docs" / "performance"
EVIDENCE = PERFORMANCE_DOCS / "MAS_BROWSER_RENDER_PROFILE_EVIDENCE.json"
REPORT = PERFORMANCE_DOCS / "MAS_BROWSER_RENDER_PROFILE_REPORT.md"
PLAN = PERFORMANCE_DOCS / "MAS_BROWSER_RENDER_PROFILE_PLAN.md"
RUNNER = REPO_ROOT / "scripts" / "performance" / "run_mas_browser_profile.py"

SIZES = ("100", "1000", "10000")
WARMUPS = 5
SAMPLES = 20
VERDICTS = {
    "MATTERS_NOW",
    "MATTERS_AT_SCALE",
    "NOT_MATERIAL_IN_MEASURED_RANGE",
    "INSUFFICIENT_EVIDENCE",
}
DECISION_RISKS = ("M2", "M4", "M5", "PAINT", "MEMORY")
PLACEMENTS = {
    "before_window",
    "after_window",
    "crosses_window_start",
    "crosses_window_end",
    "inside_delta",
    "spans_deltas",
    "UNKNOWN_TIMING",
}

# The files this order may touch. Everything else is the product, the
# MAS-PERF-001 baseline, or frozen DO-015 evidence.
ALLOWED_CHANGES = {
    "docs/development/IN_FLIGHT.md",
    "docs/performance/MAS_BROWSER_RENDER_PROFILE_PLAN.md",
    "docs/performance/MAS_BROWSER_RENDER_PROFILE_EVIDENCE.json",
    "docs/performance/MAS_BROWSER_RENDER_PROFILE_REPORT.md",
    "web/mvp1/tests/performance/browser_render_profile.html",
    "web/mvp1/tests/performance/browser_render_profile.mjs",
    "web/mvp1/tests/performance/browser_render_profile_page.js",
    "web/mvp1/tests/performance/browser_crypto_shim.js",
    "scripts/performance/run_mas_browser_profile.py",
    "tests/performance/test_browser_render_profile_evidence.py",
}


@pytest.fixture(scope="module")
def runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_mas_browser_profile", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def nearest_rank(samples: list[float], p: float) -> float:
    # Written out again rather than imported: a summary checked by the code
    # that produced it proves nothing.
    ordered = sorted(samples)
    rank = min(len(ordered) - 1, math.ceil((p / 100) * len(ordered)) - 1)
    return ordered[max(0, rank)]


def expected_summary(samples: list[float]) -> dict[str, Any]:
    return {
        "count": len(samples),
        "median_ms": nearest_rank(samples, 50),
        "p95_ms": nearest_rank(samples, 95),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


def resolve(payload: Any, path: str) -> list[Any]:
    """Follow a dotted citation, where ``*`` means every key at that level."""

    found: list[Any] = [payload]
    for part in path.split("."):
        nxt: list[Any] = []
        for item in found:
            if not isinstance(item, dict):
                return []
            if part == "*":
                nxt.extend(item.values())
            elif part in item:
                nxt.append(item[part])
        found = nxt
    return found


def blocks_of(operation: dict[str, Any]) -> list[dict[str, Any]]:
    """An operation's own series block, and its M4 sub-operations if any."""

    nested = [operation[key] for key in ("active_update", "selector_only") if key in operation]
    return [operation, *nested]


def sampled_series(evidence: dict[str, Any]) -> list[tuple[str, dict[str, Any], int]]:
    """Every (label, series block, warm-ups discarded) in the evidence."""

    out = []
    for size, operations in evidence["operations"].items():
        for name, operation in operations.items():
            for block in blocks_of(operation):
                for series_name, series in block.get("series", {}).items():
                    out.append((f"{size}.{name}.{series_name}", series, block["warmups_discarded"]))
    for size, runs in evidence["frame_windows"].items():
        for run, window in runs.items():
            for key in ("frame_deltas", "render_frame_js"):
                out.append((f"{size}.{run}.{key}", window[key], window["warmups_discarded"]))
    return out


# --- identity ------------------------------------------------------------------


def test_the_documents_exist() -> None:
    for path in (EVIDENCE, REPORT, PLAN):
        assert path.is_file(), f"{path.name} is missing"


def test_the_evidence_is_this_order_and_says_what_it_replaced(evidence: dict[str, Any]) -> None:
    assert evidence["order"] == "MAS-PERF-002R"
    assert "measurement only" in evidence["purpose"]
    superseded = evidence["supersedes"]
    assert superseded["order"] == "MAS-PERF-002"
    assert superseded["disposition"] == "UNRECOVERABLE_SUPERSEDED"
    assert superseded["reported_head"] == "707527e0c8d1dcb00fb714dbbf574b0cc9ae4d51"


def test_the_browser_and_host_are_identified(evidence: dict[str, Any]) -> None:
    environment = evidence["environment"]
    for key in (
        "os",
        "cpu",
        "browser",
        "viewport",
        "device_scale_factor",
        "display_refresh_rate_hz",
        "repository_sha",
        "base_sha",
    ):
        assert environment.get(key) not in (None, ""), f"{key} not recorded"
    assert environment["browser"]["headed"] is True
    assert environment["browser"]["product"].startswith("Chrome/")
    collection = evidence["collection"]
    for key in ("harness_version", "driver_version", "runner_version", "commands", "chrome_flags"):
        assert collection.get(key), f"{key} not recorded"
    assert not any(flag.startswith("--headless") for flag in collection["chrome_flags"])


@pytest.mark.parametrize("size", SIZES)
def test_every_size_is_present_and_its_digests_agree(
    evidence: dict[str, Any], runner: ModuleType, size: str
) -> None:
    workload = evidence["workloads"][size]
    regenerated = runner.workload_digest(runner.build_benchmark_workload(int(size)))
    assert workload["python_digest"] == regenerated
    assert workload["node_digest"] == regenerated
    assert workload["page_digests"], "the page never reported its own digest"
    assert set(workload["page_digests"].values()) == {regenerated}
    assert workload["generator_check_output"].endswith(regenerated)
    assert workload["agree"] is True


@pytest.mark.parametrize("size", SIZES)
def test_regenerating_a_workload_gives_the_same_digest(runner: ModuleType, size: str) -> None:
    first = runner.workload_digest(runner.build_benchmark_workload(int(size)))
    second = runner.workload_digest(runner.build_benchmark_workload(int(size)))
    assert first == second


# --- samples and summaries -------------------------------------------------------


def test_every_series_discards_five_and_keeps_twenty(evidence: dict[str, Any]) -> None:
    series = sampled_series(evidence)
    assert series
    for label, block, warmups in series:
        assert warmups == WARMUPS, f"{label}: {warmups} warm-ups"
        assert len(block["samples_ms"]) == SAMPLES, f"{label}: {len(block['samples_ms'])} samples"


def test_every_summary_recomputes_from_its_samples(evidence: dict[str, Any]) -> None:
    for label, block, _ in sampled_series(evidence):
        assert block["summary"] == expected_summary(block["samples_ms"]), label


@pytest.mark.parametrize("size", SIZES)
def test_every_operation_ran_at_every_size(evidence: dict[str, Any], size: str) -> None:
    assert set(evidence["operations"][size]) == {
        "m5_tab_mount",
        "m5_notation_mount",
        "m4_tab_active",
        "m4_notation_active",
        "m2_render_frame",
        "m2_frame_window",
    }


def test_the_largest_frame_window_was_taken_twice(evidence: dict[str, Any]) -> None:
    assert set(evidence["frame_windows"]["10000"]) == {"run_1", "run_2"}


# --- clocks ---------------------------------------------------------------------


def test_every_series_names_one_clock(evidence: dict[str, Any]) -> None:
    for size, operations in evidence["operations"].items():
        for name, operation in operations.items():
            if operation["kind"] == "frame_window":
                continue
            for block in blocks_of(operation):
                for series_name, series in block.get("series", {}).items():
                    assert series.get("clock"), f"{size}.{name}.{series_name} names no clock"


def test_no_series_is_a_remainder_of_two_clocks(evidence: dict[str, Any]) -> None:
    # Paint is never derived by subtraction: no series may be named as one.
    for label, _, _ in sampled_series(evidence):
        series_name = label.rsplit(".", 1)[-1]
        assert "paint" not in series_name, label
        assert "minus" not in series_name and "remainder" not in series_name, label
    assert "subtract" in evidence["collection"]["derived_values"]


def test_cold_mount_and_active_update_are_kept_apart(evidence: dict[str, Any]) -> None:
    for operations in evidence["operations"].values():
        for name, operation in operations.items():
            if name.startswith("m5_"):
                assert (operation["risk"], operation["kind"]) == ("M5", "cold_mount")
                assert "selector_ms" not in operation["series"], name
                assert "active_update" not in operation
            if name.startswith("m4_"):
                assert (operation["risk"], operation["kind"]) == ("M4", "active_update")
                assert "selector_ms" in operation["selector_only"]["series"]
    for decision in evidence["decisions"]:
        cites = " ".join(decision["cites"])
        if decision["risk"] == "M5":
            assert "m4_" not in cites, "an M4 selector measurement is cited for M5"
        if decision["risk"] == "M4":
            assert "m5_" not in cites, "an M5 mount measurement is cited for M4"


# --- frames and long tasks ------------------------------------------------------


def test_frame_timestamps_are_ordered_and_deltas_are_theirs(evidence: dict[str, Any]) -> None:
    for size, runs in evidence["frame_windows"].items():
        for run, window in runs.items():
            frames = window["frame_timestamps_ms"]
            assert len(frames) == SAMPLES + 1, f"{size}.{run}"
            assert frames == sorted(frames), f"{size}.{run}: timestamps out of order"
            deltas = [later - earlier for earlier, later in zip(frames, frames[1:], strict=False)]
            assert window["frame_deltas"]["samples_ms"] == deltas, f"{size}.{run}"
            discarded = window["discarded_timestamps_ms"]
            assert len(discarded) == WARMUPS
            assert not discarded or max(discarded) <= frames[0]


def test_every_long_task_is_stored_whole_and_placed_honestly(
    evidence: dict[str, Any], runner: ModuleType
) -> None:
    for size, runs in evidence["frame_windows"].items():
        for run, window in runs.items():
            for task in window["long_tasks"]:
                label = f"{size}.{run}"
                for key in (
                    "start_time_ms",
                    "duration_ms",
                    "name",
                    "attribution",
                    "time_origin_ms",
                    "time_origin",
                    "attribution_status",
                    "placement",
                ):
                    assert key in task, f"{label}: long task lacks {key}"
                assert task["placement"] in PLACEMENTS
                recomputed = runner.place_long_task(
                    task["start_time_ms"], task["duration_ms"], window["frame_timestamps_ms"]
                )
                assert recomputed["placement"] == task["placement"], label
                assert task["attribution_status"] == runner.attribution_status(
                    task["attribution"]
                ), label


def test_a_task_before_the_first_frame_is_never_inside_a_delta(runner: ModuleType) -> None:
    frames = [100.0, 116.7, 133.3, 150.0]
    assert runner.place_long_task(10.0, 60.0, frames)["placement"] == "before_window"
    assert runner.place_long_task(60.0, 60.0, frames)["placement"] == "crosses_window_start"
    assert runner.place_long_task(99.9, 5.0, frames)["placement"] == "crosses_window_start"


def test_a_task_across_the_last_frame_is_never_inside_a_delta(runner: ModuleType) -> None:
    frames = [100.0, 116.7, 133.3, 150.0]
    assert runner.place_long_task(140.0, 60.0, frames)["placement"] == "crosses_window_end"
    assert runner.place_long_task(150.0, 60.0, frames)["placement"] == "after_window"


def test_only_a_task_wholly_inside_one_delta_is_given_that_delta(runner: ModuleType) -> None:
    frames = [100.0, 116.7, 133.3, 150.0]
    assert runner.place_long_task(117.0, 16.0, frames) == {
        "placement": "inside_delta",
        "delta_index": 1,
    }
    assert runner.place_long_task(110.0, 30.0, frames) == {
        "placement": "spans_deltas",
        "delta_indices": [0, 2],
    }


# --- honest missing data --------------------------------------------------------


def test_missing_timing_is_unknown_not_guessed(runner: ModuleType) -> None:
    frames = [100.0, 116.7]
    assert runner.place_long_task(None, 60.0, frames) == {"placement": "UNKNOWN_TIMING"}
    assert runner.place_long_task(100.0, None, frames) == {"placement": "UNKNOWN_TIMING"}
    assert runner.place_long_task(100.0, 60.0, [100.0]) == {"placement": "UNKNOWN_TIMING"}


def test_missing_or_unknown_attribution_stays_that_way(runner: ModuleType) -> None:
    assert runner.attribution_status(None) == "missing"
    assert runner.attribution_status([]) == "missing"
    # A window container says where the task ran, not what ran it.
    in_window = [{"name": "unknown", "container_type": "window", "container_name": ""}]
    assert runner.attribution_status(in_window) == "unknown"
    named = [{"name": "self", "container_type": "window", "container_name": ""}]
    assert runner.attribution_status(named) == "attributed"


def test_a_memory_reading_without_a_metric_is_not_measured(runner: ModuleType) -> None:
    reading = {"js_heap_used_bytes": None, "dom_nodes": None}
    reduced = runner.reduce_memory({"group": {"before": reading, "after": reading}})
    assert reduced["status"] == "NOT_MEASURED"


def test_every_trace_is_decoded_or_says_why_not(evidence: dict[str, Any]) -> None:
    for size in SIZES:
        trace = evidence["traces"][size]
        for part in ("frame_window", "mount", "mount_through_next_frames"):
            reduced = trace.get(part, trace)
            assert reduced["status"] in {"DECODED", "UNAVAILABLE"}, f"{size}.{part}"
            if reduced["status"] == "UNAVAILABLE":
                assert reduced.get("reason"), f"{size}.{part}: unavailable without a reason"


def test_paint_and_memory_verdicts_match_what_was_captured(evidence: dict[str, Any]) -> None:
    decisions = {decision["risk"]: decision for decision in evidence["decisions"]}
    decoded = all(
        evidence["traces"][size].get("frame_window", {}).get("status") == "DECODED"
        and evidence["traces"][size]["frame_window"].get("per_frame", {}).get("frames")
        for size in SIZES
    )
    if not decoded:
        assert decisions["PAINT"]["classification"] == "INSUFFICIENT_EVIDENCE"
    measured = all(evidence["memory"][size]["status"] == "MEASURED" for size in SIZES)
    if not measured:
        assert decisions["MEMORY"]["classification"] == "NOT_MEASURED"


# --- verdicts -------------------------------------------------------------------


def test_every_risk_has_exactly_one_verdict(evidence: dict[str, Any]) -> None:
    risks = [decision["risk"] for decision in evidence["decisions"]]
    assert sorted(risks) == sorted(DECISION_RISKS)
    for decision in evidence["decisions"]:
        allowed = VERDICTS | ({"NOT_MEASURED"} if decision["risk"] == "MEMORY" else set())
        assert decision["classification"] in allowed, decision["risk"]
        assert decision["finding"] and decision["next_action"], decision["risk"]


def test_every_verdict_cites_evidence_that_exists(evidence: dict[str, Any]) -> None:
    for decision in evidence["decisions"]:
        assert decision["cites"], f"{decision['risk']} cites nothing"
        for path in decision["cites"]:
            assert resolve(evidence, path), f"{decision['risk']}: {path} resolves to nothing"


def test_the_report_classifies_the_same_way_the_evidence_does(evidence: dict[str, Any]) -> None:
    report = REPORT.read_text(encoding="utf-8")
    for decision in evidence["decisions"]:
        row = re.search(rf"^\|\s*{decision['risk']}\b.*$", report, re.MULTILINE)
        assert row, f"{decision['risk']} has no row in the report"
        assert decision["classification"] in row.group(0), decision["risk"]


def test_the_report_says_the_earlier_attempt_was_superseded() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert "707527e" in report
    assert "unrecoverable" in report.lower()
    assert "produced anew" in report.lower()


# --- the measured tree ----------------------------------------------------------


def test_the_measured_tree_changed_nothing_but_this_orders_files(
    evidence: dict[str, Any],
) -> None:
    # Checked between the recorded base and the commit the capture ran on --
    # a fixed pair, so later orders that legitimately change the product never
    # turn this red. Skipped where that history is not present (a shallow CI
    # checkout); the pull request is checked by hand as well.
    environment = evidence["environment"]
    try:
        changed = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "diff",
                "--name-only",
                environment["base_sha"],
                environment["repository_sha"],
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("base or measured commit not in this checkout's history")
    unexpected = sorted(set(changed) - ALLOWED_CHANGES)
    assert not unexpected, f"product or frozen files changed: {unexpected}"
