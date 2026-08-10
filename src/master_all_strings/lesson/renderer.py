"""Zero-authority scrolling-fretboard renderer consumer.

Reads projection data only. May surface display-only assignment metadata
(title / objective / teacher note). Must never read routing or compute frets.
"""

from __future__ import annotations

from dataclasses import dataclass

from .projection import ScrollingFretboardProjectionV1, projection_to_renderer_view

__all__ = ["RendererViewV1", "render_scrolling_fretboard_view"]


@dataclass(frozen=True)
class RendererViewV1:
    """Pixels-facing view model with no musical authority."""

    title: str
    objective: str | None
    teacher_note: str | None
    notes: tuple[dict[str, object], ...]
    # Intentionally absent: routing fields.


def render_scrolling_fretboard_view(
    projection: ScrollingFretboardProjectionV1,
) -> RendererViewV1:
    """Adapt a semantic projection into a renderer view. Chooses nothing."""

    raw = projection_to_renderer_view(projection)
    notes_raw = raw["notes"]
    if not isinstance(notes_raw, list):
        raise TypeError("projection notes must be a list")
    note_dicts = tuple(dict(item) for item in notes_raw if isinstance(item, dict))
    objective = raw["objective"]
    teacher_note = raw["teacher_note"]
    return RendererViewV1(
        title=str(raw["title"]),
        objective=None if objective is None else str(objective),
        teacher_note=None if teacher_note is None else str(teacher_note),
        notes=note_dicts,
    )
