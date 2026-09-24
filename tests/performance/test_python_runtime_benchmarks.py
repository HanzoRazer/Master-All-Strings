"""M6, M7 and M8 — the Python lookups the review called linear.

Three claims: catalog lookup is O(media) per reference and therefore O(R×M) for
a lesson, the demo manifest is reread and reparsed on every call, and
provenance lookup scans every entry.

These are microbenchmarks that live beside assertions, because a timing without
a correctness check measures how fast the wrong answer is produced. Each
benchmark asserts the value first and times it second.

Iteration counts are deliberately small: this file runs in the normal test
suite, where its job is to stay honest and finish quickly. The authoritative
numbers come from `scripts/performance/run_mas_performance_baseline.py`, which
runs the same functions with the full sample counts.

No timing threshold is asserted anywhere. A test that fails because a laptop
was busy is a test people learn to ignore.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    RoundingPolicy,
    ScoreSourceKind,
    SourceEventProvenanceV1,
)
from master_all_strings.media.catalog import LessonMediaCatalogV1
from master_all_strings.media.contracts import (
    MEDIA_SCHEMA_VERSION,
    LessonMediaReferenceV1,
    LessonMediaV1,
    MediaSourceV1,
)
from master_all_strings.mvp.demo_library import load_demo_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Small on purpose. The baseline runner uses the full sizes.
TEST_SIZES = (100, 1000)


def sample(fn: Callable[[], Any], *, iterations: int = 20, warmup: int = 5) -> dict[str, float]:
    """Repeated timings of one call, in milliseconds."""

    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    samples.sort()
    return {
        "iterations": float(iterations),
        "median_ms": samples[len(samples) // 2],
        "p95_ms": samples[min(len(samples) - 1, int(0.95 * len(samples)))],
        "min_ms": samples[0],
        "max_ms": samples[-1],
    }


def build_catalog(media_count: int, references_per_lesson: int = 8) -> LessonMediaCatalogV1:
    media = tuple(
        LessonMediaV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            media_id=f"bench-media-{index:05d}",
            media_type="video",
            title=f"Benchmark media {index}",
            source=MediaSourceV1(
                kind="local_file",
                relative_path=f"bench/bench-{index:05d}.mp4",
                mime_type="video/mp4",
            ),
            duration_seconds=30.0,
        )
        for index in range(media_count)
    )
    # References point at the *end* of the media tuple, which is where a linear
    # scan is most expensive -- the interesting case, not the flattering one.
    references = tuple(
        LessonMediaReferenceV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            reference_id=f"bench-ref-{index:05d}",
            lesson_key="bench-lesson",
            media_id=f"bench-media-{media_count - 1 - index:05d}",
            role="demonstration",
            sort_order=index,
        )
        for index in range(min(references_per_lesson, media_count))
    )
    return LessonMediaCatalogV1(media=media, references=references)


def build_provenance(entry_count: int) -> RevisionProvenanceV1:
    entries = tuple(
        SourceEventProvenanceV1(
            schema_version=SourceEventProvenanceV1.SCHEMA_VERSION,
            canonical_event_id=f"bench-canonical-{index:05d}",
            source_capture_event_ids=(f"capture-{index:05d}",),
            source_channel=0,
            observed_source_string=None,
            source_capture_time_ns=index * 1_000_000,
            source_release_time_ns=index * 1_000_000 + 500_000,
            converted_start_tick=index * 480,
            converted_duration_ticks=480,
            rounding_delta_start_ns=0,
            rounding_delta_duration_ns=0,
            rounding_policy=RoundingPolicy.ROUND_HALF_AWAY_FROM_ZERO,
            ticks_per_quarter=480,
            microseconds_per_quarter=500_000,
        )
        for index in range(entry_count)
    )
    return RevisionProvenanceV1(
        schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
        source_kind=ScoreSourceKind.PERFORMANCE_CAPTURE,
        policy_version="1.0.0",
        source_reference="bench-capture",
        event_provenance=entries,
    )


# --- M6: media catalog ---------------------------------------------------------


@pytest.mark.parametrize("size", TEST_SIZES)
def test_catalog_lookup_is_correct_and_timed(size: int) -> None:
    catalog = build_catalog(size)
    first = f"bench-media-{0:05d}"
    last = f"bench-media-{size - 1:05d}"

    assert catalog.get(first).media_id == first
    assert catalog.get(last).media_id == last
    assert catalog.contains(last)
    assert not catalog.contains("bench-media-missing")

    timings = {
        "get_first": sample(lambda: catalog.get(first)),
        "get_last": sample(lambda: catalog.get(last)),
        "contains_missing": sample(lambda: catalog.contains("bench-media-missing")),
        "media_for_lesson": sample(lambda: catalog.media_for_lesson("bench-lesson")),
    }
    assert all(entry["median_ms"] >= 0 for entry in timings.values())


@pytest.mark.parametrize("size", TEST_SIZES)
def test_media_for_lesson_returns_every_reference(size: int) -> None:
    # The correctness claim beside the timing: a faster lookup later must
    # return exactly this.
    catalog = build_catalog(size)
    resolved = catalog.media_for_lesson("bench-lesson")
    assert len(resolved) == min(8, size)
    assert [item.media_id for item in resolved] == [
        f"bench-media-{size - 1 - index:05d}" for index in range(len(resolved))
    ]


# --- M7: demo manifest ----------------------------------------------------------


def test_the_manifest_is_reread_on_every_call() -> None:
    # Not a timing claim: a structural one. Two calls produce equal values
    # from separate parses, which is what makes a cache a safe change later.
    first = load_demo_manifest()
    second = load_demo_manifest()
    assert first == second
    assert first is not second
    timings = sample(load_demo_manifest, iterations=10, warmup=2)
    assert timings["median_ms"] >= 0


# --- M8: provenance -------------------------------------------------------------


@pytest.mark.parametrize("size", TEST_SIZES)
def test_provenance_lookup_is_correct_and_timed(size: int) -> None:
    provenance = build_provenance(size)
    first = f"bench-canonical-{0:05d}"
    last = f"bench-canonical-{size - 1:05d}"

    assert provenance.for_event(first) is not None
    assert provenance.for_event(last) is not None
    assert provenance.for_event("bench-canonical-missing") is None

    timings = {
        "first": sample(lambda: provenance.for_event(first)),
        "last": sample(lambda: provenance.for_event(last)),
        "missing": sample(lambda: provenance.for_event("bench-canonical-missing")),
    }
    assert all(entry["median_ms"] >= 0 for entry in timings.values())


def test_no_timing_threshold_is_asserted_in_this_file() -> None:
    # The rule this tranche runs on, enforced against itself: benchmarks
    # record numbers, they do not gate the build on them.
    source = Path(__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("assert") and "_ms" in stripped:
            assert ">= 0" in stripped, f"timing threshold asserted: {stripped}"


def test_the_workload_sizes_match_the_shared_vocabulary() -> None:
    # 100 / 1000 / 10000 is the vocabulary the whole tranche reports in. This
    # file runs the two cheap sizes; the baseline runner covers all three.
    plan = (REPO_ROOT / "docs" / "performance" / "MAS_RUNTIME_PERFORMANCE_PLAN.md").read_text(
        encoding="utf-8"
    )
    assert "10,000" in plan
    assert set(TEST_SIZES) <= {100, 1000, 10000}
