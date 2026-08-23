"""DO-012 timeline bindings carried by the DO-011 Lesson Media sidecar.

Bindings live here because they are media metadata: which asset follows which
lesson, and over what span. The musical anchors that say *where* a lesson
position is live with the projection instead, because they are derived from
canonical musical timing. The coordinator joins the two in presentation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from master_all_strings.media.catalog import load_media_catalog
from master_all_strings.media.contracts import (
    LessonMediaReferenceV1,
    LessonMediaRole,
    MediaContractError,
    MediaCueV1,
)
from master_all_strings.media.presentation import lesson_media_payload
from master_all_strings.media.resolver import MediaResolver
from master_all_strings.media.serialization import binding_to_dict, reference_to_dict
from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BINDING_SCHEMA = (
    REPO_ROOT
    / "resources"
    / "presentation"
    / "schema"
    / "media_timeline_binding_v1.schema.json"
)
CUE_SCHEMA = REPO_ROOT / "resources" / "media" / "schema" / "media_cue_v1.schema.json"

V = PRESENTATION_SCHEMA_VERSION
LESSON = "half_steps_one_string"
VIDEO = "half-steps-demo-video"


def _binding(**overrides: object) -> MediaTimelineBindingV1:
    base: dict[str, object] = {
        "schema_version": V,
        "binding_id": "binding-1",
        "lesson_id": LESSON,
        "media_id": VIDEO,
        "sync_mode": MediaSyncMode.SYNCHRONIZED,
        "lesson_anchor_seconds": 0.0,
        "media_anchor_seconds": 0.0,
    }
    base.update(overrides)
    return MediaTimelineBindingV1(**base)  # type: ignore[arg-type]


def _reference(**overrides: object) -> LessonMediaReferenceV1:
    base: dict[str, object] = {
        "schema_version": "1.0.0",
        "reference_id": "ref-1",
        "lesson_key": LESSON,
        "media_id": VIDEO,
        "role": LessonMediaRole.DEMONSTRATION,
    }
    base.update(overrides)
    return LessonMediaReferenceV1(**base)  # type: ignore[arg-type]


# --- cue binding -------------------------------------------------------------


def test_cue_time_and_lesson_time_are_distinct_fields() -> None:
    """time_seconds is a position inside the asset; lesson_time_seconds is not."""

    cue = MediaCueV1(
        cue_id="cue-1", time_seconds=1.8, label="Play on one string", lesson_time_seconds=3.5
    )
    assert cue.time_seconds == 1.8
    assert cue.lesson_time_seconds == 3.5
    assert cue.is_transport_bound is True


def test_an_unbound_cue_stays_media_local() -> None:
    cue = MediaCueV1(cue_id="cue-2", time_seconds=1.0, label="Zone 1")
    assert cue.lesson_time_seconds is None
    assert cue.is_transport_bound is False


def test_negative_lesson_time_is_refused() -> None:
    with pytest.raises(MediaContractError, match="lesson_time_seconds"):
        MediaCueV1(cue_id="cue-3", time_seconds=1.0, label="x", lesson_time_seconds=-0.1)


def test_non_finite_lesson_time_is_refused() -> None:
    # require_finite raises SpatialMappingError, matching how DO-011 already
    # validates time_seconds. Both derive from ValueError.
    with pytest.raises(ValueError, match="lesson_time_seconds"):
        MediaCueV1(
            cue_id="cue-4", time_seconds=1.0, label="x", lesson_time_seconds=float("inf")
        )


def test_bound_cue_may_point_past_the_media_duration() -> None:
    """A bound cue seeks the lesson, so it can reach where the media cannot."""

    cue = MediaCueV1(
        cue_id="cue-5", time_seconds=1.8, label="later", lesson_time_seconds=99.0
    )
    assert cue.lesson_time_seconds == 99.0


# --- reference binding -------------------------------------------------------


def test_reference_without_a_binding_is_detached_by_default() -> None:
    """Synchronization is never implied by media merely existing."""

    assert _reference().timeline_binding is None


def test_reference_carries_a_matching_binding() -> None:
    reference = _reference(timeline_binding=_binding())
    assert reference.timeline_binding is not None
    assert reference.timeline_binding.media_id == VIDEO


def test_binding_naming_a_different_lesson_is_refused() -> None:
    with pytest.raises(MediaContractError, match="lesson_key"):
        _reference(timeline_binding=_binding(lesson_id="ascending_scale"))


def test_binding_naming_a_different_asset_is_refused() -> None:
    """Otherwise the reference would synchronize something it is not about."""

    with pytest.raises(MediaContractError, match="media_id"):
        _reference(timeline_binding=_binding(media_id="some-other-media"))


def test_non_binding_object_is_refused() -> None:
    with pytest.raises(MediaContractError, match="MediaTimelineBindingV1"):
        _reference(timeline_binding={"binding_id": "x"})


# --- catalog + payload -------------------------------------------------------


def test_bundled_catalog_binds_the_golden_demonstration_clip() -> None:
    catalog = load_media_catalog()
    reference = next(r for r in catalog.references if r.reference_id == "ref-half-video")
    binding = reference.timeline_binding
    assert binding is not None
    assert binding.sync_mode is MediaSyncMode.SYNCHRONIZED
    # A 3.0s clip against a 4.5s lesson: partial range, declared honestly.
    assert binding.lesson_end_seconds == 3.0
    assert binding.media_end_seconds == 3.0


def test_bundled_catalog_leaves_other_media_detached() -> None:
    catalog = load_media_catalog()
    for reference_id in ("ref-half-intro", "ref-half-diagram"):
        reference = next(r for r in catalog.references if r.reference_id == reference_id)
        assert reference.timeline_binding is None


def test_bundled_catalog_exercises_both_cue_paths() -> None:
    catalog = load_media_catalog()
    cues = {cue.cue_id: cue for cue in catalog.get(VIDEO).cues}
    bound = [cue for cue in cues.values() if cue.is_transport_bound]
    unbound = [cue for cue in cues.values() if not cue.is_transport_bound]
    assert bound and unbound, "the catalog must demonstrate bound and unbound cues"
    # One bound cue deliberately points past the clip's own range.
    assert cues["cue-one-string"].lesson_time_seconds == 3.5


def test_lesson_media_payload_exposes_the_binding() -> None:
    payload = lesson_media_payload(LESSON)
    video = next(item for item in payload["items"] if item["media"]["media_id"] == VIDEO)
    assert video["timeline_binding"]["binding_id"] == "binding-half-steps-demo"
    assert video["timeline_binding"]["sync_mode"] == "synchronized"


def test_lesson_media_payload_reports_detached_media_as_null() -> None:
    payload = lesson_media_payload(LESSON)
    text = next(
        item for item in payload["items"] if item["media"]["media_id"] == "half-steps-intro-text"
    )
    assert text["timeline_binding"] is None


def test_payload_binding_validates_against_the_presentation_schema() -> None:
    """One contract, one wire shape: the sidecar reuses the presentation encoder."""

    schema = json.loads(BINDING_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    payload = lesson_media_payload(LESSON)
    for item in payload["items"]:
        if item["timeline_binding"] is not None:
            validator.validate(item["timeline_binding"])


def test_payload_cues_validate_against_the_extended_cue_schema() -> None:
    schema = json.loads(CUE_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    payload = lesson_media_payload(LESSON)
    seen = 0
    for item in payload["items"]:
        for cue in item["media"]["cues"]:
            validator.validate(cue)
            seen += 1
    assert seen > 0


def test_reference_serialization_round_trips_the_binding() -> None:
    reference = _reference(timeline_binding=_binding(lesson_end_seconds=3.0, media_end_seconds=3.0))
    encoded = reference_to_dict(reference)
    assert encoded["timeline_binding"]["lesson_end_seconds"] == 3.0
    assert binding_to_dict(None) is None


def test_unavailable_media_still_reports_what_it_would_have_followed() -> None:
    """A soft-failed asset should not silently lose its synchronization intent."""

    catalog = load_media_catalog()
    resolver = MediaResolver(asset_root=Path("does-not-exist"))
    resolved = resolver.resolve_for_lesson(catalog, LESSON)
    video = next(item for item in resolved if item.media.media_id == VIDEO)
    assert video.available is False
    assert video.timeline_binding is not None
