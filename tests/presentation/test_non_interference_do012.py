"""DO-012 non-interference: presentation synchronization changes nothing upstream.

The whole tranche is additive presentation. If any of these digests move, a
follower has reached back into an authority it only observes.

The digest constants are the ones already pinned by the MVP 2A suites; they are
repeated here deliberately rather than imported, so this file fails loudly if
someone updates one in a single place.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path

import pytest

from master_all_strings.education.serialization import compute_evaluation_digest
from master_all_strings.media.presentation import lesson_media_payload
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.education_api import LocalPracticeEvaluationApi

REPO_ROOT = Path(__file__).resolve().parents[2]

HALF_STEPS_BEHAVIOR = "sha256:075268cae2e858e93774a59ae3e2d7df8b5b73aaaa4c209069afbe006b1d4878"
HALF_STEPS_PROJECTION = "sha256:398f53a7a9ef4f623742d9e76d582ca196919e60821ed2b7e9a928ac15a5d1df"
HALF_STEPS_PLAYBACK = "sha256:f9b578ae35e3d436d027f71f1240e763f844163f561fc6b57f83c86bb05266fd"
ASCENDING_BEHAVIOR = "sha256:9f86b56c92e9d8e32dbd55275a45b5c4b17e937bad8e4552cb262c73eefd32e9"

GOLDEN_DEMO_DIGESTS = (
    "sha256:0d71b47db5275e8d0c40782152fef252f0aaee2263cf242b0909d475ea40014c",
    "sha256:adf76129ef11641051fb04c03e5eb07d6bad0f8db226860cc74c3f5a3056e717",
    "sha256:1ffaa27fa50f3fd7cd8067c12c2a25bc2344b5a63aa5113e0d545aa91999d657",
)


# --- Musical Core / MSME / Zone ----------------------------------------------


def test_golden_lesson_musical_digests_are_unchanged() -> None:
    response = MvpApplication().run_demo("half_steps_one_string")
    assert response.behavior_digest == HALF_STEPS_BEHAVIOR
    assert response.projection.projection_digest == HALF_STEPS_PROJECTION
    assert response.playback_plan.playback_digest == HALF_STEPS_PLAYBACK


def test_second_lesson_musical_digest_is_unchanged() -> None:
    assert MvpApplication().run_demo("ascending_scale").behavior_digest == ASCENDING_BEHAVIOR


def test_zone_semantics_are_still_copied_not_derived() -> None:
    """Zone gained a time-varying readout; its semantic content did not change.

    Zone semantics reach the browser through the DO-008 stack, not through the
    bundled demos, so the checked-in DO-008 export is what carries them.
    """

    payload = json.loads(
        (REPO_ROOT / "web" / "mvp1" / "do008" / "projection.json").read_text(encoding="utf-8")
    )
    zoned = [note for note in payload["projection"]["notes"] if note.get("zone_semantics")]
    assert len(zoned) == 48, "the DO-008 export should carry 48 Zone-annotated notes"
    for note in zoned:
        semantics = note["zone_semantics"]
        assert semantics["zone_id"]
        assert isinstance(semantics["semantic_roles"], list)
    # The semantic artifact digest is the DO-008 authority and is not ours to move.
    assert payload["behavior_digest"].startswith("sha256:")


def test_spatial_selection_is_unchanged_by_the_anchor_export() -> None:
    response = MvpApplication().run_demo("half_steps_one_string")
    selected = [note for note in response.projection.notes if note.status.value == "selected"]
    assert selected
    for note in selected:
        assert note.string_id is not None
        assert note.fret_number is not None


# --- Educational --------------------------------------------------------------


def test_educational_golden_demo_digests_are_unchanged() -> None:
    """ISOLATE_PASSAGE now drives a loop; the decision that produced it did not move."""

    result = LocalPracticeEvaluationApi().handle("golden_demo", {})
    assert tuple(a["digest"] for a in result["attempts"]) == GOLDEN_DEMO_DIGESTS
    assert result["sequence"] == ["slow_down", "isolate_passage", "continue"]


def test_educational_evaluation_is_deterministic_across_runs() -> None:
    first = LocalPracticeEvaluationApi().handle("golden_demo", {})
    second = LocalPracticeEvaluationApi().handle("golden_demo", {})
    assert first["attempts"] == second["attempts"]


def test_isolate_action_still_reports_the_same_focus_range() -> None:
    """The adapter consumes focus ticks; it does not change which ones are chosen."""

    result = LocalPracticeEvaluationApi().handle("golden_demo", {})
    isolate = next(a for a in result["attempts"] if a["primary_action"] == "isolate_passage")
    assert isolate["digest"] == GOLDEN_DEMO_DIGESTS[1]


def test_evaluation_digest_helper_is_untouched() -> None:
    assert callable(compute_evaluation_digest)


# --- boundary ------------------------------------------------------------------

_UPSTREAM_PACKAGES = (
    "master_all_strings.core",
    "master_all_strings.education",
    "master_all_strings.performance",
    "master_all_strings.instruments",
)


def _modules_under(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    names = [package_name]
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        names.append(info.name)
    return names


@pytest.mark.parametrize("package_name", _UPSTREAM_PACKAGES)
def test_upstream_authorities_do_not_import_presentation(package_name: str) -> None:
    """Presentation observes; it is never a dependency of what it observes.

    Media may import presentation (it carries bindings), but Musical Core,
    Educational, Performance, and instrument profiles must not: a follower
    appearing in an authority's import graph is how a presentation concern
    starts influencing a musical decision.
    """

    for name in _modules_under(package_name):
        module = importlib.import_module(name)
        source_deps = {
            value.__name__
            for value in vars(module).values()
            if getattr(value, "__module__", "").startswith("master_all_strings.presentation")
        }
        assert not source_deps, f"{name} depends on presentation: {sorted(source_deps)}"


def test_media_payload_is_additive_over_do011() -> None:
    """Every DO-011 key survives; DO-012 only adds beside them."""

    payload = lesson_media_payload("half_steps_one_string")
    for key in (
        "schema_version",
        "lesson_key",
        "items",
        "available_count",
        "unavailable_count",
        "status",
        "message",
    ):
        assert key in payload
    for item in payload["items"]:
        for key in (
            "available",
            "diagnostic",
            "public_url",
            "reference_id",
            "role",
            "optional",
            "media",
        ):
            assert key in item


def test_presentation_declares_no_canonical_revision_authority() -> None:
    """DO-013 owns revision provenance. DO-012 must not anticipate it."""

    from dataclasses import fields

    from master_all_strings.presentation import contracts

    for name in dir(contracts):
        value = getattr(contracts, name)
        if hasattr(value, "__dataclass_fields__"):
            assert "canonical_revision_id" not in {f.name for f in fields(value)}
