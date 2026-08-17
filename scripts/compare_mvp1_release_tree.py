#!/usr/bin/env python3
"""Compare a publication candidate tree against original MVP 1 product HEAD.

Classification is intentionally honest. Documentation, CI, release tooling,
generated governance views, and the explicit post-freeze correctness patch are
reported separately. Canonical governance source and unknown product/runtime
paths fail the gate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "7a9b68455b84b065fcd6b184c0903b292d090ef7"

# Review-required localhost API correctness fixes applied after product freeze.
# These are NOT documentation; they must remain an explicit, narrow allowlist.
# Do not expand without a new release authorization.
PRODUCT_CORRECTNESS_PATCH_PATHS = frozenset(
    {
        "src/master_all_strings/mvp/performance_api.py",
        "tests/mvp/test_performance_api.py",
    }
)

BUCKET_ORDER = (
    "DOCS_ONLY_DIFFERENCE",
    "CI_ONLY_DIFFERENCE",
    "RELEASE_TOOLING_ONLY_DIFFERENCE",
    "GENERATED_GOVERNANCE_ONLY_DIFFERENCE",
    "PRODUCT_CORRECTNESS_PATCH",
    "ARCHITECTURE_DIFFERENCE",
    "PRODUCT_DIFFERENCE",
)

FAILING_BUCKETS = frozenset({"PRODUCT_DIFFERENCE", "ARCHITECTURE_DIFFERENCE"})


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
    if path in PRODUCT_CORRECTNESS_PATCH_PATHS:
        return "PRODUCT_CORRECTNESS_PATCH"
    if path.startswith(".github/"):
        return "CI_ONLY_DIFFERENCE"
    # Generated architecture views only — never the canonical registry.
    if path.startswith("docs/architecture/ENGINE_"):
        return "GENERATED_GOVERNANCE_ONLY_DIFFERENCE"
    # Canonical governance / architecture source authority.
    if path == "governance/engine_architecture_v1.json" or path.startswith("governance/"):
        return "ARCHITECTURE_DIFFERENCE"
    if (
        path.startswith("scripts/verify_mvp1")
        or path.startswith("scripts/verify_no_squash_release_topology")
        or path.startswith("scripts/compare_mvp1")
        or path.startswith("scripts/build_mvp1")
        or path.startswith("scripts/build_do010")
        or path.startswith("tests/mvp/test_mvp1_publication")
    ):
        return "RELEASE_TOOLING_ONLY_DIFFERENCE"
    if path == "README.md" or path.startswith("docs/"):
        return "DOCS_ONLY_DIFFERENCE"
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
        help="Original certified product SHA (default: 7a9b684…)",
    )
    args = parser.parse_args(argv)

    diff = _run(["git", "diff", "--name-only", f"{args.product}..{args.candidate}"])
    paths = [line for line in diff.splitlines() if line.strip()]
    if not paths:
        print("IDENTICAL_PRODUCT_TREE")
        print("RESULT: IDENTICAL_PRODUCT_TREE")
        return 0

    buckets: dict[str, list[str]] = {label: [] for label in BUCKET_ORDER}
    for path in paths:
        buckets[classify(path)].append(path)

    for label in BUCKET_ORDER:
        items = buckets[label]
        if not items:
            continue
        print(f"{label}:")
        for path in items:
            print(f"  {path}")

    failing = [label for label in BUCKET_ORDER if label in FAILING_BUCKETS and buckets[label]]
    if failing:
        print(f"RESULT: {failing[0]}", file=sys.stderr)
        return 1

    present = [label for label in BUCKET_ORDER if buckets[label]]
    if not present:
        print("RESULT: IDENTICAL_PRODUCT_TREE")
        return 0

    # Honest aggregate: never collapse tooling/patches into "documentation only".
    if present == ["DOCS_ONLY_DIFFERENCE"]:
        print("RESULT: DOCS_ONLY_DIFFERENCE")
    elif "PRODUCT_CORRECTNESS_PATCH" in present:
        print("RESULT: ALLOWED_PUBLICATION_DIFFERENCE_WITH_CORRECTNESS_PATCHES")
    else:
        print("RESULT: ALLOWED_PUBLICATION_DIFFERENCE")
    print("CLASSES: " + ",".join(present))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
