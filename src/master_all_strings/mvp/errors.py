"""User-facing MVP application errors."""

from __future__ import annotations


class MvpError(Exception):
    """Base MVP application error."""

    def __init__(self, message: str, *, code: str = "mvp_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class LessonLoadError(MvpError):
    def __init__(self, message: str = "Unable to load lesson") -> None:
        super().__init__(message, code="lesson_load_error")


class UnsupportedMidiError(MvpError):
    def __init__(self, message: str = "Unsupported MIDI file") -> None:
        super().__init__(message, code="unsupported_midi")


class UnknownInstrumentError(MvpError):
    def __init__(self, message: str = "Unknown instrument profile") -> None:
        super().__init__(message, code="unknown_instrument")


class ProjectionBuildError(MvpError):
    def __init__(self, message: str = "Unable to build projection") -> None:
        super().__init__(message, code="projection_build_error")


class PlaybackPlanBuildError(MvpError):
    def __init__(self, message: str = "Unable to build playback plan") -> None:
        super().__init__(message, code="playback_plan_build_error")


class UnsupportedPlaybackPlanVersionError(MvpError):
    def __init__(self, message: str = "Unsupported playback plan version") -> None:
        super().__init__(message, code="unsupported_playback_plan_version")


class PracticePolicyBuildError(MvpError):
    def __init__(self, message: str = "Unable to build practice policy") -> None:
        super().__init__(message, code="practice_policy_build_error")


class UnsupportedProjectionVersionError(MvpError):
    def __init__(self, message: str = "Unsupported projection version") -> None:
        super().__init__(message, code="unsupported_projection_version")


def format_mvp_error(exc: BaseException) -> str:
    """Map internal failures to concise user-readable text."""

    if isinstance(exc, MvpError):
        return exc.message
    text = str(exc)
    lowered = text.lower()
    if "midi" in lowered:
        return "Unsupported MIDI file"
    if "instrument" in lowered:
        return "Unknown instrument profile"
    if "schema" in lowered or "assignment" in lowered:
        return "Invalid lesson"
    if "projection" in lowered:
        return "Internal projection failure"
    if "no note" in lowered or "missing_content" in lowered:
        return "No usable musical events"
    return "Unable to load lesson"
