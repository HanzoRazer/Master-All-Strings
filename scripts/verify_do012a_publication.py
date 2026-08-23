#!/usr/bin/env python3
"""DO-012A publication verifier.

Mechanises the checks that decide whether MVP 2B is safely publishable, so the
closeout is re-runnable rather than a one-time assertion in a report.

Deliberately narrow. It answers questions about *identity, scope and evidence
completeness* -- what landed, what must not have landed, and whether the evidence
pack describes it. It performs no musical, spatial, performance or educational
validation: those authorities already have their own suites, and duplicating
them here would create a second opinion about domain truth.

Output is ASCII only. A verifier that cannot print its own result on a cp1252
console is not a verifier.

Usage:
    python scripts/verify_do012a_publication.py [--base SHA] [--head REF]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The immutable predecessor. Never changes, in any tranche.
MVP1_RELEASE_SHA = "ac38819b23ed9d85b651755e7612f42d7d528ddc"

#: The DO-012 base that PR #20 built on.
DO012_BASE_SHA = "2695993a601f6cc7b526294bdaac50ec5650cc23"

#: Hygiene work explicitly deferred out of DO-012 and DO-012A by D21 and D22.
#: These paths are not forbidden forever -- they are forbidden *in this tranche*,
#: and the whole point of checking mechanically is that "we remembered not to"
#: stops being a claim and becomes a test.
DEFERRED_HYGIENE_PATHS: frozenset[str] = frozenset(
    {
        ".gitattributes",
        ".github/workflows/verify.yml",
        "scripts/verify_mvp1_release_lineage.py",
    }
)

#: Fields the Dev Order requires in the machine-readable evidence pack.
REQUIRED_EVIDENCE_FIELDS: tuple[str, ...] = (
    "do012_base_sha",
    "do012_product_sha",
    "evidence_sha",
    "sync_health_samples",
    "do009_digest",
    "wsl_linux_results",
    "node_results",
    "browser_smoke",
    "windows_environment_exceptions",
    "deferred_out_of_scope_work",
)

#: Fields added once the alignment merge and documentation closeout exist.
PUBLICATION_EVIDENCE_FIELDS: tuple[str, ...] = (
    "alignment_pr",
    "alignment_head_sha",
    "alignment_merge_sha",
    "post_merge_main_sha",
    "publication_status",
    "mvp2b_baseline_sha",
)

#: The public timeline surface DO-012 names. Renaming any of these silently
#: would leave the order describing a contract the code no longer offers.
NAMED_TIMELINE_UTILITIES: tuple[str, ...] = (
    "validate_timeline_anchors",
    "seconds_to_tick_from_anchors",
    "tick_to_seconds_from_anchors",
    "lesson_time_to_media_time",
    "media_time_to_lesson_time",
    "build_teaching_playhead_state",
)

NAMED_SYNCHRONIZATION_UTILITIES: tuple[str, ...] = (
    "calculate_drift_ms",
    "classify_sync_health",
    "choose_sync_correction",
)

EVIDENCE_PATH = Path("docs/mvp2/DO012_INTEGRATION_EVIDENCE.json")

PRESENTATION_EXAMPLES = Path("resources/presentation/examples")

#: Health fixtures carry one authoritative prefix. The pre-alignment name was
#: ``health_*``; leaving both alive would mean two naming conventions competing
#: inside the same evidence set, and a reader could not tell which was current.
SYNC_HEALTH_PREFIX = "sync_health_"
LEGACY_HEALTH_PREFIX = "health_"


# --- pure predicates ---------------------------------------------------------
#
# Everything below takes its input as an argument rather than reaching for the
# repository, so the classification logic can be tested against synthetic cases
# instead of against whatever branch happens to exist locally.


def deferred_hygiene_in(changed_paths: Iterable[str]) -> tuple[str, ...]:
    """Deferred-hygiene paths present in a change set, sorted.

    Takes the change set rather than computing it, so a test can hand it a
    synthetic list. A check that can only run against a real branch is a check
    nobody can prove works.
    """

    return tuple(sorted({path for path in changed_paths if path in DEFERRED_HYGIENE_PATHS}))


def missing_evidence_fields(
    payload: dict[str, Any], *, required: Sequence[str] = REQUIRED_EVIDENCE_FIELDS
) -> tuple[str, ...]:
    """Required fields that are absent or still ``None``.

    Present-but-null counts as missing: a placeholder key is exactly the shape a
    half-finished evidence pack has, and it should not read as complete.
    """

    return tuple(name for name in required if payload.get(name) is None)


def inconsistent_baseline_fields(payload: dict[str, Any]) -> tuple[str, ...]:
    """Internal contradictions in the recorded publication identities."""

    problems: list[str] = []
    base = payload.get("do012_base_sha")
    if base is not None and base != DO012_BASE_SHA:
        problems.append(f"do012_base_sha is {base}, expected {DO012_BASE_SHA}")

    merge = payload.get("alignment_merge_sha")
    post_merge = payload.get("post_merge_main_sha")
    baseline = payload.get("mvp2b_baseline_sha")

    if merge is not None and post_merge is not None and merge != post_merge:
        problems.append(
            "post_merge_main_sha must be the alignment merge commit itself"
        )
    # The baseline is the documentation closeout, which lands *after* the merge.
    # Recording them as equal would mean the baseline predates the evidence that
    # is supposed to describe it.
    if baseline is not None and merge is not None and baseline == merge:
        problems.append(
            "mvp2b_baseline_sha must be the post-merge documentation commit, "
            "not the alignment merge commit"
        )
    if baseline is not None and merge is None:
        problems.append("mvp2b_baseline_sha recorded without alignment_merge_sha")
    return tuple(problems)


def verify_fixture_naming(fixture_names: Iterable[str]) -> tuple[str, ...]:
    """Health fixtures using the superseded ``health_*`` name, sorted.

    Takes the names rather than reading the directory, so the rule can be tested
    against synthetic sets. Only health fixtures are policed: every other
    fixture in the directory has its own naming and is none of this check's
    business.
    """

    offenders: list[str] = []
    for name in fixture_names:
        stem = name.rsplit("/", 1)[-1]
        if stem.startswith(SYNC_HEALTH_PREFIX):
            continue
        if stem.startswith(LEGACY_HEALTH_PREFIX):
            offenders.append(stem)
    return tuple(sorted(offenders))


def presentation_fixture_names(root: Path | None = None) -> tuple[str, ...]:
    """Every presentation example fixture, including the invalid subdirectory."""

    base = root or (REPO_ROOT / PRESENTATION_EXAMPLES)
    if not base.is_dir():
        return ()
    return tuple(sorted(path.name for path in base.rglob("*.json")))


def contracts_declaring_revision_id(module: Any) -> tuple[str, ...]:
    """Presentation dataclasses that declare ``canonical_revision_id``.

    DO-013 owns revision provenance. A presentation contract that grows the field
    early would let derived state imply an authority it does not have.
    """

    offenders: list[str] = []
    for name in sorted(dir(module)):
        value = getattr(module, name)
        if not is_dataclass(value) or isinstance(value, type) is False:
            continue
        if any(f.name == "canonical_revision_id" for f in fields(value)):
            offenders.append(name)
    return tuple(offenders)


def missing_named_utilities(module: Any, expected: Sequence[str]) -> tuple[str, ...]:
    """Named utilities the module does not export."""

    return tuple(name for name in expected if not hasattr(module, name))


# --- repository probes -------------------------------------------------------


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def _git_ok(*args: str) -> bool:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def changed_paths(base: str, head: str) -> tuple[str, ...]:
    """Paths differing between ``base`` and ``head`` along their merge base."""

    output = _git("diff", "--name-only", f"{base}...{head}")
    return tuple(line for line in output.splitlines() if line.strip())


def mvp1_unchanged() -> bool:
    return _git("rev-parse", "mvp-1^{commit}") == MVP1_RELEASE_SHA


def is_ancestor(candidate: str, descendant: str) -> bool:
    return _git_ok("merge-base", "--is-ancestor", candidate, descendant)


def merge_parent_count(ref: str) -> int:
    output = _git("rev-list", "--parents", "-n", "1", ref)
    return max(0, len(output.split()) - 1)


def load_evidence(path: Path | None = None) -> dict[str, Any]:
    target = path or (REPO_ROOT / EVIDENCE_PATH)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("evidence pack must be a JSON object")
    return payload


# --- report ------------------------------------------------------------------


def _check(results: list[tuple[bool, str]], ok: bool, message: str) -> None:
    results.append((ok, message))


def run(base: str, head: str, *, require_publication: bool = False) -> int:
    """Run every check and print an ASCII report. Returns a process exit code."""

    results: list[tuple[bool, str]] = []

    _check(results, mvp1_unchanged(), f"mvp-1 unchanged at {MVP1_RELEASE_SHA[:12]}")
    _check(
        results,
        is_ancestor(DO012_BASE_SHA, head),
        f"DO-012 base {DO012_BASE_SHA[:12]} is an ancestor of {head}",
    )

    delta = changed_paths(base, head)
    offenders = deferred_hygiene_in(delta)
    _check(
        results,
        not offenders,
        "deferred hygiene absent from the alignment delta"
        + (f" (found {', '.join(offenders)})" if offenders else ""),
    )

    from master_all_strings.presentation import contracts, synchronization, timeline

    revision = contracts_declaring_revision_id(contracts)
    _check(
        results,
        not revision,
        "no presentation contract declares canonical_revision_id"
        + (f" (found on {', '.join(revision)})" if revision else ""),
    )

    absent = missing_named_utilities(timeline, NAMED_TIMELINE_UTILITIES)
    absent += missing_named_utilities(synchronization, NAMED_SYNCHRONIZATION_UTILITIES)
    _check(
        results,
        not absent,
        "named utilities are importable" + (f" (missing {', '.join(absent)})" if absent else ""),
    )

    stale = verify_fixture_naming(presentation_fixture_names())
    _check(
        results,
        not stale,
        "health fixtures use the sync_health_ prefix"
        + (f" (found {', '.join(stale)})" if stale else ""),
    )

    evidence = load_evidence()
    required = list(REQUIRED_EVIDENCE_FIELDS)
    if require_publication:
        required += list(PUBLICATION_EVIDENCE_FIELDS)
    missing = missing_evidence_fields(evidence, required=required)
    _check(
        results,
        not missing,
        "evidence pack fields present" + (f" (missing {', '.join(missing)})" if missing else ""),
    )

    problems = inconsistent_baseline_fields(evidence)
    _check(
        results,
        not problems,
        "baseline identities consistent" + (f" ({'; '.join(problems)})" if problems else ""),
    )

    if require_publication:
        merge_sha = str(evidence.get("alignment_merge_sha", ""))
        _check(
            results,
            merge_parent_count(merge_sha) == 2,
            f"alignment merge {merge_sha[:12]} has two parents",
        )

    for ok, message in results:
        print(f"{'OK  ' if ok else 'FAIL'} {message}")

    failures = [message for ok, message in results if not ok]
    if failures:
        print(f"DO-012A publication: FAIL ({len(failures)} of {len(results)})", file=sys.stderr)
        return 1
    print("DO-012A publication: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="comparison base ref")
    parser.add_argument("--head", default="HEAD", help="ref under verification")
    parser.add_argument(
        "--require-publication",
        action="store_true",
        help="also require the post-merge publication fields",
    )
    args = parser.parse_args(argv)
    return run(args.base, args.head, require_publication=args.require_publication)


if __name__ == "__main__":
    raise SystemExit(main())
