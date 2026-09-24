"""The baseline has to keep meaning what it says.

Evidence decays quietly. A classification loses the measurement it cited, a
size disappears, an environment field goes missing, and the file still parses
and still reads like a result. These hold the shape: every risk classified,
every classification pointing at a number that exists, every workload size
present, and the environment captured.

They check the record, not the runtime. Nothing here asserts a timing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_DOCS = REPO_ROOT / "docs" / "performance"
BASELINE = PERFORMANCE_DOCS / "MAS_RUNTIME_PERFORMANCE_BASELINE.json"
REPORT = PERFORMANCE_DOCS / "MAS_RUNTIME_PERFORMANCE_REPORT.md"
PLAN = PERFORMANCE_DOCS / "MAS_RUNTIME_PERFORMANCE_PLAN.md"

WORKLOAD_SIZES = ("100", "1000", "10000")
RISKS = tuple(f"M{index}" for index in range(1, 11))
VERDICTS = {
    "MATTERS_NOW",
    "MATTERS_AT_SCALE",
    "NOT_MATERIAL_IN_MEASURED_RANGE",
    "INSUFFICIENT_EVIDENCE",
}
REQUIRED_ENVIRONMENT = (
    "os",
    "architecture",
    "python_version",
    "node_version",
    "repository_sha",
    "node_measurement_platform",
    "linux_node_measurement",
)


@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


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
            else:
                return []
        found = nxt
    return found


def test_the_documents_exist(baseline: dict[str, Any]) -> None:
    assert BASELINE.exists()
    assert REPORT.exists()
    assert PLAN.exists()
    assert baseline["order"] == "MAS-PERF-001"


def test_the_environment_is_captured(baseline: dict[str, Any]) -> None:
    environment = baseline["environment"]
    for field in REQUIRED_ENVIRONMENT:
        assert environment.get(field), f"{field} missing: the numbers are not comparable"
    # Saying otherwise would imply Node coverage this repository does not have.
    assert environment["linux_node_measurement"] == "NOT_PRESENT"


def test_every_workload_size_has_a_digest(baseline: dict[str, Any]) -> None:
    workloads = baseline["workloads"]
    assert workloads["workload_version"]
    for size in WORKLOAD_SIZES:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", workloads[size]), size
    # Different sizes must be different workloads, or a digest is decorative.
    assert len({workloads[size] for size in WORKLOAD_SIZES}) == len(WORKLOAD_SIZES)


def test_every_benchmark_completed(baseline: dict[str, Any]) -> None:
    for name, payload in baseline["measurements"].items():
        assert payload.get("status") == "OK", f"{name} did not complete"


@pytest.mark.parametrize("size", WORKLOAD_SIZES)
def test_the_browser_benchmarks_cover_every_size(baseline: dict[str, Any], size: str) -> None:
    for benchmark in ("audio_scheduler", "fretboard_renderer", "score_views"):
        assert size in baseline["measurements"][benchmark]["measurements"], f"{benchmark}/{size}"


def test_every_risk_is_classified(baseline: dict[str, Any]) -> None:
    classified = {decision["risk"] for decision in baseline["decisions"]}
    assert classified == set(RISKS), f"unclassified: {set(RISKS) - classified}"


@pytest.mark.parametrize("risk", RISKS)
def test_each_classification_is_one_of_the_four(baseline: dict[str, Any], risk: str) -> None:
    decision = next(item for item in baseline["decisions"] if item["risk"] == risk)
    assert decision["classification"] in VERDICTS
    assert decision["finding"].strip()
    assert decision["next_action"].strip()


@pytest.mark.parametrize("risk", RISKS)
def test_each_classification_cites_a_measurement_that_exists(
    baseline: dict[str, Any], risk: str
) -> None:
    # The check that stops a verdict becoming an opinion: every citation has to
    # resolve to something in this file.
    decision = next(item for item in baseline["decisions"] if item["risk"] == risk)
    assert decision["cites"], f"{risk} cites nothing"
    for citation in decision["cites"]:
        resolved = resolve(baseline, citation)
        assert resolved, f"{risk} cites {citation}, which resolves to nothing"


def test_a_sample_summary_carries_median_and_p95(baseline: dict[str, Any]) -> None:
    summaries = resolve(baseline, "measurements.audio_scheduler.measurements.*.middle")
    assert summaries
    for summary in summaries:
        for field in ("iterations", "median_ms", "p95_ms", "min_ms", "max_ms"):
            assert field in summary, field
        assert summary["iterations"] >= 10, "a single reading is not a measurement"


def test_the_limitations_are_stated(baseline: dict[str, Any]) -> None:
    limitations = " ".join(baseline["limitations"]).lower()
    for expected in ("layout", "paint", "linux", "queryselectorall"):
        assert expected in limitations, f"{expected} limitation not recorded"


def test_the_report_classifies_the_same_way_the_evidence_does(baseline: dict[str, Any]) -> None:
    # Two documents describing one result only help if they agree.
    report = REPORT.read_text(encoding="utf-8")
    for decision in baseline["decisions"]:
        row = re.search(rf"^\|\s*{decision['risk']} .*$", report, re.MULTILINE)
        assert row, f"{decision['risk']} has no row in the report"
        assert decision["classification"] in row.group(0), (
            f"{decision['risk']}: report says something other than "
            f"{decision['classification']}"
        )


def test_no_timing_threshold_is_asserted_anywhere_in_this_tranche() -> None:
    # The rule the tranche runs on, enforced against its own tests: a
    # benchmark that fails the build on a number is a flaky gate people learn
    # to ignore. Only measured timings count -- a workload's own duration
    # fields are data, not measurements.
    timing_fields = ("median_ms", "p95_ms", "min_ms", "max_ms", "elapsed_s")
    for path in sorted((REPO_ROOT / "tests" / "performance").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("assert"):
                continue
            if not any(field in stripped for field in timing_fields):
                continue
            assert ">= 0" in stripped or "in stripped" in stripped or "in summary" in stripped, (
                f"{path.name}: timing threshold asserted: {stripped}"
            )


def test_the_baseline_records_that_nothing_was_optimized(baseline: dict[str, Any]) -> None:
    assert "measurement only" in baseline["purpose"]
    assert "no runtime behaviour changed" in baseline["purpose"]
