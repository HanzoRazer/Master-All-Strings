"""Internal builders that construct validated candidate positions.

This module is private to candidate generation. It owns the derivation of the
fields that follow from a resolved (string, target pitch) pair, so
``candidate_generation`` can stay focused on admissibility.

Two modelling decisions are encoded here and are worth stating explicitly, because
both are places where an implementation could silently start interpreting
performance technique -- which candidate generation is not authorized to do.

**Semitone anchors versus microtonal displacement.** ``relative_semitone_position``
and ``physical_semitone_position_from_nut`` are semitone *anchors*; ``cents_offset``
carries microtonal displacement separately and unchanged. The two are deliberately
not folded together. A fretted candidate anchors to the nearest canonical fret and
carries the offset alongside it, per the DO-003 ruling on ``cents_offset``; the
fretless case is modelled symmetrically. Folding cents into the position would also
make ``cents_offset`` redundant with it, and the contract carries both.

**Geometry follows the anchor, not the offset.** ``normalized_position`` and
``distance_from_nut_mm`` derive from the semitone anchor and ignore
``cents_offset``. Displacing the geometry by the offset would assert where a finger
must land to sound the pitch -- a performance-technique claim reserved for a later
feasibility layer.
"""

from __future__ import annotations

from master_all_strings.core.foundation import FingerboardMode, SpatialMappingError
from master_all_strings.instruments import StringProfile

from .enums import SpatialReferenceType
from .geometry import distance_from_nut_mm, geometry_tolerance, normalized_position_for_semitones
from .models import SpatialPosition

__all__ = ["build_candidate"]

# Single source for the unsupported-mode message. Generation rejects HYBRID up front
# so a caller fails before any per-string work, and the builder rejects it again for
# callers reaching it directly; sharing the text keeps the two from drifting apart.
HYBRID_UNSUPPORTED_MESSAGE = (
    "hybrid candidate generation is not yet defined; it requires a representative "
    "instrument profile and a defined transition model between discrete and "
    "continuous regions before behavior can be specified"
)


def _snap_to_integer(value: float) -> float:
    """Return ``value`` snapped to a whole number when within geometry tolerance.

    Positions are computed by subtraction of exact values, so an integral result is
    normally exact. Snapping guards the case where a caller supplies a capo position
    that is integral only within floating-point error, keeping the
    ``relative_semitone_position == 0.0`` biconditional on SpatialPosition exact.
    """

    nearest = round(value)
    if abs(value - nearest) <= geometry_tolerance():
        return float(nearest)
    return value


def _is_integral(value: float) -> bool:
    return abs(value - round(value)) <= geometry_tolerance()


def _is_effectively_zero(value: float) -> bool:
    """Return whether ``value`` is zero to within tolerance.

    Used for ``cents_offset`` so the reference-type decision matches the tolerant
    treatment positions already receive. Exact ``== 0.0`` would let float noise from
    an upstream normalizer (a residual ``1e-15``) reclassify an exact chromatic
    target from IMAGINARY_SEMITONE to CONTINUOUS_POSITION, changing an externally
    visible field on the strength of numerical dust.
    """

    return abs(value) <= geometry_tolerance()


def build_candidate(
    *,
    string: StringProfile,
    fingerboard_mode: FingerboardMode,
    scale_length_mm: float | None,
    sounding_midi_note: int,
    cents_offset: float,
    relative_semitone_position: float,
    physical_semitone_position_from_nut: float,
) -> SpatialPosition:
    """Build one validated :class:`SpatialPosition` for a resolved string/pitch pair.

    Callers are responsible for admissibility (range, constraints, enabled state);
    this function only derives the dependent fields and enforces contract validity.
    """

    relative = _snap_to_integer(relative_semitone_position)
    physical = _snap_to_integer(physical_semitone_position_from_nut)

    if fingerboard_mode is FingerboardMode.HYBRID:
        raise SpatialMappingError(HYBRID_UNSUPPORTED_MESSAGE)

    physical_fret_number: int | None
    if fingerboard_mode is FingerboardMode.FRETTED:
        if not _is_integral(physical):
            raise SpatialMappingError(
                "fretted instruments require whole-semitone positions; "
                f"derived a fractional position of {physical!r} from the nut "
                "(a fractional capo_position on a fretted instrument is "
                "internally inconsistent)",
            )
        physical_fret_number = int(round(physical))
        reference_type = SpatialReferenceType.PHYSICAL_FRET
    else:
        physical_fret_number = None
        # An exact semitone target uses the imaginary-semitone reference, which is
        # authoritative for ordinary chromatic fretless instruction. A target
        # displaced by cents is a fractional position and uses the continuous
        # reference instead.
        if _is_effectively_zero(cents_offset) and _is_integral(physical):
            reference_type = SpatialReferenceType.IMAGINARY_SEMITONE
        else:
            reference_type = SpatialReferenceType.CONTINUOUS_POSITION

    return SpatialPosition(
        string_id=string.string_id,
        course_id=string.course_id,
        display_order=string.display_order,
        sounding_midi_note=sounding_midi_note,
        cents_offset=cents_offset,
        relative_semitone_position=relative,
        physical_semitone_position_from_nut=physical,
        physical_fret_number=physical_fret_number,
        reference_type=reference_type,
        normalized_position=normalized_position_for_semitones(physical),
        distance_from_nut_mm=distance_from_nut_mm(scale_length_mm, physical),
        # The contract binds open-string identity to the position *relative to the
        # capo*, not to the nut: with a capo the capo becomes the new nut, so a note
        # stopped at the capo is open in exactly this sense.
        is_open_string=relative == 0.0,
    )
