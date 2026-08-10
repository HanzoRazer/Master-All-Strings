"""MVP automatic fingering scaffold pending DO-004 / ADR-0005.

Uses MSME enumeration order plus soft lesson spatial guidance. This is not the
constitutional deterministic selector; it exists so LessonAssignment can prove
end-to-end musical equivalence today without inventing a second authority.
"""

from __future__ import annotations

from master_all_strings.core.spatial_mapping import SpatialPosition
from master_all_strings.core.spatial_mapping.enums import OpenStringPolicy

from .enums import OpenStringPreference
from .errors import LessonValidationError
from .resolver import SpatialSelectionRequestV1

__all__ = ["select_automatic_position"]

_OPEN_PREF_TO_POLICY = {
    OpenStringPreference.ALLOW: OpenStringPolicy.ALLOW,
    OpenStringPreference.PREFER: OpenStringPolicy.PREFER,
    OpenStringPreference.AVOID: OpenStringPolicy.AVOID,
    OpenStringPreference.EXCLUDE: OpenStringPolicy.EXCLUDE,
}


def select_automatic_position(
    candidates: tuple[SpatialPosition, ...],
    *,
    spatial: SpatialSelectionRequestV1,
) -> SpatialPosition:
    """Pick one candidate deterministically from MSME enumeration order.

    Soft preferred fret region filters the pool when any candidate remains.
    Open-string preference applies as a soft/hard filter per policy mapping.
    """

    if not candidates:
        raise LessonValidationError(
            "no MSME candidates available for automatic selection",
            code="unplayable",
        )

    pool = list(candidates)
    policy = _OPEN_PREF_TO_POLICY[spatial.open_string_preference]
    if policy is OpenStringPolicy.EXCLUDE:
        filtered = [c for c in pool if not c.is_open_string]
        if filtered:
            pool = filtered
        else:
            raise LessonValidationError(
                "open strings excluded and no stopped candidates remain",
                code="unplayable",
            )
    elif policy is OpenStringPolicy.AVOID:
        filtered = [c for c in pool if not c.is_open_string]
        if filtered:
            pool = filtered
    elif policy is OpenStringPolicy.PREFER:
        preferred = [c for c in pool if c.is_open_string]
        if preferred:
            pool = preferred

    if spatial.preferred_fret_min is not None or spatial.preferred_fret_max is not None:
        lo = spatial.preferred_fret_min
        hi = spatial.preferred_fret_max
        region = []
        for candidate in pool:
            fret = candidate.physical_fret_number
            if fret is None:
                continue
            if lo is not None and fret < lo:
                continue
            if hi is not None and fret > hi:
                continue
            region.append(candidate)
        if region:
            pool = region

    # MSME already returns (display_order, relative_semitone_position) order.
    # Re-sort explicitly so this MVP scaffold stays stable if generation order changes.
    # string_id is only a temporary deterministic tie-breaker for this scaffold; it is
    # not a musical rule and should be replaced when DO-004 / ADR-0005 lands.
    pool.sort(key=lambda c: (c.display_order, c.relative_semitone_position, c.string_id))
    return pool[0]
