"""What receiving a lesson must not do.

A delivery arriving is a lesson sitting in an inbox. It is not the lesson
starting: nothing is resolved, nothing plays, nobody is evaluated, and no
guided session begins. That boundary is easy to state and easy to erode --
one convenient call to "just prepare it" inside receive and arrival becomes
activation, with a student's practice history recording lessons they never
opened.

Two kinds of proof here, because each catches what the other misses. The spies
prove nothing was called on the paths a delivery actually travels. The import
check proves the delivery modules cannot reach those subsystems at all, which
still holds for paths no test thought to exercise.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.education import evaluation as evaluation_module
from master_all_strings.education import guided_session_service as guided_module
from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import (
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)
from master_all_strings.mvp import application as application_module
from master_all_strings.mvp.lesson_delivery_api import LocalLessonDeliveryApi

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
SOURCE = REPO_ROOT / "src" / "master_all_strings"

DELIVERY_MODULES = (
    SOURCE / "education" / "assignment_delivery.py",
    SOURCE / "education" / "assignment_delivery_serialization.py",
    SOURCE / "education" / "assignment_delivery_repository.py",
    SOURCE / "education" / "assignment_delivery_service.py",
    SOURCE / "mvp" / "lesson_delivery_api.py",
)

#: Subsystems a delivery has no business touching on its way into an inbox.
FORBIDDEN_IMPORTS = (
    "master_all_strings.performance",
    "master_all_strings.core.transport",
    "master_all_strings.education.evaluation",
    "master_all_strings.education.guided_session",
    "master_all_strings.education.guided_session_service",
    "master_all_strings.mvp.application",
    "master_all_strings.mvp.orchestrator",
    "master_all_strings.mvp.playback",
)


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


@pytest.fixture
def tripwires(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the activation entry points with things that fail if called."""

    called: list[str] = []

    def trip(name: str) -> Any:
        def _tripped(*_args: object, **_kwargs: object) -> Any:
            called.append(name)
            raise AssertionError(f"receiving a delivery called {name}")

        return _tripped

    monkeypatch.setattr(
        application_module.MvpApplication, "run_assignment_json", trip("run_assignment_json")
    )
    monkeypatch.setattr(
        evaluation_module, "evaluate_practice_attempt", trip("evaluate_practice_attempt")
    )
    monkeypatch.setattr(
        guided_module, "create_from_first_evaluated_attempt", trip("guided session create")
    )
    return called


def test_receiving_activates_nothing(
    assignment: LessonAssignmentV1, tripwires: list[str]
) -> None:
    service = LessonDeliveryService()
    envelope = envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    service.receive(envelope)
    service.get("delivery-001")
    service.list()
    service.list(recipient_ref="student-bo")
    assert tripwires == []


def test_the_api_path_activates_nothing(
    assignment: LessonAssignmentV1, tripwires: list[str]
) -> None:
    api = LocalLessonDeliveryApi()
    payload = delivery_to_dict(
        envelope_for(
            assignment,
            delivery_id="delivery-001",
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )
    assert api.handle_http("POST", "/api/education/lesson-deliveries", payload)[0] == 201
    assert api.handle_http("GET", "/api/education/lesson-deliveries", {})[0] == 200
    assert api.handle_http("GET", "/api/education/lesson-deliveries/delivery-001", {})[0] == 200
    assert tripwires == []


@pytest.mark.parametrize("module", DELIVERY_MODULES, ids=lambda p: p.name)
def test_delivery_modules_cannot_reach_the_engines(module: Path) -> None:
    # Stronger than a spy: a module that never imports Transport cannot start
    # playback down some path no test happened to drive.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    offending = sorted(
        name
        for name in imported
        for forbidden in FORBIDDEN_IMPORTS
        if name == forbidden or name.startswith(forbidden + ".")
    )
    assert offending == [], f"{module.name} imports {offending}"


def test_the_lesson_is_unchanged_by_the_round_trip(assignment: LessonAssignmentV1) -> None:
    # Behaviour is the thing a student ultimately receives; artifact equality
    # is the stricter statement, and both are asserted rather than one.
    before = compute_lesson_behavior_digest(assignment)
    service = LessonDeliveryService()
    service.receive(
        envelope_for(
            assignment,
            delivery_id="delivery-001",
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )
    received = service.get("delivery-001").assignment
    assert compute_lesson_behavior_digest(received) == before
    assert serialize_lesson_assignment(received) == serialize_lesson_assignment(assignment)


def test_the_service_mints_no_identities(assignment: LessonAssignmentV1) -> None:
    # Delivery IDs are caller supplied. A service that minted them would make
    # a retry indistinguishable from a new delivery.
    for module in DELIVERY_MODULES:
        source = module.read_text(encoding="utf-8")
        assert "uuid" not in source.lower(), f"{module.name} mints identities"
