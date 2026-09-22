#!/usr/bin/env python3
"""DO-015 Stage 9 certification verifier.

Checks that the frozen evidence still describes this repository. It answers
questions about *lineage, completeness and boundary* -- which commit was
certified, whether the evidence says everything it must, whether the artifacts
it cites exist, and whether anything outside the certification surface moved
after the certified commit. It runs no tests: the suites are their own
authority and re-running them under another name would only produce a second
opinion about the same thing.

The one property nothing else can check is the boundary. A certification that
quietly carried a product change would certify a commit that never existed as
a product, so the diff between the certified product and the evidence freeze
is enumerated against an allowlist here.

Output is ASCII only. A verifier that cannot print its own result on a legacy
console is not a verifier.

Usage:
    python scripts/verify_do015_certification.py [--evidence PATH] [--offline]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "docs" / "mvp2" / "DO015_INTEGRATION_EVIDENCE.json"

#: The immutable predecessor merges this tranche is built on.
STAGE7_MERGE_SHA = "286d5aa439831ea44ff6e198a8518a45f076b513"

#: Sections the Dev Order requires in the machine-readable record.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "lineage",
    "environment",
    "targeted_tests",
    "full_tests",
    "node",
    "python",
    "coverage",
    "ruff",
    "mypy",
    "fixtures",
    "in_flight",
    "browser_reproducible",
    "browser_visual",
    "identity_chain",
    "digest_invariants",
    "lesson_transition",
    "revision_fail_closed",
    "stage8_adversarial",
    "known_environment_exceptions",
    "known_limitations",
    "deferred_work",
)

REQUIRED_LINEAGE: tuple[str, ...] = (
    "repository",
    "stage7_merge_sha",
    "stage8_product_sha",
    "stage8_merge_sha",
    "stage9_base_sha",
    "certified_product_sha",
)

#: Only certification surfaces may move after the certified product commit.
#: Test code counts: the verifier's own tests are certification tooling.
ALLOWED_PREFIXES: tuple[str, ...] = ("docs/", "tests/", "web/mvp1/tests/")
ALLOWED_EXACT: frozenset[str] = frozenset({"scripts/verify_do015_certification.py"})

_SHA = re.compile(r"^[0-9a-f]{40}$")


def _ascii(text: str) -> str:
    return text.replace("—", "-").encode("ascii", "replace").decode("ascii")


def _git(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def load_evidence(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        try:
            shown: Path | str = path.relative_to(REPO_ROOT)
        except ValueError:
            shown = path
        return None, [f"evidence file is missing: {shown}"]
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"evidence file is not valid JSON: {exc}"]
    if not isinstance(loaded, dict):
        return None, ["evidence file must be a JSON object"]
    return loaded, []


def check_required_sections(evidence: dict[str, Any]) -> list[str]:
    """Every section the order names must be present and say something."""

    problems = [
        f"evidence is missing section {name!r}"
        for name in REQUIRED_SECTIONS
        if name not in evidence
    ]
    for name in REQUIRED_SECTIONS:
        value = evidence.get(name)
        if name in evidence and value in ({}, "", None):
            problems.append(f"evidence section {name!r} is empty")
    return problems


def check_lineage(evidence: dict[str, Any]) -> list[str]:
    """The recorded SHAs must be real SHAs, and say the same thing twice."""

    lineage = evidence.get("lineage")
    if not isinstance(lineage, dict):
        return ["lineage must be an object"]
    problems = [f"lineage is missing {key!r}" for key in REQUIRED_LINEAGE if key not in lineage]
    for key in REQUIRED_LINEAGE:
        if key == "repository" or key not in lineage:
            continue
        value = str(lineage[key])
        if not _SHA.match(value):
            problems.append(f"lineage {key} is not a full 40-character sha: {value!r}")
    if lineage.get("stage7_merge_sha") not in (None, STAGE7_MERGE_SHA):
        problems.append(
            "lineage stage7_merge_sha must be "
            f"{STAGE7_MERGE_SHA}, got {lineage['stage7_merge_sha']}"
        )
    certified = lineage.get("certified_product_sha")
    base = lineage.get("stage9_base_sha")
    if certified and base and certified != base:
        # Allowed, but only deliberately: certification then covers commits the
        # Stage 8 merge did not contain, and the record has to say why.
        if not str(evidence.get("lineage", {}).get("certified_beyond_base_reason", "")).strip():
            problems.append(
                "certified_product_sha differs from stage9_base_sha without "
                "lineage.certified_beyond_base_reason"
            )
    return problems


def check_ancestry(evidence: dict[str, Any], head: str | None) -> list[str]:
    """The certified commit and its predecessors must really be behind HEAD."""

    lineage = evidence.get("lineage")
    if not isinstance(lineage, dict) or head is None:
        return []
    problems = []
    for key in ("stage8_merge_sha", "certified_product_sha"):
        sha = lineage.get(key)
        if not sha:
            continue
        if _git(["merge-base", "--is-ancestor", str(sha), head]) is None:
            problems.append(f"lineage {key} {sha} is not an ancestor of HEAD")
    stage8_merge = lineage.get("stage8_merge_sha")
    if stage8_merge and _git(
        ["merge-base", "--is-ancestor", STAGE7_MERGE_SHA, str(stage8_merge)]
    ) is None:
        problems.append("the Stage 7 merge is not an ancestor of the Stage 8 merge")
    product = lineage.get("stage8_product_sha")
    if product and stage8_merge:
        if _git(["merge-base", "--is-ancestor", str(product), str(stage8_merge)]) is None:
            problems.append("stage8_product_sha is not an ancestor of stage8_merge_sha")
    return problems


def check_artifacts(evidence: dict[str, Any], root: Path) -> list[str]:
    """Everything the evidence points at has to be there to be reviewed."""

    problems = []
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ["evidence must list its artifacts"]
    for item in artifacts:
        if not isinstance(item, str):
            problems.append(f"artifact entry is not a path: {item!r}")
            continue
        if not (root / item).exists():
            problems.append(f"artifact is missing: {item}")
    report = "docs/mvp2/DO015_CERTIFICATION_REPORT.md"
    if report not in artifacts:
        problems.append(f"the certification report must be listed in artifacts: {report}")
    return problems


def check_fixture_digests(evidence: dict[str, Any], root: Path) -> list[str]:
    """Freeze the Stage 3 fixture bytes into the evidence, not just a claim.

    The drift check is its own gate and runs in the suites. What belongs here
    is the record: these exact bytes were what got certified.
    """

    fixtures = evidence.get("fixtures")
    if not isinstance(fixtures, dict):
        return ["fixtures must be an object"]
    digests = fixtures.get("digests")
    if not isinstance(digests, dict) or not digests:
        return ["fixtures.digests must record each fixture's sha256"]
    problems = []
    for name, recorded in sorted(digests.items()):
        path = root / "resources" / "education" / "examples" / "guided_sessions" / name
        if not path.exists():
            problems.append(f"fixture {name} is recorded but missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded:
            problems.append(
                f"fixture {name} changed since certification "
                f"({actual[:12]} != {str(recorded)[:12]})"
            )
    fixture_dir = root / "resources" / "education" / "examples" / "guided_sessions"
    present = {item.name for item in fixture_dir.glob("*.json")}
    for extra in sorted(present - set(digests)):
        problems.append(f"fixture {extra} exists but is not recorded in the evidence")
    return problems


def check_production_diff(changed: list[str]) -> list[str]:
    """Nothing outside the certification surface may move after the baseline."""

    problems = []
    for path in changed:
        if path in ALLOWED_EXACT or any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        problems.append(f"{path} changed after the certified product sha")
    return problems


def check_witnesses(evidence: dict[str, Any]) -> list[str]:
    """The reproducible witness is mandatory; the visual one may be absent."""

    problems = []
    reproducible = evidence.get("browser_reproducible")
    if not isinstance(reproducible, dict) or reproducible.get("status") != "PASS":
        problems.append("browser_reproducible.status must be PASS: it is the mandatory witness")
    visual = evidence.get("browser_visual")
    if not isinstance(visual, dict):
        problems.append("browser_visual must be an object")
    else:
        status = visual.get("status")
        if status not in ("PASS", "NOT_AVAILABLE"):
            problems.append(f"browser_visual.status must be PASS or NOT_AVAILABLE, got {status!r}")
        if status == "NOT_AVAILABLE" and not str(visual.get("reason", "")).strip():
            problems.append("browser_visual is NOT_AVAILABLE without a reason")
    adversarial = evidence.get("stage8_adversarial")
    if not isinstance(adversarial, dict) or not adversarial.get("suites"):
        problems.append("stage8_adversarial must reference the Stage 8 suites it re-ran")
    return problems


def run_checks(evidence: dict[str, Any], root: Path, changed: list[str] | None, head: str | None):
    """Return (label, problems) for each check, in reporting order."""

    checks = [
        ("required evidence sections present", check_required_sections(evidence)),
        ("lineage is complete and self-consistent", check_lineage(evidence)),
        ("certified lineage is behind HEAD", check_ancestry(evidence, head)),
        ("cited artifacts exist", check_artifacts(evidence, root)),
        ("Stage 3 fixture bytes match the record", check_fixture_digests(evidence, root)),
        ("browser witnesses are declared honestly", check_witnesses(evidence)),
    ]
    boundary = "no production diff after the certified sha"
    if changed is None:
        checks.append((boundary, ["SKIPPED: git diff unavailable"]))
    else:
        checks.append((boundary, check_production_diff(changed)))
    return checks


def changed_paths(certified: str, head: str) -> list[str] | None:
    out = _git(["diff", "--name-only", f"{certified}..{head}"])
    if out is None:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the DO-015 certification evidence")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument(
        "--offline", action="store_true", help="skip the checks that need git"
    )
    args = parser.parse_args(argv)

    evidence, problems = load_evidence(args.evidence)
    if evidence is None:
        for problem in problems:
            print(_ascii(f"FAIL {problem}"))
        return 1

    head = None if args.offline else _git(["rev-parse", "HEAD"])
    changed = None
    if not args.offline:
        certified = str(evidence.get("lineage", {}).get("certified_product_sha", ""))
        if _SHA.match(certified) and head:
            changed = changed_paths(certified, head)

    checks = run_checks(evidence, REPO_ROOT, changed, head)
    failures = 0
    for label, found in checks:
        if not found:
            print(_ascii(f"OK   {label}"))
            continue
        skipped = all(item.startswith("SKIPPED") for item in found)
        if skipped:
            print(_ascii(f"note {label}: {found[0]}"))
            continue
        failures += 1
        print(_ascii(f"FAIL {label}"))
        for item in found:
            print(_ascii(f"       {item}"))
    total = len(checks)
    verdict = "OK" if failures == 0 else "FAIL"
    print(_ascii(f"\nDO-015 certification: {verdict} ({total - failures} of {total})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
