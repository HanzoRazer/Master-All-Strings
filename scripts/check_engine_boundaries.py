#!/usr/bin/env python
"""Thin CLI wrapper for the engine-boundary governance validator.

All logic lives in the importable module so tests do not shell out. This exists
only for a direct local command:

    python scripts/check_engine_boundaries.py            # validate
    python scripts/check_engine_boundaries.py --write-views   # regenerate views

Equivalent to ``python -m master_all_strings.governance.engine_boundaries``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from master_all_strings.governance.engine_boundaries import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
