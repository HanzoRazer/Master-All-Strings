#!/usr/bin/env python3
"""Validate the Lesson Media catalog (DO-011)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from master_all_strings.media.catalog import default_media_root, load_media_catalog  # noqa: E402
from master_all_strings.media.validation import (  # noqa: E402
    MediaValidationError,
    validate_media_catalog,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root or default_media_root()
    try:
        catalog = load_media_catalog(root)
        validate_media_catalog(catalog, asset_root=root / "examples")
    except (OSError, MediaValidationError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print(f"OK media catalog ({len(catalog.media)} media, {len(catalog.references)} refs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
