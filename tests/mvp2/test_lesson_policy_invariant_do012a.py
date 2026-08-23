"""Lesson repetition policy is lesson authority, not presentation's to move.

DO-012's ">= 3 repetitions" proof runs on ``ascending_scale`` because
``half_steps_one_string`` declares ``target_repetitions = 2`` in its own practice
policy and correctly stops after two passes. The tempting shortcut was to raise
that number so the golden lesson could demonstrate three.

That shortcut would have been invisible in the evidence: the repetition proof
would have passed, on the golden lesson, with a screenshot to match. What it
would actually have proved is that presentation can edit lesson content when the
content is inconvenient. These tests make the invariant mechanical rather than a
sentence in a report nobody re-reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.mvp.demo_library import load_demo_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRACTICE = REPO_ROOT / "web" / "mvp1" / "practice"

GOLDEN_LESSON = "half_steps_one_string"

#: As authored. DO-012 and DO-012A must both leave this alone.
GOLDEN_TARGET_REPETITIONS = 2

#: The lesson the >= 3 proof actually uses, and why it can.
UNCAPPED_LESSON = "ascending_scale"


def _policy(demo_id: str) -> dict:
    payload = json.loads((PRACTICE / f"{demo_id}.json").read_text(encoding="utf-8"))
    policy = payload["policy"]["loop"]
    assert isinstance(policy, dict)
    return policy


def test_the_golden_lesson_still_declares_its_authored_repetition_target() -> None:
    assert _policy(GOLDEN_LESSON)["target_repetitions"] == GOLDEN_TARGET_REPETITIONS


def test_the_golden_lesson_cap_is_below_the_three_repetition_requirement() -> None:
    """The conflict is real, not a misreading -- which is why a second lesson is used."""

    assert _policy(GOLDEN_LESSON)["target_repetitions"] < 3


def test_the_lesson_used_for_the_proof_declares_no_cap() -> None:
    """``ascending_scale`` can show >= 3 because its own policy permits it."""

    assert _policy(UNCAPPED_LESSON)["target_repetitions"] is None


def test_no_bundled_lesson_had_its_cap_raised_to_satisfy_the_proof() -> None:
    """Every capped lesson is capped at what it was authored with.

    A cap raised anywhere would let some lesson demonstrate three repetitions
    that its author did not intend, which is the same violation as editing the
    golden lesson, only harder to notice.
    """

    capped = {
        entry.demo_id: _policy(entry.demo_id)["target_repetitions"]
        for entry in load_demo_manifest()
        if _policy(entry.demo_id)["target_repetitions"] is not None
    }
    assert capped == {GOLDEN_LESSON: GOLDEN_TARGET_REPETITIONS}


@pytest.mark.parametrize(
    "demo_id", [entry.demo_id for entry in load_demo_manifest()]
)
def test_every_lesson_declares_an_explicit_repetition_target(demo_id: str) -> None:
    """Present-and-null is a decision; absent is an accident."""

    assert "target_repetitions" in _policy(demo_id)


def test_the_evidence_records_why_the_proof_moved_lessons() -> None:
    """The reason has to survive in the evidence, not only in a commit message."""

    evidence = json.loads(
        (REPO_ROOT / "docs" / "mvp2" / "DO012_INTEGRATION_EVIDENCE.json").read_text(
            encoding="utf-8"
        )
    )
    proof = evidence["browser_smoke"]["repetition_proof"]
    assert proof["lesson"] == UNCAPPED_LESSON
    assert proof["meets_three_repetition_criterion"] is True
    assert GOLDEN_LESSON in proof["reason_not_golden_lesson"]
