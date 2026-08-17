#!/usr/bin/env python3
"""Verify the frozen Master All Strings MVP 1 ancestry chain (DO-010A-R)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DO008 = "f9018213fb9097cb716a8c91670ae03f7ed1b514"
DO009 = "92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec"
ORIGINAL_PRODUCT = "7a9b68455b84b065fcd6b184c0903b292d090ef7"
ORIGINAL_EVIDENCE = "b727cce6da108667d7dc1823df17f85cdeb9d810"
CORRECTED_PRODUCT = "f028549b145bf3f567e936d5d7e29ab2f93f63d3"
SQUASH = "a198c7b30370d077e7213b4ebeab170c769aaaff"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def resolve(ref: str) -> str:
    result = _run(["git", "rev-parse", f"{ref}^{{commit}}"])
    if result.returncode != 0:
        raise SystemExit(f"unable to resolve {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def is_ancestor(ancestor: str, descendant: str) -> bool:
    result = _run(["git", "merge-base", "--is-ancestor", ancestor, descendant])
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-sha",
        default="HEAD",
        help="Final release/main tip that must descend from corrected product (default: HEAD)",
    )
    parser.add_argument(
        "--recertification-evidence-sha",
        default=None,
        help="Optional recertification evidence commit that must sit between corrected product and release",
    )
    parser.add_argument(
        "--require-not-squash-head",
        action="store_true",
        help="Fail if release SHA equals the PR #18 squash merge commit",
    )
    args = parser.parse_args(argv)

    corrected = resolve(CORRECTED_PRODUCT)
    release = resolve(args.release_sha)
    original_product = resolve(ORIGINAL_PRODUCT)
    original_evidence = resolve(ORIGINAL_EVIDENCE)
    do008 = resolve(DO008)
    do009 = resolve(DO009)
    squash = resolve(SQUASH)

    chain = [
        ("DO-008", do008, "DO-009", do009),
        ("DO-009", do009, "original_product", original_product),
        ("original_product", original_product, "original_evidence", original_evidence),
        ("original_evidence", original_evidence, "corrected_product", corrected),
        ("corrected_product", corrected, "release", release),
    ]
    failures: list[str] = []
    for left_name, left, right_name, right in chain:
        if not is_ancestor(left, right):
            failures.append(f"{left_name} ({left[:12]}) is not an ancestor of {right_name}")
        else:
            print(f"OK  {left_name} → {right_name}")

    if args.recertification_evidence_sha:
        evidence = resolve(args.recertification_evidence_sha)
        if not is_ancestor(corrected, evidence):
            failures.append(
                f"corrected_product ({corrected[:12]}) is not an ancestor of "
                f"recertification evidence ({evidence[:12]})"
            )
        else:
            print(f"OK  corrected_product → recertification_evidence ({evidence[:12]})")
        if not is_ancestor(evidence, release):
            failures.append(
                f"recertification evidence ({evidence[:12]}) is not an ancestor of release"
            )
        else:
            print(f"OK  recertification_evidence → release ({release[:12]})")

    if args.require_not_squash_head or True:
        if release == squash:
            failures.append(f"release tip must not be squash merge {squash[:12]}")
        else:
            print(f"OK  release tip is not squash {squash[:12]}")

    # Certified SHAs must be reachable from the release tip (topology repair proof).
    for name, sha in (
        ("DO-008", do008),
        ("DO-009", do009),
        ("original_product", original_product),
        ("original_evidence", original_evidence),
        ("corrected_product", corrected),
    ):
        if not is_ancestor(sha, release):
            failures.append(f"{name} ({sha[:12]}) is not reachable from release tip")
        else:
            print(f"OK  {name} reachable from release")

    if failures:
        for item in failures:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print("MVP 1 lineage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
