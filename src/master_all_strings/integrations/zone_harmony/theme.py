"""Presentation-only mapping from semantic IDs to the official Zone palette."""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import ZoneSemanticProjectionV1


@dataclass(frozen=True)
class ZoneVisualTokenV1:
    semantic_id: str
    token_name: str
    display_name: str
    color_hex: str

    def __post_init__(self) -> None:
        if not self.semantic_id or not self.token_name or not self.display_name:
            raise ProjectionBuildError("Zone visual token identifiers must be non-empty")
        if len(self.color_hex) != 7 or not self.color_hex.startswith("#"):
            raise ProjectionBuildError("Zone visual token color must use #RRGGBB")
        try:
            int(self.color_hex[1:], 16)
        except ValueError as exc:
            raise ProjectionBuildError("Zone visual token color must use hexadecimal") from exc


@dataclass(frozen=True)
class ZoneVisualThemeV1:
    theme_version: str
    theme_id: str
    tokens: tuple[ZoneVisualTokenV1, ...]

    def __post_init__(self) -> None:
        if self.theme_version != "1.0":
            raise ProjectionBuildError("unsupported Zone visual theme version")
        semantic_ids = [token.semantic_id for token in self.tokens]
        if len(semantic_ids) != len(set(semantic_ids)):
            raise ProjectionBuildError("Zone visual theme semantic IDs must be unique")

    def token_for(self, semantic_id: str) -> ZoneVisualTokenV1 | None:
        return next((token for token in self.tokens if token.semantic_id == semantic_id), None)


DEFAULT_ZONE_VISUAL_THEME_V1 = ZoneVisualThemeV1(
    theme_version="1.0",
    theme_id="zone-tritone-canonical-light-v1",
    tokens=(
        ZoneVisualTokenV1("ZONE_1", "zone-1", "Deep Blue", "#1A4D8F"),
        ZoneVisualTokenV1("ZONE_2", "zone-2", "Warm Amber", "#D4860F"),
        ZoneVisualTokenV1("TRITONE_ANCHOR", "tritone-anchor", "Bold Red", "#C41E3A"),
        ZoneVisualTokenV1(
            "HALF_STEP_CROSSING", "half-step-crossing", "Bright Green", "#2E8B57"
        ),
    ),
)


def apply_zone_visual_theme(
    semantics: ZoneSemanticProjectionV1,
    theme: ZoneVisualThemeV1 = DEFAULT_ZONE_VISUAL_THEME_V1,
) -> tuple[ZoneVisualTokenV1, ...]:
    """Resolve presentation tokens without interpreting musical relationships."""

    semantic_ids = (semantics.zone_id, *semantics.semantic_roles)
    resolved: list[ZoneVisualTokenV1] = []
    seen: set[str] = set()
    for semantic_id in semantic_ids:
        if semantic_id in seen:
            continue
        seen.add(semantic_id)
        token = theme.token_for(semantic_id)
        if token is not None:
            resolved.append(token)
    return tuple(resolved)


__all__ = [
    "DEFAULT_ZONE_VISUAL_THEME_V1",
    "ZoneVisualThemeV1",
    "ZoneVisualTokenV1",
    "apply_zone_visual_theme",
]
