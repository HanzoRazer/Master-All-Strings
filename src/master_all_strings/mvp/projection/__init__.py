"""MVP fretboard product projection."""

from master_all_strings.mvp.projection.builder import (
    SelectedNoteInput,
    build_fretboard_scroll_projection,
)
from master_all_strings.mvp.projection.models import (
    FRETBOARD_SCROLL_PROJECTION_TYPE,
    FRETBOARD_SCROLL_PROJECTION_VERSION,
    FretboardProjectedNoteV1,
    FretboardScrollProjectionV1,
    ProjectedNoteStatus,
    SelectionOrigin,
    ZoneSemanticProjectionV1,
)
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    deserialize_fretboard_projection,
    serialize_fretboard_projection,
    validate_projection,
)

__all__ = [
    "FRETBOARD_SCROLL_PROJECTION_TYPE",
    "FRETBOARD_SCROLL_PROJECTION_VERSION",
    "FretboardProjectedNoteV1",
    "FretboardScrollProjectionV1",
    "ProjectedNoteStatus",
    "SelectedNoteInput",
    "SelectionOrigin",
    "ZoneSemanticProjectionV1",
    "build_fretboard_scroll_projection",
    "compute_projection_digest",
    "deserialize_fretboard_projection",
    "serialize_fretboard_projection",
    "validate_projection",
]
