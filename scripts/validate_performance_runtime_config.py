#!/usr/bin/env python
"""Thin CLI wrapper for the performance runtime-configuration validator.

All logic lives in the importable module so tests do not shell out. This exists only
for a direct local command:

    python scripts/validate_performance_runtime_config.py
    python scripts/validate_performance_runtime_config.py path/to/config.json

Read-only: validates and reports. Installs nothing, changes no system setting.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from master_all_strings.performance.cli import validate_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(validate_main())
