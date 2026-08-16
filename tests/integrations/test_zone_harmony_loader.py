from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from master_all_strings.integrations.zone_harmony import (
    ZoneId,
    ZoneSemanticLoadError,
    ZoneSemanticRole,
    load_zone_semantics_from_bundle,
)


def _payload() -> dict[str, object]:
    transition = {
        "from_event_id": "comp:000000",
        "to_event_id": "comp:000001",
        "interval_semitones": 1,
        "transition_type": "HALF_STEP",
        "from_zone": "ZONE_1",
        "to_zone": "ZONE_2",
        "crosses_zone": True,
        "semantic_roles": ["HALF_STEP_CROSSING"],
    }
    return {
        "artifact_type": "zone_semantics",
        "schema_version": "1.0",
        "theory_name": "String Master Zone/Tritone",
        "theory_version": "0.1.0",
        "source_id": "request-1",
        "events": [
            {
                "event_id": "comp:000000",
                "pitch_class": 0,
                "zone_id": "ZONE_1",
                "tritone_axis_id": "0-6",
                "semantic_roles": ["ZONE_1"],
            },
            {
                "event_id": "comp:000001",
                "pitch_class": 1,
                "zone_id": "ZONE_2",
                "tritone_axis_id": "1-7",
                "semantic_roles": ["ZONE_2", "HALF_STEP_CROSSING"],
                "transition_from_previous": transition,
            },
        ],
        "transitions": [transition],
        "provenance": {
            "producer": "sg-agentd",
            "source_bundle_id": "clip_1",
            "generation_id": "request-1",
            "string_master_commit": "5d7af1d0efcd026c8cdf861c8a0f8467d77ee03e",
            "authority": {"producer": "zt_band"},
        },
    }


def _write_bundle(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    if payload is None:
        manifest = {"artifacts": [], "extensions": {}}
    else:
        artifact_bytes = (json.dumps(payload, sort_keys=True) + "\n").encode()
        (bundle / "zone_semantics.json").write_bytes(artifact_bytes)
        manifest = {
            "artifacts": [],
            "extensions": {
                "zone_semantics": {
                    "artifact_type": "zone_semantics",
                    "schema_version": "1.0",
                    "path": "zone_semantics.json",
                    "sha256": f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}",
                    "content_type": "application/json",
                }
            },
        }
    (bundle / "clip.bundle.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def test_loads_hash_verified_manifest_declared_semantics(tmp_path: Path) -> None:
    loaded = load_zone_semantics_from_bundle(_write_bundle(tmp_path, _payload()))

    assert loaded is not None
    assert loaded.events[0].zone_id is ZoneId.ZONE_1
    assert loaded.events[1].semantic_roles[-1] is ZoneSemanticRole.HALF_STEP_CROSSING
    assert loaded.provenance.source_bundle_id == "clip_1"


def test_missing_optional_semantics_returns_none(tmp_path: Path) -> None:
    assert load_zone_semantics_from_bundle(_write_bundle(tmp_path)) is None


def test_rejects_hash_mismatch(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path, _payload())
    (bundle / "zone_semantics.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ZoneSemanticLoadError, match="sha256 mismatch"):
        load_zone_semantics_from_bundle(bundle)


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema_version"] = "2.0"

    with pytest.raises(ZoneSemanticLoadError, match="unsupported Zone semantic schema"):
        load_zone_semantics_from_bundle(_write_bundle(tmp_path, payload))


def test_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    manifest = {
        "extensions": {
            "zone_semantics": {
                "artifact_type": "zone_semantics",
                "schema_version": "1.0",
                "path": "../outside.json",
                "sha256": "sha256:" + "0" * 64,
                "content_type": "application/json",
            }
        }
    }
    (bundle / "clip.bundle.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ZoneSemanticLoadError, match="escapes the bundle"):
        load_zone_semantics_from_bundle(bundle)
