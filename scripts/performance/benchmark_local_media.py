#!/usr/bin/env python3
"""M9 — what the local server costs when it serves a media file.

The claim under test: the asset route calls ``asset.read_bytes()`` and then
writes the response, so the whole file is resident before a byte is sent, and
concurrent requests multiply that.

Measured against the real ``serve_mvp_directory`` over real sockets, with files
generated into a temporary directory and deleted afterwards. Nothing large is
committed: a hundred-megabyte fixture in git would be a worse problem than the
one being measured.

Peak memory is reported only where the interpreter can answer without a new
dependency -- ``tracemalloc`` sees the allocation the handler makes, which is
the quantity in question.

Emits JSON on stdout. Changes nothing.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from master_all_strings.mvp.local_server import serve_mvp_directory  # noqa: E402

#: Sizes the review asks about. The largest is a video-shaped file.
SIZES_MB = (1, 10, 100)
CONCURRENCY = (1, 2, 4)


def _write_asset(root: Path, size_mb: int) -> Path:
    """A file of the requested size, written in chunks rather than at once."""

    assets = root / "examples"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / f"bench-{size_mb}mb.bin"
    chunk = b"\0" * (1024 * 1024)
    with target.open("wb") as handle:
        for _ in range(size_mb):
            handle.write(chunk)
    return target


def _fetch(url: str) -> int:
    with urllib.request.urlopen(url, timeout=300) as response:
        return len(response.read())


def measure(size_mb: int, media_root: Path, base_url: str, iterations: int) -> dict[str, Any]:
    url = f"{base_url}/media/assets/bench-{size_mb}mb.bin"
    expected = size_mb * 1024 * 1024
    assert _fetch(url) == expected, "the server must return the whole file"

    results: dict[str, Any] = {"bytes": expected}
    for workers in CONCURRENCY:
        samples = []
        for _ in range(iterations):
            started = time.perf_counter_ns()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                lengths = list(pool.map(lambda _: _fetch(url), range(workers)))
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            assert all(length == expected for length in lengths)
            samples.append(elapsed_ms)
        samples.sort()
        median = statistics.median(samples)
        results[f"concurrency_{workers}"] = {
            "iterations": len(samples),
            "median_ms": median,
            "p95_ms": samples[min(len(samples) - 1, int(0.95 * len(samples)))],
            "min_ms": samples[0],
            "max_ms": samples[-1],
            "requests": workers,
            "megabytes_per_second": (expected * workers / (1024 * 1024)) / (median / 1000)
            if median
            else 0.0,
        }

    tracemalloc.start()
    _fetch(url)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results["client_peak_bytes"] = peak
    results["note"] = (
        "peak is this process's allocation for one request; the server handler "
        "reads the whole file into memory before writing it"
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument(
        "--max-mb",
        type=int,
        default=100,
        help="skip sizes above this, for a quicker developer run",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="mas-perf-media-") as raw:
        root = Path(raw)
        (root / "index.html").write_text("<html></html>", encoding="utf-8")
        media_root = root / "media"
        sizes = [size for size in SIZES_MB if size <= args.max_mb]
        for size_mb in sizes:
            _write_asset(media_root, size_mb)

        httpd, _thread, url = serve_mvp_directory(
            root, open_browser=False, media_root=media_root
        )
        base_url = url.rsplit("/", 1)[0]
        try:
            measurements = {
                f"{size_mb}mb": measure(size_mb, media_root, base_url, args.iterations)
                for size_mb in sizes
            }
        finally:
            httpd.shutdown()
            httpd.server_close()

    print(
        json.dumps(
            {
                "benchmark": "local_media_serving",
                "risk": "M9",
                "measures": "end-to-end latency over real sockets against the local server",
                "sizes_mb": sizes,
                "concurrency": list(CONCURRENCY),
                "measurements": measurements,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
