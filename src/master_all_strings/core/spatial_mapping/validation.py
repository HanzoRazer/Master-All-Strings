"""Shared validation helpers for spatial-mapping contracts.

The helpers now live in the dependency-neutral ``core.foundation`` module (so
``instruments`` can use them without importing ``core.spatial_mapping``). They are
re-exported here so existing ``from .validation import ...`` call sites keep working.
"""

from __future__ import annotations

from master_all_strings.core.foundation import (
    require_finite,
    require_index,
    require_midi_note,
    require_non_empty,
    require_nonnegative,
    require_positive,
)

__all__ = [
    "require_finite",
    "require_index",
    "require_midi_note",
    "require_non_empty",
    "require_nonnegative",
    "require_positive",
]
