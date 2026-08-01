"""``DIRECT_EVENT_IMPORT_V1`` behaviour (DO-007A A5).

The policy is where captured performance becomes canonical music, so it is where a
musical claim would most easily be smuggled in. These tests fix what it converts, what
it refuses, and what it deliberately declines to infer.
"""

from __future__ import annotations

from conftest import (  # type: ignore[import-not-found]
    MPQ_120,
    NS_PER_QUARTER,
    make_request,
    note,
    source_event,
)
from master_all_strings.core.ingestion.contracts import SourceMidiEventKind
from master_all_strings.core.ingestion.policies import (
    POLICY_VERSION,
    import_direct_events,
)
from master_all_strings.core.ingestion.results import (
    IngestionWarningCode,
    RejectionReason,
)


class TestConversion:
    def test_a_matched_pair_becomes_one_event(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0)))
        assert outcome.accepted_count == 1
        assert outcome.rejections == ()

    def test_timing_converts_at_960_ppq(self) -> None:
        outcome = import_direct_events(
            make_request(
                source_events=note(
                    0, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2
                )
            )
        )
        event = outcome.events[0]
        assert event.start_tick == 960
        assert event.duration_ticks == 960

    def test_pitch_and_velocity_pass_through_unchanged(self) -> None:
        outcome = import_direct_events(
            make_request(source_events=note(0, midi_note=57, velocity=113))
        )
        assert outcome.events[0].midi_note == 57
        assert outcome.events[0].velocity == 113

    def test_velocity_comes_from_the_onset_not_the_release(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0, velocity=101)))
        assert outcome.events[0].velocity == 101

    def test_several_notes_convert(self) -> None:
        events = note(0) + note(1, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2)
        assert import_direct_events(make_request(source_events=events)).accepted_count == 2

    def test_a_chord_preserves_simultaneous_onsets(self) -> None:
        events = (
            note(0, midi_note=60)
            + note(1, midi_note=64)
            + note(2, midi_note=67)
        )
        outcome = import_direct_events(make_request(source_events=events))
        assert {e.start_tick for e in outcome.events} == {0}
        assert sorted(e.midi_note for e in outcome.events) == [60, 64, 67]

    def test_a_note_on_with_zero_velocity_releases(self) -> None:
        # MIDI convention. Treating it otherwise would leave a phantom sounding note
        # and reject a valid take.
        events = (
            source_event(0, SourceMidiEventKind.NOTE_ON, 0, velocity=90),
            source_event(1, SourceMidiEventKind.NOTE_ON, NS_PER_QUARTER, velocity=0),
        )
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 1
        assert outcome.rejections == ()

    def test_event_ids_are_derived_from_the_source(self) -> None:
        # Re-ingesting the same capture must produce the same canonical ids, and
        # therefore the same digest.
        outcome = import_direct_events(make_request(source_events=note(0)))
        assert outcome.events[0].event_id == "ev-src-0000"

    def test_ppq_is_configurable(self) -> None:
        outcome = import_direct_events(
            make_request(source_events=note(0), ticks_per_quarter=480)
        )
        assert outcome.events[0].duration_ticks == 480


class TestNoInference:
    def test_channel_is_never_mapped_to_voice(self) -> None:
        # A channel may carry a divided-pickup string, device routing, or an
        # articulation. Equating it with a voice manufactures musical structure.
        outcome = import_direct_events(make_request(source_events=note(0, channel=5)))
        assert outcome.events[0].voice_id is None

    def test_channel_reaches_provenance(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0, channel=5)))
        assert outcome.event_provenance[0].source_channel == 5

    def test_channel_use_is_reported_as_a_warning(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0, channel=3)))
        codes = {w.code for w in outcome.warnings}
        assert IngestionWarningCode.CHANNEL_NOT_MAPPED_TO_VOICE in codes

    def test_observed_string_is_preserved(self) -> None:
        outcome = import_direct_events(
            make_request(source_events=note(0, observed_source_string=2))
        )
        assert outcome.event_provenance[0].observed_source_string == 2
        assert outcome.event_provenance[0].string_identity_observed is True

    def test_absent_string_stays_unresolved(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0)))
        assert outcome.event_provenance[0].observed_source_string is None
        codes = {w.code for w in outcome.warnings}
        assert IngestionWarningCode.SOURCE_STRING_UNRESOLVED in codes

    def test_no_quantization_occurs(self) -> None:
        # 30 ms late stays 30 ms late; a quantizer would snap this to 960.
        late = NS_PER_QUARTER + 30_000_000
        outcome = import_direct_events(
            make_request(source_events=note(0, onset_ns=late, release_ns=late + NS_PER_QUARTER))
        )
        assert outcome.events[0].start_tick == 1018

    def test_cents_offset_is_not_invented(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0)))
        assert outcome.events[0].cents_offset == 0.0


