#!/usr/bin/env python
"""Thin CLI wrapper for read-only performance-runtime inspection.

    python scripts/inspect_performance_runtime.py

Reports configuration validity, the synth registry, fake-runtime health, and a
rendered diagnostic report. It never starts a real runtime and never mutates the
operating system.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from master_all_strings.performance.cli import inspect_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(inspect_main())
