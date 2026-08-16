#!/usr/bin/env python3
"""Update machine-readable MVP 1 publication evidence fields."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs" / "mvp" / "MVP1_PUBLICATION_EVIDENCE.json"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-status", default=None)
    parser.add_argument("--candidate-sha", default=None)
    parser.add_argument("--pull-request", default=None)
    parser.add_argument("--merged-sha", default=None)
    parser.add_argument("--release-sha", default=None)
    parser.add_argument("--github-ci", default=None)
    parser.add_argument("--tree-equivalence", default=None)
    args = parser.parse_args()

    data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    if args.publication_status:
        data["publication_status"] = args.publication_status
    if args.candidate_sha:
        data["candidate_sha"] = args.candidate_sha
    elif data.get("candidate_sha") is None:
        data["candidate_sha"] = _git("rev-parse", "HEAD")
    if args.pull_request is not None:
        data["pull_request"] = args.pull_request
    if args.merged_sha is not None:
        data["merged_sha"] = args.merged_sha
    if args.release_sha is not None:
        data["release_sha"] = args.release_sha
    if args.github_ci is not None:
        data["github_ci"] = args.github_ci
    if args.tree_equivalence is not None:
        data["tree_equivalence"]["product_paths_vs_7a9b684"] = args.tree_equivalence

    EVIDENCE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(EVIDENCE_PATH), "status": data["publication_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
