#!/usr/bin/env python3
"""Fail if final release topology is the PR #18 squash merge."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQUASH = "a198c7b30370d077e7213b4ebeab170c769aaaff"
DO008 = "f9018213fb9097cb716a8c91670ae03f7ed1b514"
DO009 = "92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec"
ORIGINAL_PRODUCT = "7a9b68455b84b065fcd6b184c0903b292d090ef7"
CORRECTED_PRODUCT = "f028549b145bf3f567e936d5d7e29ab2f93f63d3"
RECOVERY_REF = "refs/remotes/origin/recovery/mvp1-squash-merge"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=False, text=True, capture_output=True)


def resolve(ref: str) -> str:
    result = _run(["git", "rev-parse", f"{ref}^{{commit}}"])
    if result.returncode != 0:
        raise SystemExit(f"unable to resolve {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def is_ancestor(ancestor: str, descendant: str) -> bool:
    return _run(["git", "merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-sha", default="HEAD")
    args = parser.parse_args(argv)

    release = resolve(args.release_sha)
    squash = resolve(SQUASH)
    failures: list[str] = []

    if release == squash:
        failures.append("release tip equals squash merge commit")
    else:
        print(f"OK  release tip {release[:12]} != squash {squash[:12]}")

    # Squash may remain only via recovery/audit refs, not as mainline ancestry requirement.
    recovery = _run(["git", "rev-parse", RECOVERY_REF])
    if recovery.returncode == 0:
        recovery_sha = recovery.stdout.strip()
        if recovery_sha != squash:
            failures.append(f"recovery ref points to {recovery_sha[:12]}, expected squash")
        else:
            print(f"OK  recovery ref preserves squash {squash[:12]}")
    else:
        # Local-only recovery is acceptable if remote is unavailable in shallow clones.
        local = _run(["git", "rev-parse", "refs/heads/recovery/mvp1-squash-merge"])
        if local.returncode == 0 and local.stdout.strip() == squash:
            print(f"OK  local recovery ref preserves squash {squash[:12]}")
        else:
            print("WARN recovery ref not visible in this clone (object may still exist)")

    for name, ref in (
        ("DO-008", DO008),
        ("DO-009", DO009),
        ("original_product", ORIGINAL_PRODUCT),
        ("corrected_product", CORRECTED_PRODUCT),
    ):
        sha = resolve(ref)
        if not is_ancestor(sha, release):
            failures.append(f"{name} ({sha[:12]}) is not an ancestor of release tip")
        else:
            print(f"OK  {name} ancestor of release")

    parents = _run(["git", "rev-list", "--parents", "-n", "1", squash])
    if parents.returncode == 0:
        parts = parents.stdout.strip().split()
        if len(parts) != 2:
            # squash should be single-parent from GitHub squash-merge
            print(f"OK  squash parent count recorded as {len(parts) - 1}")
        else:
            print("OK  squash is single-parent topology (non-release)")

    if failures:
        for item in failures:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print("no-squash release topology: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
