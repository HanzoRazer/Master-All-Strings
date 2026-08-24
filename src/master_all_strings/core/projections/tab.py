"""Guitar TAB projection from a canonical revision (DO-013).

TAB is the projection with a spatial dependency, and therefore the one that could
most easily start deciding things. It must not.

Every string and fret it prints was chosen upstream by spatial selection. This
module looks the choice up; it never calls MSME, never ranks candidates, and
never falls back to the first one. Where no choice was made it says
``UNRESOLVED`` — which is more useful than a plausible fingering, because a
plausible fingering is indistinguishable from a real decision and a learner would
practise it.

It also checks the choice rather than trusting it: a selected string and fret
that does not sound the canonical pitch is a contradiction between two
authorities, and passing it through would let TAB quietly contradict the score it
claims to render.
"""

from __future__ import annotations

from collections.abc import Mapping

from master_all_strings.core.projections.contracts import (
    PROJECTION_SCHEMA_VERSION,
    TabEventStatus,
    TabEventV1,
    TabProjectionV1,
)
from master_all_strings.core.score.errors import ScoreContractError, require_identifier
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.spatial_mapping.models import SpatialPosition

__all__ = [
    "SelectedSpatialRealizationV1",
    "build_tab_projection",
    "validate_tab_spatial_identity",
]


class SelectedSpatialRealizationV1:
    """One canonical event's chosen realization, or an explicit absence.

    Deliberately not a candidate list. A builder handed candidates would be one
    line away from picking one, and this type is shaped so that line cannot be
    written: there is a position or there is a reason there is not.
    """

    __slots__ = ("canonical_event_id", "position", "unplayable_reason")

    def __init__(
        self,
        *,
        canonical_event_id: str,
        position: SpatialPosition | None = None,
        unplayable_reason: str | None = None,
    ) -> None:
        require_identifier(canonical_event_id, "canonical_event_id")
        if position is not None and unplayable_reason is not None:
            raise ScoreContractError(
                "a realization is either playable or unplayable, not both"
            )
        if position is not None and not isinstance(position, SpatialPosition):
            raise ScoreContractError("position must be a SpatialPosition")
        if unplayable_reason is not None:
            require_identifier(unplayable_reason, "unplayable_reason")
        self.canonical_event_id = canonical_event_id
        self.position = position
        self.unplayable_reason = unplayable_reason

    @property
    def status(self) -> TabEventStatus:
        if self.position is not None:
            return TabEventStatus.PLAYABLE
        if self.unplayable_reason is not None:
            return TabEventStatus.UNPLAYABLE
        return TabEventStatus.UNRESOLVED


def validate_tab_spatial_identity(
    *, canonical_midi_note: int, position: SpatialPosition
) -> None:
    """Check that the selected realization sounds the canonical pitch.

    Two authorities describe this note -- Musical Core says which pitch, spatial
    selection says where it is played. If they disagree, one of them is wrong and
    TAB is not the place to decide which. Refuse rather than render.
    """

    if position.sounding_midi_note != canonical_midi_note:
        raise ScoreContractError(
            "selected realization does not sound the canonical pitch: "
            f"canonical MIDI {canonical_midi_note}, selected string "
            f"{position.string_id!r} sounds {position.sounding_midi_note}"
        )


def build_tab_projection(
    revision: CanonicalScoreRevisionV1,
    *,
    instrument_profile_id: str,
    selected: Mapping[str, SelectedSpatialRealizationV1],
) -> TabProjectionV1:
    """Project one canonical revision as TAB under one instrument profile.

    ``selected`` is keyed by canonical event id. An event missing from it is
    ``UNRESOLVED``; nothing here consults candidates to fill the gap.
    """

    if not isinstance(revision, CanonicalScoreRevisionV1):
        raise ScoreContractError("expected CanonicalScoreRevisionV1")
    require_identifier(instrument_profile_id, "instrument_profile_id")

    events: list[TabEventV1] = []

    for event in sorted(revision.events, key=lambda e: (e.start_tick, e.event_id)):
        realization = selected.get(event.event_id)
        if realization is None:
            realization = SelectedSpatialRealizationV1(canonical_event_id=event.event_id)
        if realization.canonical_event_id != event.event_id:
            raise ScoreContractError(
                "selected realization is keyed to a different canonical event"
            )

        status = realization.status
        string_id: str | None = None
        fret: int | None = None
        cents: float | None = None

        if status is TabEventStatus.PLAYABLE:
            position = realization.position
            assert position is not None
            validate_tab_spatial_identity(
                canonical_midi_note=event.midi_note, position=position
            )
            string_id = position.string_id
            fret = position.physical_fret_number
            cents = position.cents_offset
        # UNPLAYABLE and UNRESOLVED are not projection limitations: they are
        # first-class answers this contract can state. Recording them as
        # unsupported features would imply TAB fell short, when in fact it
        # reported exactly what upstream decided.

        events.append(
            TabEventV1(
                schema_version=PROJECTION_SCHEMA_VERSION,
                canonical_event_id=event.event_id,
                start_tick=event.start_tick,
                duration_ticks=event.duration_ticks,
                midi_note=event.midi_note,
                status=status,
                string_id=string_id,
                fret=fret,
                cents_offset=cents,
            )
        )

    return TabProjectionV1(
        schema_version=PROJECTION_SCHEMA_VERSION,
        canonical_revision_id=revision.revision_id,
        instrument_profile_id=instrument_profile_id,
        events=tuple(events),
    )