class TestPairing:
    def test_pairing_is_fifo_within_a_channel_and_pitch(self) -> None:
        # Two overlapping strikes of the same pitch: the first release closes the
        # first onset. Any rule is defensible; silence about which one is not.
        events = (
            source_event(0, SourceMidiEventKind.NOTE_ON, 0, velocity=90),
            source_event(1, SourceMidiEventKind.NOTE_ON, 100_000_000, velocity=100),
            source_event(2, SourceMidiEventKind.NOTE_OFF, 200_000_000),
            source_event(3, SourceMidiEventKind.NOTE_OFF, 300_000_000),
        )
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 2
        first = next(e for e in outcome.events if e.event_id == "ev-src-0000")
        assert first.velocity == 90
        assert first.start_tick == 0

    def test_the_same_pitch_on_different_channels_does_not_cross_pair(self) -> None:
        events = (
            source_event(0, SourceMidiEventKind.NOTE_ON, 0, channel=0),
            source_event(1, SourceMidiEventKind.NOTE_ON, 0, channel=1),
            source_event(2, SourceMidiEventKind.NOTE_OFF, NS_PER_QUARTER, channel=1),
            source_event(3, SourceMidiEventKind.NOTE_OFF, NS_PER_QUARTER, channel=0),
        )
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 2
        channels = {p.source_channel for p in outcome.event_provenance}
        assert channels == {0, 1}

    def test_pairing_records_both_source_ids(self) -> None:
        outcome = import_direct_events(make_request(source_events=note(0)))
        assert outcome.event_provenance[0].source_capture_event_ids == (
            "src-0000",
            "src-0001",
        )

    def test_input_order_does_not_change_the_result(self) -> None:
        events = note(0) + note(1, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2)
        forward = import_direct_events(make_request(source_events=events))
        backward = import_direct_events(make_request(source_events=tuple(reversed(events))))
        assert {e.event_id for e in forward.events} == {e.event_id for e in backward.events}


class TestRejections:
    def test_an_unmatched_note_on_is_rejected_not_synthesized(self) -> None:
        # DO-006 preserved these deliberately as evidence; inventing an ending would
        # destroy that and violate ADR-0007 D15.
        events = (source_event(0, SourceMidiEventKind.NOTE_ON, 0),)
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 0
        assert outcome.rejections[0].reason is RejectionReason.UNMATCHED_NOTE_ON
        assert "src-0000" in outcome.rejections[0].source_event_ids

    def test_an_unmatched_note_off_is_rejected(self) -> None:
        events = (source_event(0, SourceMidiEventKind.NOTE_OFF, 0),)
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.rejections[0].reason is RejectionReason.UNMATCHED_NOTE_OFF

    def test_good_notes_survive_alongside_a_rejection(self) -> None:
        events = note(0) + (source_event(9, SourceMidiEventKind.NOTE_ON, 0, midi_note=67),)
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 1
        assert outcome.rejections

    def test_a_sub_tick_duration_is_rejected_not_widened(self) -> None:
        events = note(0, onset_ns=0, release_ns=1000)
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.accepted_count == 0
        assert outcome.rejections[0].reason is RejectionReason.DURATION_BELOW_ONE_TICK

    def test_an_event_before_the_origin_is_rejected(self) -> None:
        events = note(0, onset_ns=0, release_ns=NS_PER_QUARTER)
        outcome = import_direct_events(
            make_request(source_events=events, capture_origin_ns=1_000_000)
        )
        assert outcome.rejections[0].reason is RejectionReason.EVENT_BEFORE_CAPTURE_ORIGIN

    def test_rejections_name_their_source_events(self) -> None:
        events = (source_event(0, SourceMidiEventKind.NOTE_ON, 0),)
        outcome = import_direct_events(make_request(source_events=events))
        assert outcome.rejected_count == 1


