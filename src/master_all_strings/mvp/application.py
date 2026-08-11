"""MVP application composition root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from master_all_strings.core.spatial_mapping.serialization import instrument_profile_from_mapping
from master_all_strings.instruments import InstrumentProfile
from master_all_strings.mvp.demo_library import (
    default_demo_root,
    load_demo_assignment,
    load_demo_manifest,
)
from master_all_strings.mvp.errors import UnknownInstrumentError
from master_all_strings.mvp.models import (
    MvpInstrumentOptionV1,
    MvpLessonSummaryV1,
    MvpLoadStatus,
    MvpProjectionResponseV1,
)
from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator, MvpOrchestrationResultV1

__all__ = ["MvpApplication", "load_default_instrument_catalog"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_INSTRUMENT_DIR = _REPO_ROOT / "resources" / "instruments" / "examples"
_PRIMARY_INSTRUMENT = "guitar-standard-6"


def load_default_instrument_catalog() -> dict[str, InstrumentProfile]:
    catalog: dict[str, InstrumentProfile] = {}
    for path in sorted(_INSTRUMENT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = instrument_profile_from_mapping(data)
        catalog[profile.instrument_id] = profile
    return catalog


class MvpApplication:
    """Thin composition root over demo library + orchestrator."""

    def __init__(
        self,
        *,
        instrument_profiles: dict[str, InstrumentProfile] | None = None,
        demo_root: Path | None = None,
    ) -> None:
        self._profiles = instrument_profiles or load_default_instrument_catalog()
        self._demo_root = demo_root or default_demo_root()
        self._orchestrator = MvpLessonOrchestrator(self._profiles)

    def list_demos(self) -> tuple[MvpLessonSummaryV1, ...]:
        return tuple(entry.to_summary() for entry in load_demo_manifest(self._demo_root))

    def list_instruments(self) -> tuple[MvpInstrumentOptionV1, ...]:
        options: list[MvpInstrumentOptionV1] = []
        for profile in self._orchestrator.list_instruments():
            options.append(
                MvpInstrumentOptionV1(
                    instrument_id=profile.instrument_id,
                    display_name=profile.display_name,
                    experimental=profile.instrument_id != _PRIMARY_INSTRUMENT,
                )
            )
        return tuple(options)

    def run_demo(
        self,
        demo_id: str,
        *,
        instrument_profile_id: str | None = None,
    ) -> MvpProjectionResponseV1:
        assignment = load_demo_assignment(demo_id, root=self._demo_root)
        result = self._orchestrator.load_assignment(
            assignment,
            instrument_profile_id=instrument_profile_id
            or assignment.spatial_guidance.instrument_profile_id,
        )
        return self._to_response(result)

    def run_midi(
        self,
        midi_bytes: bytes,
        *,
        instrument_profile_id: str,
        assignment_id: str = "local-midi",
        source_name: str | None = None,
        title: str | None = None,
    ) -> MvpProjectionResponseV1:
        if instrument_profile_id not in self._profiles:
            raise UnknownInstrumentError(f"Unknown instrument profile: {instrument_profile_id}")
        result = self._orchestrator.import_midi(
            midi_bytes,
            assignment_id=assignment_id,
            instrument_profile_id=instrument_profile_id,
            source_name=source_name,
            title=title,
        )
        return self._to_response(result)

    def run_assignment_json(
        self,
        text: str | bytes | dict[str, Any],
        *,
        instrument_profile_id: str | None = None,
    ) -> MvpProjectionResponseV1:
        result = self._orchestrator.load_assignment_json(
            text,
            instrument_profile_id=instrument_profile_id,
        )
        return self._to_response(result)

    @staticmethod
    def _to_response(result: MvpOrchestrationResultV1) -> MvpProjectionResponseV1:
        return MvpProjectionResponseV1(
            status=MvpLoadStatus.READY,
            summary_title=result.assignment.title,
            instrument_id=result.projection.instrument.instrument_id,
            behavior_digest=result.behavior_digest,
            projection=result.projection,
            warnings=result.projection.warnings,
            unsupported_features=result.projection.unsupported_features,
        )
