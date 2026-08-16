#!/usr/bin/env python3
"""Verify the frozen Master All Strings MVP 1 ancestry chain."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DO008 = "f9018213fb9097cb716a8c91670ae03f7ed1b514"
DO009 = "92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec"
PRODUCT = "7a9b68455b84b065fcd6b184c0903b292d090ef7"
EVIDENCE = "b727cce6da108667d7dc1823df17f85cdeb9d810"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def is_ancestor(ancestor: str, descendant: str) -> bool:
    result = _run(["git", "merge-base", "--is-ancestor", ancestor, descendant])
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-sha",
        default=None,
        help="Optional final release/merged SHA that must descend from evidence",
    )
    args = parser.parse_args(argv)

    chain = [
        ("DO-008", DO008, "DO-009", DO009),
        ("DO-009", DO009, "product", PRODUCT),
        ("product", PRODUCT, "evidence", EVIDENCE),
    ]
    failures: list[str] = []
    for left_name, left, right_name, right in chain:
        if not is_ancestor(left, right):
            failures.append(f"{left_name} ({left[:12]}) is not an ancestor of {right_name}")
        else:
            print(f"OK  {left_name} → {right_name}")

    if args.release_sha:
        if not is_ancestor(EVIDENCE, args.release_sha):
            failures.append(
                f"evidence ({EVIDENCE[:12]}) is not an ancestor of release {args.release_sha}"
            )
        else:
            print(f"OK  evidence → release ({args.release_sha})")

    if failures:
        for item in failures:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print("MVP 1 lineage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
