"""Master All Strings MVP application / presentation adapter."""

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import MvpError, format_mvp_error
from master_all_strings.mvp.models import MvpProjectionResponseV1
from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator
from master_all_strings.mvp.projection import (
    FretboardScrollProjectionV1,
    build_fretboard_scroll_projection,
    serialize_fretboard_projection,
)

__all__ = [
    "FretboardScrollProjectionV1",
    "MvpApplication",
    "MvpError",
    "MvpLessonOrchestrator",
    "MvpProjectionResponseV1",
    "build_fretboard_scroll_projection",
    "format_mvp_error",
    "serialize_fretboard_projection",
]
