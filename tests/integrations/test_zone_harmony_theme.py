from __future__ import annotations

import pytest

from master_all_strings.integrations.zone_harmony import (
    DEFAULT_ZONE_VISUAL_THEME_V1,
    ZoneVisualThemeV1,
    ZoneVisualTokenV1,
    apply_zone_visual_theme,
)
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import ZoneSemanticProjectionV1


def test_official_semantic_palette_is_pinned() -> None:
    assert {
        token.semantic_id: (token.display_name, token.color_hex)
        for token in DEFAULT_ZONE_VISUAL_THEME_V1.tokens
    } == {
        "ZONE_1": ("Deep Blue", "#1A4D8F"),
        "ZONE_2": ("Warm Amber", "#D4860F"),
        "TRITONE_ANCHOR": ("Bold Red", "#C41E3A"),
        "HALF_STEP_CROSSING": ("Bright Green", "#2E8B57"),
    }


def test_theme_resolves_projection_ids_without_theory_inference() -> None:
    semantics = ZoneSemanticProjectionV1(
        zone_id="ZONE_1",
        semantic_roles=("ZONE_1", "TRITONE_ANCHOR", "HALF_STEP_CROSSING"),
        tritone_axis_id="0-6",
    )

    tokens = apply_zone_visual_theme(semantics)

    assert [token.token_name for token in tokens] == [
        "zone-1",
        "tritone-anchor",
        "half-step-crossing",
    ]


def test_unmapped_non_visual_role_is_ignored() -> None:
    semantics = ZoneSemanticProjectionV1(
        zone_id="ZONE_2",
        semantic_roles=("ZONE_2", "WHOLE_STEP_STABLE"),
    )

    assert [token.semantic_id for token in apply_zone_visual_theme(semantics)] == ["ZONE_2"]


@pytest.mark.parametrize(
    "token",
    [
        ("", "token", "Name", "#123456"),
        ("ID", "token", "Name", "123456"),
        ("ID", "token", "Name", "#ZZZZZZ"),
    ],
)
def test_visual_token_rejects_invalid_presentation_values(token: tuple[str, ...]) -> None:
    with pytest.raises(ProjectionBuildError):
        ZoneVisualTokenV1(*token)


def test_theme_rejects_unknown_version_and_duplicate_semantic_ids() -> None:
    token = ZoneVisualTokenV1("ZONE_1", "zone-1", "Deep Blue", "#1A4D8F")
    with pytest.raises(ProjectionBuildError, match="version"):
        ZoneVisualThemeV1("2.0", "future", (token,))
    with pytest.raises(ProjectionBuildError, match="unique"):
        ZoneVisualThemeV1("1.0", "duplicate", (token, token))
