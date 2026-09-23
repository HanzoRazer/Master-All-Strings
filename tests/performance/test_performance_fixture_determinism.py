"""Benchmark workloads must be the same lesson every time, in both languages.

A performance number is only comparable to another one if the input was
identical. These hold that: the same event count produces the same bytes, and
the Node mirror of the grammar produces the same digest as the Python original.

Without the cross-language check the two halves of this tranche could measure
different lessons while each reported a number, and the report would compare
them as though they were the same thing.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "performance" / "generate_benchmark_lesson.py"
JS_FIXTURES = REPO_ROOT / "web" / "mvp1" / "tests" / "performance" / "benchmark-fixtures.js"


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_benchmark_lesson", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _generator()


@pytest.mark.parametrize("count", [0, 1, 100, 1000])
def test_the_same_count_produces_the_same_bytes(generator: ModuleType, count: int) -> None:
    first = generator.build_benchmark_workload(count)
    second = generator.build_benchmark_workload(count)
    assert first == second
    assert generator.workload_digest(first) == generator.workload_digest(second)


def test_workloads_of_different_sizes_are_different(generator: ModuleType) -> None:
    digests = {
        size: generator.workload_digest(generator.build_benchmark_workload(size))
        for size in (100, 1000)
    }
    assert len(set(digests.values())) == 2


def test_nothing_in_a_workload_comes_from_a_clock_or_a_random_source(
    generator: ModuleType,
) -> None:
    # The failure this prevents is subtle: a workload carrying a timestamp
    # still benchmarks fine, and quietly makes every measurement
    # incomparable to every other. Asserted on imports, not on the text --
    # prose about randomness is not a random source.
    import ast

    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"random", "uuid", "time", "datetime", "secrets", "os"}


def test_the_workload_exercises_every_string_and_varying_durations(
    generator: ModuleType,
) -> None:
    # A workload where every note is identical would measure a compiler's
    # constant folding more than the renderer.
    events = generator.build_benchmark_events(120)
    assert {event["string_index"] for event in events} == set(range(6))
    assert len({event["release_ms"] - event["onset_ms"] for event in events}) > 1
    assert len({event["fret"] for event in events}) > 1


def test_events_are_ordered_and_overlap_like_real_playing(generator: ModuleType) -> None:
    events = generator.build_benchmark_events(50)
    onsets = [event["onset_ms"] for event in events]
    assert onsets == sorted(onsets)
    # Longer notes ring into the next onset, so the renderer and scheduler see
    # simultaneous events rather than a strictly sequential stream.
    assert any(
        events[index]["release_ms"] > events[index + 1]["onset_ms"]
        for index in range(len(events) - 1)
    )


def test_the_cli_check_reports_a_digest(
    generator: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generator.main(["--events", "100", "--check"]) == 0
    printed = capsys.readouterr().out
    assert "workload 100: sha256:" in printed


def test_the_cli_writes_the_workload_it_reports(
    generator: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "workload.json"
    assert generator.main(["--events", "100", "--output", str(target)]) == 0
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["event_count"] == 100
    assert generator.workload_digest(written) in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("count", [0, 1, 100, 1000])
def test_the_node_mirror_produces_the_same_digest(generator: ModuleType, count: int) -> None:
    # The check that keeps this tranche honest: one grammar, two
    # implementations, and a single lesson behind every measured number.
    script = (
        "import { buildBenchmarkWorkload, workloadDigest } from "
        f"{json.dumps(JS_FIXTURES.as_uri())};"
        f"process.stdout.write(workloadDigest(buildBenchmarkWorkload({count})));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    expected = generator.workload_digest(generator.build_benchmark_workload(count))
    assert result.stdout.strip() == expected
