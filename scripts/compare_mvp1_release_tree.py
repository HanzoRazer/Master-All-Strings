#!/usr/bin/env python3
"""Compare a publication candidate tree against certified MVP 1 product HEAD."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "7a9b68455b84b065fcd6b184c0903b292d090ef7"

# Paths that may differ from product HEAD without counting as product drift.
DOCUMENTATION_PREFIXES = (
    "README.md",
    "docs/",
    "scripts/verify_mvp1_",
    "scripts/compare_mvp1_",
    "scripts/build_mvp1_",
    "scripts/build_do010_evidence.py",
)
GENERATED_PREFIXES = (
    "docs/architecture/ENGINE_",
)


def _run(args: list[str]) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def classify(path: str) -> str:
    if path.startswith("docs/architecture/ENGINE_") or path.startswith("governance/"):
        return "GENERATED_ONLY_DIFFERENCE"
    if (
        path.startswith(DOCUMENTATION_PREFIXES)
        or path.startswith("docs/")
        or path == "README.md"
        or path.startswith("tests/mvp/test_mvp1_publication")
        or path.startswith("scripts/build_do010")
        or path.startswith("scripts/verify_mvp1")
        or path.startswith("scripts/compare_mvp1")
        or path.startswith("scripts/build_mvp1")
    ):
        return "DOCUMENTATION_ONLY_DIFFERENCE"
    return "PRODUCT_DIFFERENCE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        default="HEAD",
        help="Publication candidate ref (default: HEAD)",
    )
    parser.add_argument(
        "--product",
        default=PRODUCT,
        help="Certified product SHA (default: 7a9b684…)",
    )
    args = parser.parse_args(argv)

    diff = _run(["git", "diff", "--name-only", f"{args.product}..{args.candidate}"])
    paths = [line for line in diff.splitlines() if line.strip()]
    if not paths:
        print("IDENTICAL_PRODUCT_TREE")
        return 0

    buckets = {
        "DOCUMENTATION_ONLY_DIFFERENCE": [],
        "GENERATED_ONLY_DIFFERENCE": [],
        "PRODUCT_DIFFERENCE": [],
    }
    for path in paths:
        buckets[classify(path)].append(path)

    for label, items in buckets.items():
        if not items:
            continue
        print(f"{label}:")
        for path in items:
            print(f"  {path}")

    if buckets["PRODUCT_DIFFERENCE"]:
        print("RESULT: PRODUCT_DIFFERENCE", file=sys.stderr)
        return 1
    if buckets["DOCUMENTATION_ONLY_DIFFERENCE"] or buckets["GENERATED_ONLY_DIFFERENCE"]:
        print("RESULT: DOCUMENTATION_ONLY_DIFFERENCE")
        return 0
    print("RESULT: IDENTICAL_PRODUCT_TREE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
