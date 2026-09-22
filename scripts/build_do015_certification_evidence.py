#!/usr/bin/env python3
"""Build the DO-015 Stage 9 integration evidence, deterministically.

The verifier answers "is this record consistent with the repository?". This
answers the other question a freeze has to answer: "where did the record come
from?". Without it a reviewer can confirm the frozen JSON is plausible but
cannot reproduce the assembly that selected and correlated its values, which is
not good enough for a tranche whose product is evidence.

Everything here is derived from the repository. Lineage is stated once below,
identity and digest facts are read out of the captured artifacts, and the
fixture digests are computed with the verifier's own rule. The only values that
cannot be derived are measurements -- test counts, coverage, the CI run -- and
those sit in MEASUREMENTS beside the command that produced each one.
Re-certifying means re-running those commands and updating that block.

    python scripts/build_do015_certification_evidence.py            # write
    python scripts/build_do015_certification_evidence.py --check    # compare

``--check`` builds the record in memory and compares it against the committed
file, so a stale freeze fails instead of sitting there looking authoritative.

Output is ASCII only, like the other verifiers here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "docs" / "mvp2" / "DO015_INTEGRATION_EVIDENCE.json"
ARTIFACTS = REPO_ROOT / "docs" / "mvp2" / "do015_artifacts"
FIXTURE_DIR = REPO_ROOT / "resources" / "education" / "examples" / "guided_sessions"

LINEAGE = {
    "repository": "HanzoRazer/Master-All-Strings",
    "stage7_merge_sha": "286d5aa439831ea44ff6e198a8518a45f076b513",
    "stage8_product_sha": "a29afb5e6972c5dfbf2266dee7a0ec47597c1d98",
    "stage8_merge_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
    "stage9_base_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
    "certified_product_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
    "stage9_branch": "cursor/do015-full-certification-cc02",
}

#: Measurements: the recorded results of the commands named beside them in the
#: record below. Nothing here can be derived from the tree, so re-running and
#: updating this block is what re-certifying means.
MEASUREMENTS: dict[str, Any] = {
    "targeted": {"passed": 491, "skipped": 0, "failed": 0},
    "full": {"passed": 2968, "skipped": 3, "failed": 2},
    "coverage_percent": 95.63,
    "node": {"passed": 505, "failed": 0},
    "mypy_source_files": 161,
    "stage8": {"node_tests": 12, "python_tests": 70},
}

#: The CI seal lives in a data file, not here. Sealing a run has to be a
#: metadata-only commit -- the record's own semantics say everything after the
#: named run is paperwork -- and editing this module would make it a code
#: change, which the verifier rejects, correctly.
CI_SEAL = ARTIFACTS / "ci_seal.json"


def _verifier() -> Any:
    """Share the verifier's digest rule rather than restating it."""

    spec = importlib.util.spec_from_file_location(
        "verify_do015_certification",
        REPO_ROOT / "scripts" / "verify_do015_certification.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ascii(text: str) -> str:
    return text.replace("—", "-").encode("ascii", "replace").decode("ascii")


def _artifact(name: str) -> dict[str, Any]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    """Assemble the record from the repository and the captured artifacts."""

    verify = _verifier()
    browser = _artifact("browser_smoke_summary.json")
    session = _artifact("certified_session.json")
    scenarios = _artifact("certification_scenarios.json")
    recorded = session["session"]

    return {
        "do": "DO-015",
        "stage": 9,
        "title": "Full MAS certification and evidence freeze",
        "built_by": "scripts/build_do015_certification_evidence.py",
        "verified_by": "scripts/verify_do015_certification.py",
        "source_of_truth": {
            "order": [
                "the suites and the capture script: executable, and the only "
                "things that can be wrong in a way that matters",
                "the captured artifacts under do015_artifacts/: regenerated and "
                "compared by those suites",
                "DO015_INTEGRATION_EVIDENCE.json: this record, assembled by the "
                "generator and checked by the verifier",
                "DO015_CERTIFICATION_REPORT.md: prose, and the weakest of the four",
            ],
            "rule": (
                "Where any two disagree the earlier one wins. The report is "
                "written for a reader, the JSON for a checker, the artifacts by "
                "the product, and the suites are the product."
            ),
            "reproduce": [
                "python scripts/build_do015_certification_evidence.py --check",
                "python scripts/verify_do015_certification.py",
                "pytest tests/mvp2/test_do015_certification_scenarios.py",
                "node web/mvp1/tests/do015_certification_capture.mjs",
            ],
        },
        "lineage": dict(
            LINEAGE,
            note=(
                "The Stage 8 product head is a29afb5, not the f671a73 an earlier "
                "draft of the Stage 9 order carried: two review-fix commits "
                "landed before the merge. certified_product_sha equals "
                "stage9_base_sha because Stage 9 changes no product file, and "
                "the verifier enforces that."
            ),
        ),
        "environment": {
            "python": "3.11.9",
            "node": "v24.11.0",
            "platform": "Windows-10-10.0.26100-SP0",
            "authoritative_ci": "GitHub Actions verify.yml, ubuntu-latest, Python 3.11",
        },
        "targeted_tests": dict(
            MEASUREMENTS["targeted"],
            command=(
                "pytest tests/education tests/mvp/test_guided_session_api_do015.py "
                "tests/mvp/test_do015_certification.py tests/mvp2"
            ),
            covers=[
                "Stage 1 contract",
                "Stage 2 service",
                "Stage 3 fixtures",
                "Stage 4 API",
                "Stage 8 adversarial",
                "Stage 9 certification",
            ],
        ),
        "full_tests": dict(
            MEASUREMENTS["full"],
            command="pytest --cov --cov-report=term-missing",
            failed_are="the two known Windows-only environment artifacts recorded below",
        ),
        "node": dict(
            MEASUREMENTS["node"],
            command="node --test tests/*.test.js (web/mvp1)",
            version="v24.11.0",
            platform="Windows",
            linux_ci_coverage="NOT_PRESENT",
            note=(
                "verify.yml has four Python steps and no Node step. Recorded, "
                "not repaired: the workflow is a deferred-hygiene path frozen "
                "by DO-012A."
            ),
        ),
        "python": {"version": "3.11.9", "authoritative_platform": "linux (GitHub Actions)"},
        "coverage": {
            "total_percent": MEASUREMENTS["coverage_percent"],
            "floor_percent": 95.0,
            "source": "master_all_strings",
            "result": "PASS",
        },
        "ruff": {"command": "ruff check src tests", "result": "PASS"},
        "mypy": {
            "command": "mypy",
            "result": "PASS",
            "source_files": MEASUREMENTS["mypy_source_files"],
            "mode": "strict",
        },
        "fixtures": {
            "drift_check": "PASS",
            "command": "python scripts/build_guided_session_fixtures.py --check",
            "digest_method": "sha256 of the file with CRLF normalised to LF",
            "note": (
                "A digest over raw working-copy bytes is a property of the "
                "checkout rather than of the content, and the first CI run of "
                "this certification failed for exactly that reason."
            ),
            "digests": {
                path.name: verify.content_digest(path)
                for path in sorted(FIXTURE_DIR.glob("*.json"))
            },
        },
        "in_flight": {
            "command": "python scripts/check_in_flight.py",
            "result": "PASS",
            "branches_in_flight": 1,
        },
        "browser_reproducible": {
            "status": "PASS",
            "witness": browser["witness"],
            "runner": "node web/mvp1/tests/do015_certification_capture.mjs",
            "asserted_by": "web/mvp1/tests/do015_certification.test.js",
            "proves": browser["proves"],
            "does_not_prove": browser["does_not_prove"],
            "session_id": browser["session_id"],
            "final_status": browser["final_status"],
            "attempt_ids": browser["attempt_ids"],
            "canonical_revision_id": browser["canonical_revision_id"],
            "console_errors": browser["console_errors"],
            "summary_artifact": "docs/mvp2/do015_artifacts/browser_smoke_summary.json",
        },
        "browser_visual": {
            "status": "NOT_AVAILABLE",
            "reason": "connected real-browser control unavailable in certification environment",
            "checked": "list_connected_browsers returned no connected Chrome extension",
            "consequence": "no screenshots were captured; rendering is not certified here",
            "mitigation": (
                "the reproducible witness certifies orchestration and the UI "
                "event path; DOM rendering remains uncertified and is a known "
                "limitation"
            ),
        },
        "identity_chain": {
            "result": "PASS",
            "browser_witness": browser["identity_chain"],
            "authoritative_witness": {
                "session_id": recorded["session_id"],
                "attempt_ids": [a["attempt_id"] for a in recorded["attempts"]],
                "performance_session_ids": [
                    a["performance_session_id"] for a in recorded["attempts"]
                ],
                "evaluation_digests": [a["evaluation_digest"] for a in recorded["attempts"]],
                "guidance_digests": [a["guidance_digest"] for a in recorded["attempts"]],
                "canonical_revision_ids": sorted(
                    {a["canonical_revision_id"] for a in recorded["attempts"]}
                ),
            },
        },
        "digest_invariants": {
            "session_digest": recorded["session_digest"],
            "session_digest_recomputed": session["session_digest_recomputed"],
            "session_digest_matches": (
                recorded["session_digest"] == session["session_digest_recomputed"]
            ),
            "serialized_session_sha256": session["serialized_bytes_sha256"],
            "attempt_immutability": browser["attempt_0_immutable"],
            "note": (
                "The session digest is the contract's own computation, taken "
                "from the real Stage 4 API. The browser mirror computes no "
                "digests and claims none."
            ),
        },
        "lesson_transition": {
            "result": "PASS",
            "authoritative_witness": session["lesson_transition"],
            "browser_witness": {
                "proves": "the page asks for a transition and stands the old session down",
                "does_not_prove": (
                    "what a transition is: that is the Stage 2 service's answer, "
                    "and the browser witness reaches it through a JavaScript mirror"
                ),
                "previous_session_status": browser["lesson_transition"]["previous_session_status"],
                "new_lesson_session": browser["lesson_transition"]["new_lesson_session"],
                "history_rendered_on_new_lesson": browser["lesson_transition"]["history_rendered"],
            },
        },
        "revision_fail_closed": dict({"result": "PASS"}, **browser["revision_fail_closed"]),
        "stage8_adversarial": dict(
            MEASUREMENTS["stage8"],
            result="PASS",
            suites=[
                "web/mvp1/tests/guided_authority_adversarial.test.js",
                "tests/education/test_guided_session_adversarial_do015.py",
                "tests/mvp2/test_do015_crosswalk_citations.py",
            ],
            note=(
                "Re-run, not reimplemented. The Stage 8 crosswalk in "
                "DO015_TRANCHE_PLAN.md maps each authority cell to a test at path:line."
            ),
        ),
        "controlled_scenarios": {
            "scenario": scenarios["scenario"],
            "artifact": "docs/mvp2/do015_artifacts/certification_scenarios.json",
            "regenerated_by": "tests/mvp2/test_do015_certification_scenarios.py",
            "legs": {
                name: {
                    "lesson": leg["lesson"],
                    "pattern": leg["pattern"],
                    "action": leg["response"]["evaluation"]["primary_next_action"]["action_type"],
                    "findings": len(leg["response"]["evaluation"]["findings"]),
                }
                for name, leg in scenarios["legs"].items()
            },
            "unsupported_actions": {
                "browser_natural_witness": "NOT_AVAILABLE",
                "reason": "no bundled lesson produces VIEW_ONE_STRING or ENABLE_ZONE_VIEW",
                "authoritative_test_witness": "PASS",
                "covered_by": [
                    "web/mvp1/tests/guided_action_executor.test.js:252",
                    "web/mvp1/tests/guided_action_executor.test.js:269",
                ],
            },
        },
        "linux_ci": dict(
            json.loads(CI_SEAL.read_text(encoding="utf-8")),
            workflow=".github/workflows/verify.yml",
            platform="ubuntu-latest, Python 3.11",
            semantics=(
                "The run named here is the green run for the last commit that "
                "changed certification content, not for the pull-request head. "
                "Naming the head needs a commit, which moves the head: that "
                "never converges. The verifier proves certified_content_sha is "
                "behind HEAD and that every commit after it touches only "
                "evidence and register metadata. The head's own run is a live "
                "review gate, not something this static record chases."
            ),
            note="Authoritative for the Windows-only failures above; runs no Node step.",
        ),
        "artifacts": [
            "docs/mvp2/DO015_CERTIFICATION_REPORT.md",
            "docs/mvp2/do015_artifacts/browser_smoke_summary.json",
            "docs/mvp2/do015_artifacts/certification_scenarios.json",
            "docs/mvp2/do015_artifacts/certified_session.json",
            "docs/mvp2/do015_artifacts/ci_seal.json",
        ],
        "known_environment_exceptions": [
            {
                "test": (
                    "tests/integrations/test_do008_end_to_end.py::"
                    "test_checked_in_bundle_correlates_all_authoritative_semantic_events"
                ),
                "platform": "Windows",
                "cause": "sha256 over a checked-in bundle artifact in a CRLF working copy",
                "reproduced_on_base": True,
                "authoritative_result": "PASS on Linux CI",
                "repaired": False,
                "why_not": "Stage 9 does not authorize Windows hygiene",
            },
            {
                "test": "tests/mvp/test_mvp1_publication_utils.py::test_mvp1_lineage_script_passes",
                "platform": "Windows",
                "cause": "the lineage script prints U+2192 through a cp1252 console",
                "reproduced_on_base": True,
                "authoritative_result": "PASS on Linux CI",
                "repaired": False,
                "why_not": "Stage 9 does not authorize Windows hygiene",
            },
        ],
        "known_limitations": [
            "DOM rendering is not certified: no connected browser was available, "
            "so there is no visual witness and no screenshots.",
            "Node has no Linux CI coverage; the Node suite is certified on Windows only.",
            "The reproducible browser witness mirrors the Stage 2 lifecycle in "
            "JavaScript. Lifecycle truth, transition truth and the session digest "
            "are certified separately through the real Stage 4 API.",
            "VIEW_ONE_STRING and ENABLE_ZONE_VIEW have no natural browser witness "
            "and remain covered by unit and Stage 8 tests.",
        ],
        "deferred_work": [
            "Stage 8 crosswalk verifier checks citation shape, not semantic target meaning.",
            "Line-number citations are fragile; symbol-based path::name references "
            "are preferred future hardening.",
            "Adversarial tests import private helpers from another test module; "
            "future test-maintenance coupling.",
            "Neither check_in_flight.py nor verify_do015_certification.py is a CI "
            "gate: verify.yml is a deferred-hygiene path frozen by DO-012A and "
            "unfreezing it needs an owner ruling.",
        ],
        "not_claimed": [
            "published",
            "released",
            "MVP 2 complete",
            "tagged",
            "production release",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or check the DO-015 evidence")
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed record with a freshly built one",
    )
    args = parser.parse_args(argv)

    built = json.dumps(build(), indent=2) + "\n"
    if not args.check:
        EVIDENCE.write_text(built, encoding="utf-8")
        print(_ascii(f"wrote {EVIDENCE.relative_to(REPO_ROOT)}"))
        return 0

    if not EVIDENCE.exists():
        print(_ascii("FAIL the evidence has not been written yet"))
        return 1
    committed = EVIDENCE.read_text(encoding="utf-8")
    if committed == built:
        print(_ascii("DO-015 evidence: OK (the committed record is what this builds)"))
        return 0
    print(_ascii("FAIL the committed evidence is not what this generator builds"))
    committed_obj = json.loads(committed)
    built_obj = json.loads(built)
    for key in sorted(set(committed_obj) | set(built_obj)):
        if committed_obj.get(key) != built_obj.get(key):
            print(_ascii(f"       section differs: {key}"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
