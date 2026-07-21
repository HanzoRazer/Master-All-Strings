"""Deterministic candidate generation for the Musical Spatial Mapping Engine.

This module answers *"where can this note be played?"* -- every valid playable
position for one canonical musical event on one configured instrument. It does not
answer *"which position should we recommend?"*; selection, scoring, tie-breaking,
preference policy and pedagogical interpretation are deliberately absent and belong
to a later Dev Order.

Ambiguity is preserved: several playable positions is the normal case, and all of
them are returned.
"""

from __future__ import annotations

from collections.abc import Iterator

from master_all_strings.core.foundation import FingerboardMode, SpatialMappingError
from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.instruments import InstrumentProfile, StringProfile

from .candidate_builders import HYBRID_UNSUPPORTED_MESSAGE, build_candidate
from .geometry import geometry_tolerance
from .models import MappingConstraints, SpatialPosition

__all__ = ["generate_candidates"]

# A module-level frozen singleton rather than an instantiated default argument:
# MappingConstraints is immutable so sharing one instance is safe, and ruff's B008
# forbids a call in a default. Public behavior is identical to a default-constructed
# MappingConstraints, and callers may continue to omit the argument entirely.
_DEFAULT_CONSTRAINTS = MappingConstraints()


def _string_is_admissible(string: StringProfile, constraints: MappingConstraints) -> bool:
    """Return whether hard constraints and profile state admit this string at all."""

    if not string.enabled:
        return False
    if constraints.allowed_string_ids is not None:
        if string.string_id not in constraints.allowed_string_ids:
            return False
    return string.string_id not in constraints.excluded_string_ids


def _maximum_physical_position(
    string: StringProfile,
    instrument: InstrumentProfile,
) -> float | None:
    """Return the tightest declared upper bound measured from the nut.

    Only bounds that are actually declared participate; an omitted optional maximum
    is not incomplete data. ``physical_fret_count`` applies to fretted instruments
    only. Returns ``None`` when nothing bounds the string from the nut, in which case
    the MIDI domain is the only remaining limit (see ``_candidates_for_string``).
    """

    bounds: list[float] = []
    if string.maximum_semitone_position is not None:
        bounds.append(float(string.maximum_semitone_position))
    if (
        instrument.fingerboard_mode is FingerboardMode.FRETTED
        and instrument.physical_fret_count is not None
    ):
        bounds.append(float(instrument.physical_fret_count))
    if not bounds:
        return None
    return min(bounds)


def _candidates_for_string(
    string: StringProfile,
    event: MusicalEvent,
    instrument: InstrumentProfile,
    constraints: MappingConstraints,
) -> Iterator[SpatialPosition]:
    """Yield the single candidate this string can produce, if any.

    A string sounds a given pitch at exactly one place, so this yields at most one
    position; it is written as an iterator so the caller can flatten uniformly.
    """

    tolerance = geometry_tolerance()

    # The capo becomes the effective nut: it raises the string's open pitch, and
    # positions relative to it are what "open" and the maximum-relative constraint
    # are measured against.
    effective_open_midi_note = string.open_midi_note + constraints.capo_position
    relative = event.midi_note - effective_open_midi_note
    if relative < -tolerance:
        return  # below the open (or capoed) pitch of this string

    # Measured from the nut, so the capo's own offset is included again.
    physical = event.midi_note - string.open_midi_note

    maximum_physical = _maximum_physical_position(string, instrument)
    if maximum_physical is not None and physical > maximum_physical + tolerance:
        return
    if constraints.maximum_relative_semitone_position is not None:
        if relative > constraints.maximum_relative_semitone_position + tolerance:
            return
    # The MIDI ceiling needs no explicit test here. A string with no declared maximum
    # is bounded by the MIDI domain, but the sounding pitch of every candidate is
    # exactly ``event.midi_note`` (``open_midi_note + physical`` telescopes back to
    # it), and MusicalEvent already constrains that to 0..127. An explicit check
    # would be unreachable, so the bound is documented rather than coded.

    yield build_candidate(
        string=string,
        fingerboard_mode=instrument.fingerboard_mode,
        scale_length_mm=instrument.scale_length_mm,
        sounding_midi_note=event.midi_note,
        cents_offset=event.cents_offset,
        relative_semitone_position=relative,
        physical_semitone_position_from_nut=physical,
    )


def generate_candidates(
    event: MusicalEvent,
    instrument: InstrumentProfile,
    constraints: MappingConstraints = _DEFAULT_CONSTRAINTS,
) -> tuple[SpatialPosition, ...]:
    """Return every playable position for ``event`` on ``instrument``.

    Candidate order is deterministic stable enumeration only, sorted by
    ``(display_order, relative_semitone_position)``. **It does not represent ranking,
    recommendation, playability preference, or pedagogical priority.** Downstream
    consumers must not interpret index zero as the preferred position.

    An event with no playable position returns an empty tuple; that is a valid answer
    about the instrument, not an error. Errors are raised only for unsupported modes
    or internally inconsistent data.

    ``constraints`` are hard admissibility rules. Soft preferences live in
    ``MappingPreferences`` and are not consulted here -- this operation produces
    candidates, it does not choose between them.
    """

    if instrument.fingerboard_mode is FingerboardMode.HYBRID:
        raise SpatialMappingError(HYBRID_UNSUPPORTED_MESSAGE)
    # A capo clamps behind a fret, so a fractional capo on a fretted instrument is
    # internally inconsistent data. It is also silently corrupting: positions from
    # the nut stay integral (they are midi_note - open_midi_note), so nothing else
    # would flag it, but no candidate could ever reach relative position 0.0 and the
    # instrument would quietly lose every open-string candidate.
    if instrument.fingerboard_mode is FingerboardMode.FRETTED:
        capo = constraints.capo_position
        if abs(capo - round(capo)) > geometry_tolerance():
            raise SpatialMappingError(
                "fretted instruments require a whole-semitone capo_position; "
                f"got {capo!r}",
            )

    candidates = [
        candidate
        for string in instrument.strings
        if _string_is_admissible(string, constraints)
        for candidate in _candidates_for_string(string, event, instrument, constraints)
    ]
    # Sorted explicitly rather than relying on profile declaration order: display_order
    # is the instrument-defined enumeration, and the profile may list strings in any
    # order. Sorting on the candidate's own fields also makes the result independent
    # of how the profile happened to be written.
    #
    # That independence rests on an invariant owned elsewhere: InstrumentProfile
    # rejects duplicate display_order values across its strings, so the sort key is
    # total and no pair of candidates can tie. If that validation is ever relaxed,
    # ties here would silently fall back to declaration order and this guarantee
    # would break -- test_ordering_relies_on_profile_display_order_uniqueness pins it.
    candidates.sort(key=lambda c: (c.display_order, c.relative_semitone_position))
    return tuple(candidates)
