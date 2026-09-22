"""The controlled CONTINUE scenario, and proof it is the real policy's answer.

CONTINUE is the recommendation the bundled lessons never reach by fake MIDI:
the fake emitter plays 60/62/64 while every demo expects something else, so a
fake performance always produces findings, and CONTINUE is what the policy
returns when nothing is actionable.

So the performance evidence is synthetic -- each expected note played exactly,
at the seconds the projection itself states -- and everything downstream is
real. The evaluator is the product evaluator and the recommendation is its
answer, not a hand-authored action. This regenerates the frozen artifact and
fails if either the artifact or the policy moves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from master_all_strings.mvp.education_api import LocalPracticeEvaluationApi

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = REPO_ROOT / "docs" / "mvp2" / "do015_artifacts" / "certification_scenarios.json"
LESSON = "ascending_scale"
SECOND_LESSON = "descending_scale"

#: Each leg of the certified flow, and how the learner is imagined to play it.
#: The patterns were chosen so the policy reaches three different actions and
#: the flow exercises both runtime seams -- rate and loop -- before closing.
LEGS: tuple[tuple[str, str, str, str], ...] = (
    ("attempt_0_slow_down", LESSON, "alternating", "slow_down"),
    ("attempt_1_isolate", LESSON, "uniform", "isolate_passage"),
    ("attempt_2_continue", LESSON, "clean", "continue"),
    # A fourth lesson's own evidence, so the lesson-switch witness transitions
    # a real session rather than one wearing another lesson's identity.
    ("lesson_switch_witness", SECOND_LESSON, "uniform", "isolate_passage"),
)


def _offsets(pattern: str, count: int) -> list[float]:
    """Seconds to add to each note's onset, per named pattern.

    Scattered lateness and sustained lateness are different mistakes and the
    policy answers them differently: a contiguous cluster becomes
    ISOLATE_PASSAGE, a spread of late entries becomes SLOW_DOWN.
    """

    if pattern == "clean":
        return [0.0] * count
    if pattern == "uniform":
        return [0.14] * count
    if pattern == "alternating":
        return [0.25 if index % 2 == 0 else 0.0 for index in range(count)]
    raise AssertionError(f"unknown performance pattern {pattern!r}")


def _load(path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def build_leg(name: str, lesson: str, pattern: str) -> dict[str, Any]:
    """One performance of the bundled lesson, through the real evaluator."""

    projection = _load(f"web/mvp1/projections/{lesson}.json")["projection"]
    playback = _load(f"web/mvp1/playback/{lesson}.json")
    revision = _load(f"web/mvp1/projections/{lesson}/canonical_revision.json")
    notes = projection["notes"]
    offsets = _offsets(pattern, len(notes))

    observed = []
    for index, (note, offset_seconds) in enumerate(zip(notes, offsets, strict=True), start=1):
        on_ns = int((note["onset_seconds"] + offset_seconds) * 1e9)
        off_ns = int((note["release_seconds"] + offset_seconds) * 1e9)
        observed.append(
            {
                "observed_event_id": f"obs-{index}",
                "capture_id": "capture-do015-certification",
                "note_on_event_id": f"on-{index}",
                "note_off_event_id": f"off-{index}",
                "midi_note": note["midi_note"],
                "velocity": 80,
                "channel": 0,
                "source_device": "do015-certification-clean-performance",
                "note_on_time_ns": on_ns,
                "note_off_time_ns": off_ns,
                "duration_ns": off_ns - on_ns,
                "status": "complete",
                "repetition_index": 0,
                "practice_onset_seconds": note["onset_seconds"] + offset_seconds,
            }
        )

    request = {
        "assignment_id": playback["assignment_id"],
        "content_id": playback["content_id"],
        "performance_session_id": f"performance-do015-certification-{name}",
        "current_rate": 1.0,
        "timeline": projection.get("timeline", {}),
        "tempo_changes": projection.get("tempo_changes", []),
        "expected_notes": [
            {
                "event_id": note["event_id"],
                "midi_note": note["midi_note"],
                "onset_tick": note["onset_tick"],
                "duration_ticks": note["duration_ticks"],
                "velocity": 80,
            }
            for note in notes
        ],
        "observed_events": observed,
        "repetition_count": 1,
        "canonical_revision_id": revision["revision_id"],
    }
    response = LocalPracticeEvaluationApi().handle("evaluate", request)
    return {
        "leg": name,
        "lesson": lesson,
        "pattern": pattern,
        "offsets_seconds": offsets,
        "request": request,
        "response": response,
    }


def build_scenario() -> dict[str, Any]:
    """Every leg of the certified flow, each answered by the real evaluator."""

    return {
        "scenario": "controlled lifecycle certification scenario",
        "note": (
            "Synthetic performance evidence against a bundled lesson: each "
            "expected note played, shifted by a fixed offset. Every "
            "recommendation below is the real evaluator's answer to that "
            "evidence. None is hand-authored, and none is a natural "
            "fake-MIDI outcome -- the fake emitter plays notes this lesson "
            "does not contain, so it can never reach CONTINUE."
        ),
        "lessons": [LESSON, SECOND_LESSON],
        "legs": {
            name: build_leg(name, lesson, pattern) for name, lesson, pattern, _ in LEGS
        },
    }


def test_a_clean_performance_of_a_bundled_lesson_yields_continue() -> None:
    leg = build_scenario()["legs"]["attempt_2_continue"]
    evaluation = leg["response"]["evaluation"]
    assert evaluation["primary_next_action"]["action_type"] == "continue"
    assert evaluation["findings"] == []
    assert evaluation["summary"]["actionable_finding_count"] == 0
    # The guidance the browser will act on is the evaluator's own.
    assert leg["response"]["guidance"]["next_action"]["action_type"] == "continue"


def test_each_leg_is_the_action_the_policy_chose() -> None:
    # The certified flow covers both runtime seams before it closes: a rate
    # change, then a loop, then closure. If the policy ever answers these
    # performances differently, the certification record is stale and this is
    # where that shows.
    legs = build_scenario()["legs"]
    for name, _lesson, _pattern, expected in LEGS:
        evaluation = legs[name]["response"]["evaluation"]
        assert evaluation["primary_next_action"]["action_type"] == expected, name
        assert legs[name]["response"]["guidance"]["next_action"]["action_type"] == expected


def test_every_leg_carries_its_own_performance_identity() -> None:
    legs = build_scenario()["legs"]
    ids = {leg["request"]["performance_session_id"] for leg in legs.values()}
    assert len(ids) == len(legs), "attempts must not share a performance identity"
    digests = {leg["response"]["evaluation"]["evaluation_digest"] for leg in legs.values()}
    assert len(digests) == len(legs), "distinct performances must evaluate distinctly"


def test_the_scenario_is_deterministic() -> None:
    first = json.dumps(build_scenario(), sort_keys=True)
    second = json.dumps(build_scenario(), sort_keys=True)
    assert first == second


def test_the_frozen_artifact_still_matches_the_policy() -> None:
    assert ARTIFACT.exists(), "the CONTINUE scenario artifact has not been frozen"
    frozen = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert frozen == build_scenario(), (
        "the committed CONTINUE evidence no longer matches what the evaluator "
        "produces; regenerate it or explain the policy change"
    )


def test_continue_carries_no_mastery_language() -> None:
    text = json.dumps(build_scenario()).lower()
    for forbidden in ("mastered", "perfect", "course complete", "lesson passed"):
        assert forbidden not in text