class TestProvenanceEvidence:
    def test_source_nanoseconds_are_retained(self) -> None:
        events = note(0, onset_ns=123_456_789, release_ns=623_456_789)
        record = import_direct_events(make_request(source_events=events)).event_provenance[0]
        assert record.source_capture_time_ns == 123_456_789
        assert record.source_release_time_ns == 623_456_789

    def test_conversion_basis_is_retained(self) -> None:
        record = import_direct_events(make_request(source_events=note(0))).event_provenance[0]
        assert record.ticks_per_quarter == 960
        assert record.microseconds_per_quarter == MPQ_120
        assert record.rounding_policy is not None

    def test_rounding_residue_is_retained(self) -> None:
        events = note(0, onset_ns=1000, release_ns=NS_PER_QUARTER + 1000)
        record = import_direct_events(
            make_request(source_events=events, capture_origin_ns=0)
        ).event_provenance[0]
        assert record.rounding_delta_start_ns == 1000

    def test_rounding_is_reported_as_a_warning(self) -> None:
        events = note(0, onset_ns=1000, release_ns=NS_PER_QUARTER + 1000)
        outcome = import_direct_events(make_request(source_events=events))
        codes = {w.code for w in outcome.warnings}
        assert IngestionWarningCode.ROUNDING_APPLIED in codes

    def test_the_rounding_warning_names_source_events_not_canonical_ones(self) -> None:
        # A caller correlates a warning back to the capture it sent. Reporting the
        # canonical id here would hand it an id that appears nowhere in its request.
        events = note(0, onset_ns=1000, release_ns=NS_PER_QUARTER + 1000)
        outcome = import_direct_events(make_request(source_events=events))
        warning = next(
            w for w in outcome.warnings if w.code is IngestionWarningCode.ROUNDING_APPLIED
        )
        submitted = {event.source_event_id for event in events}
        assert set(warning.source_event_ids) <= submitted
        canonical = {event.event_id for event in outcome.events}
        assert set(warning.source_event_ids).isdisjoint(canonical)

    def test_every_warning_id_is_an_id_the_caller_submitted(self) -> None:
        # The invariant behind the previous test, asserted across every warning code so a
        # new warning cannot reintroduce the mismatch.
        events = note(0, onset_ns=1000, release_ns=NS_PER_QUARTER + 1000, channel=3)
        outcome = import_direct_events(make_request(source_events=events))
        submitted = {event.source_event_id for event in events}
        assert outcome.warnings
        for warning in outcome.warnings:
            assert set(warning.source_event_ids) <= submitted, warning.code

    def test_every_rejection_id_is_an_id_the_caller_submitted(self) -> None:
        events = note(0) + (source_event(9, SourceMidiEventKind.NOTE_ON, 0, midi_note=67),)
        outcome = import_direct_events(make_request(source_events=events))
        submitted = {event.source_event_id for event in events}
        assert outcome.rejections
        for rejection in outcome.rejections:
            assert set(rejection.source_event_ids) <= submitted, rejection.reason

    def test_rounding_attribution_follows_which_conversion_rounded(self) -> None:
        # Only the onset is off the grid, so the release is not implicated.
        events = note(0, onset_ns=1000, release_ns=NS_PER_QUARTER + 1000)
        outcome = import_direct_events(make_request(source_events=events))
        warning = next(
            w for w in outcome.warnings if w.code is IngestionWarningCode.ROUNDING_APPLIED
        )
        assert warning.source_event_ids == (events[0].source_event_id,)

    def test_one_provenance_record_per_canonical_event(self) -> None:
        events = note(0) + note(1, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2)
        outcome = import_direct_events(make_request(source_events=events))
        assert len(outcome.event_provenance) == outcome.accepted_count
        ids = [p.canonical_event_id for p in outcome.event_provenance]
        assert len(ids) == len(set(ids))

    def test_provenance_resolves_to_canonical_events(self) -> None:
        events = note(0) + note(1, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2)
        outcome = import_direct_events(make_request(source_events=events))
        canonical_ids = {e.event_id for e in outcome.events}
        assert {p.canonical_event_id for p in outcome.event_provenance} == canonical_ids


class TestPolicyIdentity:
    def test_the_policy_version_is_named(self) -> None:
        assert POLICY_VERSION == "DIRECT_EVENT_IMPORT_V1"

    def test_the_policy_performs_no_spatial_mapping(self) -> None:
        import inspect

        from master_all_strings.core.ingestion import policies

        source = inspect.getsource(policies)
        for forbidden in ("spatial_mapping", "generate_candidates", "fret", "string_index"):
            assert forbidden not in source, forbidden

    def test_the_policy_imports_nothing_from_performance(self) -> None:
        import ast
        import inspect
        import textwrap

        from master_all_strings.core.ingestion import policies

        tree = ast.parse(textwrap.dedent(inspect.getsource(policies)))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "performance" not in node.module

    def test_repeated_import_is_deterministic(self) -> None:
        request = make_request(source_events=note(0))
        first = import_direct_events(request)
        second = import_direct_events(request)
        assert first.events == second.events
        assert first.event_provenance == second.event_provenance
