"""Application-facing MVP state models (not domain duplicates)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.mvp.projection.models import FretboardScrollProjectionV1


class MvpLoadStatus(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class MvpLessonSummaryV1:
    demo_id: str
    title: str
    description: str
    instrument_profile_id: str
    demonstrates: tuple[str, ...]
    known_limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MvpInstrumentOptionV1:
    instrument_id: str
    display_name: str
    experimental: bool = False


@dataclass(frozen=True)
class MvpProjectionResponseV1:
    status: MvpLoadStatus
    summary_title: str
    instrument_id: str
    behavior_digest: str
    projection: FretboardScrollProjectionV1
    warnings: tuple[str, ...] = ()
    unsupported_features: tuple[str, ...] = ()
