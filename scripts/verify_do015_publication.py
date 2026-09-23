#!/usr/bin/env python3
"""Verify the DO-015 publication candidate.

Stage 9 certified the product. This asks a narrower question: is the thing
being published still that product, and does the record say so honestly?

Three claims, and nothing else:

* **lineage** -- the certified product and the Stage 9 merge are ancestors of
  what is being published, and the publication record names them correctly;
* **immutability** -- no protected product surface changed after the certified
  product. Repository hygiene -- docs, tests, scripts, the register -- may
  differ, and does;
* **status** -- the record claims a candidate, not a release. No MVP 2 tag
  here or on origin, and `mvp-1` present, at the sha it has always had.

Tag checks fail closed. A claim about origin that origin could not be asked
about is not a verified claim, and publication is where that distinction has
teeth.

Whether the certification itself still holds is Stage 9's question, and it is
delegated to Stage 9's own tools rather than reimplemented here.

**Two modes, because the question changes once publication happens.** While a
branch is writing the publication record, it is claiming *zero product change*
and a specific branch point, and both are checked. Afterwards, on ``main`` or a
successor branch, neither is answerable: the branch point cannot be
reconstructed, and successor work is supposed to add product code. What
survives publication is narrower and more durable -- the certified product is
still an ancestor, and the certification and publication artifacts are exactly
the bytes that were published. A verifier that kept demanding an unchanged
``src/`` would fail every future tranche and teach people to ignore it.

Output is ASCII only. Exit status 1 means the publication candidate is not
what it says it is.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLICATION = REPO_ROOT / "docs" / "mvp2" / "DO015_PUBLICATION_EVIDENCE.json"
REPORT = REPO_ROOT / "docs" / "mvp2" / "DO015_PUBLICATION_REPORT.md"
CERTIFICATION = REPO_ROOT / "docs" / "mvp2" / "DO015_INTEGRATION_EVIDENCE.json"

#: Runtime product. A change here after certification means what is being
#: published is not what was certified, whatever the record says.
PROTECTED = ("src/master_all_strings/", "web/mvp1/", "resources/", "governance/")

#: Browser tests live under the product tree but are not the product.
NOT_PRODUCT = ("web/mvp1/tests/",)

#: What this run can answer, decided by whether the branch is writing the
#: publication record or living after it.
CANDIDATE_MODE = "publication-candidate"
SUCCESSOR_MODE = "successor"

#: Written once and never rewritten. Stage 9's certification freeze and Stage
#: 10's publication record, including the candidate status that was true when
#: it was written.
FROZEN_ARTIFACTS = (
    "docs/mvp2/DO015_INTEGRATION_EVIDENCE.json",
    "docs/mvp2/DO015_CERTIFICATION_REPORT.md",
    "docs/mvp2/do015_artifacts",
    "docs/mvp2/DO015_PUBLICATION_EVIDENCE.json",
    "docs/mvp2/DO015_PUBLICATION_REPORT.md",
)

#: The publication record itself: a branch that changes these is proposing a
#: publication, not living after one.
PUBLICATION_RECORD = (
    "docs/mvp2/DO015_PUBLICATION_EVIDENCE.json",
    "docs/mvp2/DO015_PUBLICATION_REPORT.md",
)

#: The status a candidate may claim before the owner merges it.
CANDIDATE_STATUS = "READY_FOR_PUBLICATION"

#: Publication is the merge. Nothing in the branch may claim it has happened.
PUBLISHED_STATUS = "PUBLISHED_TO_MAIN"

REQUIRED_LINEAGE = (
    "certified_product_sha",
    "stage9_head_sha",
    "stage9_merge_sha",
    "stage10_base_sha",
    "do015_publication_baseline_sha",
)
REQUIRED_SECTIONS = ("lineage", "product_surface", "tags", "known_limitations")

#: A tag that would claim MVP 2 shipped.
FORBIDDEN_TAG_PREFIXES = ("mvp-2", "v2.")


def _ascii(text: str) -> str:
    return text.replace("—", "-").encode("ascii", "replace").decode("ascii")


def load_publication_evidence(path: Path | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """Read the publication record, or say why it cannot be read."""

    target = path or PUBLICATION
    if not target.exists():
        return None, [f"{target.name} does not exist"]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [f"{target.name} could not be read: {error}"]
    if not isinstance(payload, dict):
        return None, [f"{target.name} is not an object"]
    return payload, []


def missing_fields(evidence: dict[str, Any]) -> tuple[str, ...]:
    """Sections and lineage fields the record must carry to mean anything."""

    missing = [section for section in REQUIRED_SECTIONS if section not in evidence]
    lineage = evidence.get("lineage")
    if not isinstance(lineage, dict):
        return tuple(missing + ["lineage"])
    # The baseline is required to be *present*, and required to be null until
    # the merge that creates it exists. Absent and null are different claims.
    missing += [field for field in REQUIRED_LINEAGE if field not in lineage]
    return tuple(sorted(set(missing)))


def verify_lineage(
    evidence: dict[str, Any],
    certification: dict[str, Any],
    is_ancestor: Callable[[str, str], bool],
    head: str = "HEAD",
) -> tuple[str, ...]:
    """The record's shas must be the certified ones, and must lead to head."""

    problems: list[str] = []
    lineage = evidence.get("lineage", {})
    certified = str(lineage.get("certified_product_sha", ""))
    certified_by_stage9 = str(certification.get("lineage", {}).get("certified_product_sha", ""))
    if certified != certified_by_stage9:
        problems.append(
            f"publication names certified product {certified or '(none)'}, "
            f"but Stage 9 certified {certified_by_stage9 or '(none)'}"
        )
    merge = str(lineage.get("stage9_merge_sha", ""))
    base = str(lineage.get("stage10_base_sha", ""))
    for sha, what in (
        (certified, "certified product"),
        (merge, "Stage 9 merge"),
        (base, "Stage 10 base"),
    ):
        if not sha:
            continue
        if not is_ancestor(sha, head):
            problems.append(f"{what} {sha[:7]} is not an ancestor of {head}")
    if certified and merge and not is_ancestor(certified, merge):
        problems.append(
            f"certified product {certified[:7]} is not an ancestor of the "
            f"Stage 9 merge {merge[:7]}"
        )
    # Publishing from a base that predates the certification would publish
    # something the evidence does not describe.
    if merge and base and not is_ancestor(merge, base):
        problems.append(
            f"Stage 10 base {base[:7]} does not contain the Stage 9 merge {merge[:7]}"
        )
    return tuple(problems)


