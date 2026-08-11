"""Bundled MVP demonstration library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.errors import LessonLoadError
from master_all_strings.mvp.models import MvpLessonSummaryV1

__all__ = [
    "DemoManifestEntryV1",
    "default_demo_root",
    "load_demo_assignment",
    "load_demo_manifest",
    "resolve_demo_midi_path",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DemoManifestEntryV1:
    demo_id: str
    title: str
    description: str
    lesson_path: str
    instrument_profile_id: str
    demonstrates: tuple[str, ...]
    expected_behavior_digest: str | None = None
    expected_projection_digest: str | None = None
    midi_path: str | None = None
    known_limitations: tuple[str, ...] = ()

    def to_summary(self) -> MvpLessonSummaryV1:
        return MvpLessonSummaryV1(
            demo_id=self.demo_id,
            title=self.title,
            description=self.description,
            instrument_profile_id=self.instrument_profile_id,
            demonstrates=self.demonstrates,
            known_limitations=self.known_limitations,
        )


def default_demo_root() -> Path:
    return _REPO_ROOT / "resources" / "mvp1" / "demo_lessons"


def load_demo_manifest(root: Path | None = None) -> tuple[DemoManifestEntryV1, ...]:
    base = root or default_demo_root()
    path = base / "manifest.json"
    if not path.is_file():
        raise LessonLoadError(f"Demo manifest missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    demos = raw.get("demos")
    if not isinstance(demos, list) or not demos:
        raise LessonLoadError("Demo manifest contains no demos")
    entries: list[DemoManifestEntryV1] = []
    for item in demos:
        entries.append(
            DemoManifestEntryV1(
                demo_id=item["demo_id"],
                title=item["title"],
                description=item["description"],
                lesson_path=item["lesson_path"],
                instrument_profile_id=item["instrument_profile_id"],
                demonstrates=tuple(item.get("demonstrates") or ()),
                expected_behavior_digest=item.get("expected_behavior_digest"),
                expected_projection_digest=item.get("expected_projection_digest"),
                midi_path=item.get("midi_path"),
                known_limitations=tuple(item.get("known_limitations") or ()),
            )
        )
    return tuple(entries)


def load_demo_assignment(demo_id: str, *, root: Path | None = None) -> LessonAssignmentV1:
    base = root or default_demo_root()
    for entry in load_demo_manifest(base):
        if entry.demo_id == demo_id:
            lesson_path = (base / entry.lesson_path).resolve()
            if not lesson_path.is_file():
                raise LessonLoadError(f"Demo lesson missing: {entry.lesson_path}")
            return deserialize_lesson_assignment(lesson_path.read_text(encoding="utf-8"))
    raise LessonLoadError(f"Unknown demo lesson: {demo_id}")


def resolve_demo_midi_path(demo_id: str, *, root: Path | None = None) -> Path | None:
    base = root or default_demo_root()
    for entry in load_demo_manifest(base):
        if entry.demo_id == demo_id and entry.midi_path:
            path = (base / entry.midi_path).resolve()
            return path if path.is_file() else None
    return None