def verify_branch_point(
    recorded_base: str, branch_point: str | None, head_sha: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The recorded base must *be* the commit this branch was cut from.

    Ancestry alone is too weak: every commit back to the certification is an
    ancestor of this branch, so a base naming any of them would pass while
    misstating what was published from where. Returns (problems, notes).
    """

    if not branch_point or not head_sha:
        return (), ("branch point unknown: stage10_base_sha could not be enforced",)
    if branch_point == head_sha:
        # This history already contains origin/main's tip -- the branch has
        # merged, or main has not moved past it. There is no branch point left
        # to compare, and a verdict here would be invented.
        return (), ("branch point is HEAD: stage10_base_sha not enforced from here",)
    if recorded_base != branch_point:
        return (
            (
                f"stage10_base_sha is {recorded_base[:7]}, but this branch was cut "
                f"from {branch_point[:7]}",
            ),
            (),
        )
    return (), ()


def protected_product_changes(changed: Iterable[str]) -> tuple[str, ...]:
    """The protected product paths among changed ones.

    Everything else -- docs, tests, scripts, the register, this stage's own
    files -- is repository hygiene, and hygiene after certification is allowed.
    Requiring an empty diff would make publication tooling unusable after any
    maintenance at all.
    """

    return tuple(
        sorted(
            path
            for path in changed
            if path.startswith(PROTECTED) and not path.startswith(NOT_PRODUCT)
        )
    )


def verify_publication_status(evidence: dict[str, Any]) -> tuple[str, ...]:
    """A branch may offer a candidate. It may not announce the merge."""

    status = str(evidence.get("status", ""))
    if status == CANDIDATE_STATUS:
        return ()
    if status == PUBLISHED_STATUS:
        return (
            f"status is {PUBLISHED_STATUS} before the merge that would make it "
            f"true; a candidate says {CANDIDATE_STATUS}",
        )
    return (f"status is {status or '(none)'}, expected {CANDIDATE_STATUS}",)


def verify_tag_state(
    local: Sequence[str],
    remote: Sequence[str] | None,
    expected_mvp1: str = "",
    observed_mvp1: str = "",
) -> tuple[tuple[str, ...], str]:
    """No MVP 2 tag anywhere, and `mvp-1` present and where the record says.

    Fails closed, and that is the difference between this and the in-flight
    checker. There, an unanswerable question is nobody's to fix and becomes a
    note. Here the publication record *claims* no MVP 2 tag exists on origin;
    an origin that cannot be listed has not established that claim, so the
    claim fails rather than the check passing quietly.

    Returns the problems and the remote verdict.
    """

    problems: list[str] = []
    forbidden = sorted(
        {tag for tag in [*local, *(remote or [])] if tag.startswith(FORBIDDEN_TAG_PREFIXES)}
    )
    if forbidden:
        # Reported, never removed: an unexpected release tag is somebody's
        # decision to explain, not this script's to undo.
        problems.append(f"tags claiming MVP 2 exist: {', '.join(forbidden)} -- stop and report")
    if remote is None:
        problems.append(
            "origin's tags could not be listed, so 'no MVP 2 tag on origin' is "
            "unproven -- publication will not claim what it could not check"
        )
    if expected_mvp1 and not observed_mvp1:
        # The invariant is that mvp-1 is at a known sha, which a deleted or
        # unresolvable tag does not satisfy any more than a moved one does.
        problems.append(
            f"mvp-1 is absent or unresolved; the record says it is at {expected_mvp1[:7]}"
        )
    elif expected_mvp1 and expected_mvp1 != observed_mvp1:
        problems.append(f"mvp-1 is {observed_mvp1[:7]}, but the record says {expected_mvp1[:7]}")
    return tuple(problems), "NOT_AVAILABLE" if remote is None else "PASS"


def mode_for(publication_record_changes: Sequence[str] | None) -> str:
    """Which question this run can answer.

    A branch that touches the publication record is writing it, and must prove
    what Stage 10 claimed. Anything else is downstream of a publication that
    already happened. When the comparison cannot be made at all, the successor
    mode is the honest default: it asserts less, and asserting more on a guess
    is how a check starts lying.
    """

    return CANDIDATE_MODE if publication_record_changes else SUCCESSOR_MODE


def frozen_artifact_violations(
    last_touched: Mapping[str, str | None],
    baseline: str | None,
    is_ancestor: Callable[[str, str], bool],
) -> tuple[str, ...]:
    """Frozen artifacts must not have been touched after publication.

    The publication merge is the boundary: every commit that touched a frozen
    artifact has to be at or before it. An edit afterwards -- filling in a
    baseline sha, flipping a status to read better, refreshing a report --
    rewrites a statement about a moment that has passed, which is the one
    thing an evidence freeze exists to prevent.
    """

    if baseline is None:
        return ()
    problems = []
    for path, commit in sorted(last_touched.items()):
        if commit is None:
            problems.append(f"{path} is missing: it is part of the published record")
            continue
        if not is_ancestor(commit, baseline):
            problems.append(
                f"{path} was modified in {commit[:7]}, after the publication "
                f"at {baseline[:7]}; the published record is not editable"
            )
    return tuple(problems)


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def is_ancestor(candidate: str, descendant: str) -> bool:
    return _git("merge-base", "--is-ancestor", candidate, descendant) is not None


def changed_against(ref: str, paths: Sequence[str], head: str = "HEAD") -> tuple[str, ...] | None:
    """Paths differing between ``ref`` and ``head``, or None if ref is unknown."""

    out = _git("diff", "--name-only", f"{ref}...{head}", "--", *paths)
    if out is None:
        return None
    return tuple(sorted(line.strip() for line in out.splitlines() if line.strip()))


def publication_baseline(head: str = "HEAD") -> str | None:
    """The merge that put the publication record on the mainline.

    Derived, not recorded. The evidence deliberately carries a null baseline --
    a commit cannot name the merge that will contain it -- so the sha is read
    back out of first-parent history instead, where the merge is the commit
    that introduced the file.
    """

    out = _git(
        "log",
        "--first-parent",
        "--format=%H",
        "--diff-filter=A",
        head,
        "--",
        "docs/mvp2/DO015_PUBLICATION_EVIDENCE.json",
    )
    if out is None:
        return None
    commits = [line.strip() for line in out.splitlines() if line.strip()]
    return commits[-1] if commits else None


def last_commit_touching(path: str, head: str = "HEAD") -> str | None:
    out = _git("log", "-1", "--format=%H", head, "--", path)
    return out.strip() if out and out.strip() else None


def branch_point(head: str = "HEAD", against: str = "origin/main") -> str | None:
    """The commit this branch was cut from, or None when it cannot be found."""

    out = _git("merge-base", head, against)
    return out.strip() if out and out.strip() else None


def changed_paths(base: str, head: str) -> tuple[str, ...]:
    out = _git("diff", "--name-only", base, head)
    return tuple(sorted(line.strip() for line in (out or "").splitlines() if line.strip()))


def tags_here_and_on_origin() -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    """Local tags, and origin's -- None when origin could not be asked."""

    local = tuple((_git("tag", "-l") or "").split())
    out = _git("ls-remote", "--tags", "origin")
    if out is None:
        return local, None
    refs = (ref for _, _, ref in (line.partition("\t") for line in out.splitlines()))
    remote = {
        ref[len("refs/tags/") :].removesuffix("^{}")
        for ref in refs
        if ref.startswith("refs/tags/")
    }
    return local, tuple(sorted(remote))


def tag_sha(tag: str) -> str:
    return (_git("rev-list", "-n", "1", tag) or "").strip()


def verify_certification_is_still_valid(
    run: Callable[[list[str]], int] | None = None,
) -> tuple[str, ...]:
    """Delegate to Stage 9's own tools rather than re-deriving their answers."""

    runner = run or _script
    problems = []
    for command, what in (
        (["scripts/verify_do015_certification.py"], "certification verifier"),
        (
            ["scripts/build_do015_certification_evidence.py", "--check"],
            "certification evidence generator",
        ),
    ):
        if runner(command) != 0:
            problems.append(f"Stage 9 {what} does not pass on this tree")
    return tuple(problems)


def _script(command: list[str]) -> int:
    try:
        return subprocess.run(
            [sys.executable, *command], cwd=REPO_ROOT, check=False, timeout=900
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the DO-015 publication candidate")
    parser.add_argument("--evidence", type=Path, default=PUBLICATION)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--offline", action="store_true", help="skip the checks that need git or Stage 9's tools"
    )
    args = parser.parse_args(argv)

    evidence, problems = load_publication_evidence(args.evidence)
    if evidence is None:
        for problem in problems:
            print(_ascii(f"FAIL {problem}"))
        return 1

    checks: list[tuple[str, tuple[str, ...]]] = []
    notes: list[str] = []

    checks.append(("required publication fields", missing_fields(evidence)))
    checks.append(("publication status", verify_publication_status(evidence)))
    checks.append(
        ("publication report exists", () if REPORT.exists() else (f"{REPORT.name} is missing",))
    )

    if args.offline:
        notes.append("offline: lineage, product surface, tags and Stage 9's tools were not run")
    else:
        certification, unreadable = load_publication_evidence(CERTIFICATION)
        checks.append(("Stage 9 evidence readable", tuple(unreadable)))
        checks.append(
            ("lineage", verify_lineage(evidence, certification or {}, is_ancestor, args.head))
        )

        record_changes = changed_against("origin/main", PUBLICATION_RECORD, args.head)
        mode = mode_for(record_changes)
        if record_changes is None:
            notes.append("origin/main could not be read; running in successor mode")
        notes.append(f"mode: {mode}")

        certified = str(evidence.get("lineage", {}).get("certified_product_sha", ""))
        if mode == CANDIDATE_MODE:
            base_problems, base_notes = verify_branch_point(
                str(evidence.get("lineage", {}).get("stage10_base_sha", "")),
                branch_point(args.head),
                (_git("rev-parse", args.head) or "").strip() or None,
            )
            checks.append(("stage10_base_sha is the branch point", base_problems))
            notes.extend(base_notes)
            if certified:
                changed = protected_product_changes(changed_paths(certified, args.head))
                checks.append(
                    (
                        "protected product surface unchanged since certification",
                        tuple(f"{path} changed after the certified product" for path in changed),
                    )
                )
        else:
            # Successor work adds product code -- that is what a successor is.
            # What must not move is the published record of what was certified.
            baseline = publication_baseline(args.head)
            last_touched = {
                path: last_commit_touching(path, args.head) for path in FROZEN_ARTIFACTS
            }
            checks.append(
                (
                    "certification and publication artifacts are as published",
                    frozen_artifact_violations(last_touched, baseline, is_ancestor),
                )
            )
            if baseline is None:
                notes.append("no publication merge found; frozen artifacts were not checked")
            else:
                notes.append(f"published at {baseline[:7]}; Stage 10's branch point is history")

        recorded = evidence.get("tags", {}).get("mvp1", {})
        name = str(recorded.get("tag", "mvp-1"))
        local, remote = tags_here_and_on_origin()
        problems_found, verdict = verify_tag_state(
            local, remote, str(recorded.get("sha", "")), tag_sha(name)
        )
        checks.append(("tags", problems_found))
        if verdict == "NOT_AVAILABLE":
            notes.append("remote_tag_verdict = NOT_AVAILABLE, which fails publication")

        checks.append(("Stage 9 certification still passes", verify_certification_is_still_valid()))

    for note in notes:
        print(_ascii(f"note {note}"))
    failures = 0
    for label, found in checks:
        if found:
            failures += 1
            print(_ascii(f"FAIL {label}"))
            for item in found:
                print(_ascii(f"     {item}"))
        else:
            print(_ascii(f"OK   {label}"))

    if failures:
        print(_ascii(f"\nDO-015 publication: {failures} problem(s)"))
        return 1
    print(_ascii(f"DO-015 publication: OK ({len(checks)} of {len(checks)})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
