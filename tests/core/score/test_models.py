"""Canonical score document and revision contract invariants (DO-007A A2).

These assert that an invalid revision is unrepresentable, so neither the revision
service (A4) nor a hand-built test object can be quietly wrong.
"""

from __future__ import annotations

import dataclasses

import pytest

from conftest import (  # type: ignore[import-not-found]
    DOCUMENT_ID,
    T0,
    digest_for,
    make_event,
    make_revision,
    revision_id_for,
)
from master_all_strings.core.foundation import SpatialMappingError
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import (
    SUPPORTED_TICKS_PER_QUARTER,
    CanonicalScoreRevisionV1,
    ScoreDocumentV1,
)
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    ScoreSourceKind,
    SourceEventProvenanceV1,
)
from master_all_strings.core.score.tempo import (
    MICROSECONDS_PER_MINUTE,
    TempoChangeV1,
    tempo_from_bpm,
)


class TestScoreDocument:
    def test_valid_document_constructs(self, document: ScoreDocumentV1) -> None:
        assert document.document_id == DOCUMENT_ID
        assert document.revision_count == 1

    def test_blank_document_id_rejected(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(ScoreContractError, match="document_id"):
            dataclasses.replace(document, document_id="  ")

    def test_zero_revision_count_rejected(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(ScoreContractError, match="revision_count"):
            dataclasses.replace(document, revision_count=0)

    def test_non_utc_created_at_rejected(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(ScoreContractError, match="ISO-8601 UTC"):
            dataclasses.replace(document, created_at="2026-07-29T10:00:00+02:00")

    def test_document_carries_no_musical_content(self) -> None:
        # Duplicating revision content here would create a second place for the music
        # to live, and the two would drift.
        names = {f.name for f in dataclasses.fields(ScoreDocumentV1)}
        for forbidden in ("events", "tempo_changes", "meter_changes", "ticks_per_quarter"):
            assert forbidden not in names

    def test_document_is_frozen(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            document.document_id = "other"  # type: ignore[misc]

    def test_optional_metadata_accepted(self, document: ScoreDocumentV1) -> None:
        titled = dataclasses.replace(
            document, title="Etude in A", description="First take", external_reference="ext-1"
        )
        assert titled.title == "Etude in A"

    def test_blank_title_rejected(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(ScoreContractError, match="title"):
            dataclasses.replace(document, title="   ")

    def test_title_is_prose_not_an_identifier(self, document: ScoreDocumentV1) -> None:
        # A title was held to identifier rules, which forbade the inner formatting a
        # real one may carry. Nothing keys on a title and the digest excludes it, so
        # that was borrowed strictness with no invariant behind it.
        titled = dataclasses.replace(document, title="Étude  No. 1 — 2nd movement")
        assert titled.title == "Étude  No. 1 — 2nd movement"

    def test_external_reference_is_still_an_identifier(
        self, document: ScoreDocumentV1
    ) -> None:
        # Unlike a title, this is a key into another system, so surrounding whitespace
        # is a defect rather than formatting.
        with pytest.raises(ScoreContractError, match="external_reference"):
            dataclasses.replace(document, external_reference=" ext-1 ")

    def test_blank_description_rejected(self, document: ScoreDocumentV1) -> None:
        with pytest.raises(ScoreContractError, match="description"):
            dataclasses.replace(document, description="  ")

    def test_with_revision_advances(self, document: ScoreDocumentV1) -> None:
        advanced = document.with_revision(current_revision_id="rev-" + "a" * 24, revision_count=2)
        assert advanced.revision_count == 2
        assert document.revision_count == 1

    def test_with_revision_refuses_to_go_backwards(self, document: ScoreDocumentV1) -> None:
        # A document that could move backwards would let a stale write silently undo
        # an accepted revision.
        advanced = document.with_revision(current_revision_id="rev-" + "a" * 24, revision_count=3)
        with pytest.raises(ScoreContractError, match="must increase"):
            advanced.with_revision(current_revision_id="rev-" + "b" * 24, revision_count=2)

    def test_with_revision_refuses_to_stand_still(self, document: ScoreDocumentV1) -> None:
        # The other half of the same hole: repointing at a different revision without
        # advancing the count would leave the number disagreeing with the stored
        # history, and would describe adding a revision as if none had been added.
        advanced = document.with_revision(current_revision_id="rev-" + "a" * 24, revision_count=3)
        with pytest.raises(ScoreContractError, match="must increase"):
            advanced.with_revision(current_revision_id="rev-" + "b" * 24, revision_count=3)

    def test_with_revision_preserves_metadata(self, document: ScoreDocumentV1) -> None:
        titled = dataclasses.replace(document, title="Etude")
        assert titled.with_revision(
            current_revision_id="rev-" + "a" * 24, revision_count=2
        ).title == "Etude"


class TestRevisionIdentity:
    def test_valid_origin_revision_constructs(
        self, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        assert origin_revision.is_origin is True
        assert origin_revision.event_count == 2

    def test_revision_id_must_derive_from_the_digest(
        self, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        # A mismatch means one of the two was edited independently, which would break
        # every citation of this revision.
        with pytest.raises(ScoreContractError, match="derived from content_digest"):
            dataclasses.replace(origin_revision, revision_id="rev-" + "0" * 24)

    def test_short_digest_rejected(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        with pytest.raises(ScoreContractError, match="content_digest"):
            dataclasses.replace(origin_revision, content_digest="abc")

    def test_uppercase_digest_rejected(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        digest = digest_for("upper").upper()
        with pytest.raises(ScoreContractError, match="lowercase hex"):
            dataclasses.replace(
                origin_revision, content_digest=digest, revision_id=revision_id_for(digest)
            )

    def test_non_hex_digest_rejected(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        digest = "z" * 64
        with pytest.raises(ScoreContractError, match="lowercase hex"):
            dataclasses.replace(
                origin_revision, content_digest=digest, revision_id=revision_id_for(digest)
            )

    def test_revision_is_frozen(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            origin_revision.revision_number = 9  # type: ignore[misc]

    def test_events_are_a_tuple(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        assert isinstance(origin_revision.events, tuple)
        assert isinstance(origin_revision.tempo_changes, tuple)
        assert isinstance(origin_revision.meter_changes, tuple)

    def test_list_events_rejected(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        with pytest.raises(ScoreContractError, match="must be a tuple"):
            dataclasses.replace(origin_revision, events=[make_event(0)])  # type: ignore[arg-type]

    def test_errors_are_catchable_as_the_repository_base(
        self, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        with pytest.raises(SpatialMappingError):
            dataclasses.replace(origin_revision, content_digest="short")
        assert issubclass(ScoreContractError, SpatialMappingError)


class TestRevisionEvents:
    def test_duplicate_event_ids_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="event_id"):
            make_revision(events=(make_event(0), make_event(0, start_tick=480)))

    def test_non_event_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="MusicalEvent"):
            make_revision(events=("not-an-event",))  # type: ignore[arg-type]

    def test_empty_event_collection_permitted(self) -> None:
        # An empty score is a legitimate state -- a document created before anything is
        # played. The tempo and meter maps still have to exist.
        assert make_revision(events=()).event_count == 0

    @pytest.mark.parametrize("ppq", list(SUPPORTED_TICKS_PER_QUARTER))
    def test_supported_ticks_per_quarter_accepted(self, ppq: int) -> None:
        assert make_revision(ticks_per_quarter=ppq).ticks_per_quarter == ppq

    def test_unsupported_ticks_per_quarter_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="ticks_per_quarter"):
            make_revision(ticks_per_quarter=1000)


class TestTempoMap:
    def test_tempo_required(self) -> None:
        with pytest.raises(ScoreContractError, match="tempo at tick 0"):
            make_revision(tempo_changes=())

    def test_first_tempo_must_be_at_tick_zero(self) -> None:
        with pytest.raises(ScoreContractError, match="first tempo change must be at tick 0"):
            make_revision(tempo_changes=(tempo_from_bpm(120.0, tick=480),))

    def test_duplicate_tempo_ticks_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="tempo_changes ticks must strictly increase"):
            make_revision(tempo_changes=(tempo_from_bpm(120.0), tempo_from_bpm(90.0)))

    def test_decreasing_tempo_ticks_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="strictly increase"):
            make_revision(
                tempo_changes=(
                    tempo_from_bpm(120.0),
                    tempo_from_bpm(90.0, tick=960),
                    tempo_from_bpm(80.0, tick=480),
                )
            )

    def test_increasing_tempo_ticks_accepted(self) -> None:
        revision = make_revision(
            tempo_changes=(tempo_from_bpm(120.0), tempo_from_bpm(90.0, tick=960))
        )
        assert len(revision.tempo_changes) == 2

    def test_microseconds_per_quarter_is_authoritative(self) -> None:
        # BPM as a stored float would make two tempo maps a musician considers
        # identical produce different digests.
        names = {f.name for f in dataclasses.fields(TempoChangeV1)}
        assert "microseconds_per_quarter" in names
        assert "beats_per_minute" not in names

    def test_bpm_is_derived(self) -> None:
        assert tempo_from_bpm(120.0).beats_per_minute == pytest.approx(120.0)
        assert tempo_from_bpm(120.0).microseconds_per_quarter == 500_000

    def test_zero_microseconds_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="microseconds_per_quarter"):
            TempoChangeV1(
                schema_version=TempoChangeV1.SCHEMA_VERSION, tick=0, microseconds_per_quarter=0
            )

    def test_negative_tempo_tick_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="tick"):
            TempoChangeV1(
                schema_version=TempoChangeV1.SCHEMA_VERSION,
                tick=-1,
                microseconds_per_quarter=500_000,
            )

    def test_zero_bpm_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="beats_per_minute"):
            tempo_from_bpm(0.0)

    def test_non_numeric_bpm_rejected(self) -> None:
        # ScoreContractError, not TypeError. One bad argument should not need a caller
        # to catch two exception families, and every other validator in the package
        # raises the contract error for a wrong type.
        with pytest.raises(ScoreContractError, match="beats_per_minute"):
            tempo_from_bpm("fast")  # type: ignore[arg-type]

    def test_bool_bpm_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="beats_per_minute"):
            tempo_from_bpm(True)  # type: ignore[arg-type]

    def test_non_finite_bpm_rejected(self) -> None:
        for value in (float("nan"), float("inf")):
            with pytest.raises(ScoreContractError, match="beats_per_minute"):
                tempo_from_bpm(value)

    def test_a_fraction_bpm_is_accepted_and_exact(self) -> None:
        # The escape hatch for callers that need decimal semantics: a float BPM is read
        # as the binary double it actually is, which is reproducible but is not the
        # decimal that was typed. Fraction("120.1") is the decimal, exactly.
        from fractions import Fraction

        assert tempo_from_bpm(Fraction(120)).microseconds_per_quarter == 500_000
        assert tempo_from_bpm(Fraction("120.1")).microseconds_per_quarter == (
            tempo_from_bpm(120.1).microseconds_per_quarter
        )

    def test_bpm_conversion_rounds_half_away_from_zero(self) -> None:
        # The tempo map is inside the content digest and the Performance seam builds
        # every request through this function, so the tie rule here is identity-
        # affecting. Python's round() is banker's: it would answer 333_332 for a value
        # landing exactly on .5 with an even floor, diverging from the documented rule
        # any reimplementation would follow.
        bpm = 120_000_000 / 666_665  # 60_000_000 / bpm == 333_332.5 exactly
        assert tempo_from_bpm(bpm).microseconds_per_quarter == 333_333
        assert round(60_000_000 / bpm) == 333_332

    def test_tempo_at_tick_resolves(self) -> None:
        revision = make_revision(
            tempo_changes=(tempo_from_bpm(120.0), tempo_from_bpm(60.0, tick=960))
        )
        assert revision.tempo_at_tick(0).microseconds_per_quarter == 500_000
        assert revision.tempo_at_tick(959).microseconds_per_quarter == 500_000
        assert revision.tempo_at_tick(960).microseconds_per_quarter == MICROSECONDS_PER_MINUTE // 60
        assert revision.tempo_at_tick(5000).microseconds_per_quarter == 1_000_000


class TestMeterMap:
    def test_meter_required(self) -> None:
        with pytest.raises(ScoreContractError, match="meter at tick 0"):
            make_revision(meter_changes=())

    def test_first_meter_must_be_at_tick_zero(self) -> None:
        late = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=480, numerator=4, denominator=4
        )
        with pytest.raises(ScoreContractError, match="first meter change must be at tick 0"):
            make_revision(meter_changes=(late,))

    def test_duplicate_meter_ticks_rejected(self) -> None:
        first = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
        )
        second = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=3, denominator=4
        )
        with pytest.raises(ScoreContractError, match="meter_changes ticks must strictly increase"):
            make_revision(meter_changes=(first, second))

    @pytest.mark.parametrize("denominator", [1, 2, 4, 8, 16, 32, 64])
    def test_supported_denominators_accepted(self, denominator: int) -> None:
        assert (
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION,
                tick=0,
                numerator=4,
                denominator=denominator,
            ).denominator
            == denominator
        )

    @pytest.mark.parametrize("denominator", [0, 3, 5, 6, 7, 9, 128])
    def test_non_power_of_two_denominator_rejected(self, denominator: int) -> None:
        with pytest.raises(ScoreContractError, match="denominator"):
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION,
                tick=0,
                numerator=4,
                denominator=denominator,
            )

    def test_zero_numerator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="numerator"):
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=0, denominator=4
            )

    def test_oversized_numerator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="numerator"):
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=99, denominator=4
            )

    def test_bool_numerator_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="numerator"):
            MeterChangeV1(
                schema_version=MeterChangeV1.SCHEMA_VERSION,
                tick=0,
                numerator=True,  # type: ignore[arg-type]
                denominator=4,
            )

    def test_ticks_per_measure(self) -> None:
        four_four = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
        )
        three_four = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=3, denominator=4
        )
        six_eight = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=6, denominator=8
        )
        assert four_four.ticks_per_measure(960) == 3840
        assert three_four.ticks_per_measure(960) == 2880
        assert six_eight.ticks_per_measure(960) == 2880

    def test_meter_at_tick_resolves(self) -> None:
        first = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
        )
        second = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=3840, numerator=3, denominator=4
        )
        revision = make_revision(meter_changes=(first, second))
        assert revision.meter_at_tick(0).numerator == 4
        assert revision.meter_at_tick(3839).numerator == 4
        assert revision.meter_at_tick(3840).numerator == 3
        assert revision.meter_at_tick(99999).numerator == 3


class TestProvenanceIsRequired:
    def test_provenance_is_not_optional(self) -> None:
        # A revision that cannot say where it came from is unauditable, whatever its
        # source was.
        fields = {f.name: f for f in dataclasses.fields(CanonicalScoreRevisionV1)}
        assert fields["provenance"].default is dataclasses.MISSING
        assert fields["provenance"].default_factory is dataclasses.MISSING

    def test_non_provenance_rejected(self, origin_revision: CanonicalScoreRevisionV1) -> None:
        with pytest.raises(ScoreContractError, match="RevisionProvenanceV1"):
            dataclasses.replace(origin_revision, provenance="none")  # type: ignore[arg-type]

    def test_capture_sourced_revision_requires_a_source_reference(self) -> None:
        with pytest.raises(ScoreContractError, match="source_reference"):
            RevisionProvenanceV1(
                schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
                source_kind=ScoreSourceKind.PERFORMANCE_CAPTURE,
                policy_version="DIRECT_EVENT_IMPORT_V1",
            )

    def test_capture_sourced_revision_with_a_reference_is_valid(self) -> None:
        provenance = RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.PERFORMANCE_CAPTURE,
            policy_version="DIRECT_EVENT_IMPORT_V1",
            source_reference="capture-1",
        )
        assert provenance.source_reference == "capture-1"

    def test_manual_revision_needs_no_source_reference(self) -> None:
        provenance = RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
            policy_version="manual-1",
        )
        assert provenance.source_reference is None

    def test_duplicate_event_provenance_rejected(self) -> None:
        entry = SourceEventProvenanceV1(
            schema_version=SourceEventProvenanceV1.SCHEMA_VERSION,
            canonical_event_id="evt-0000",
        )
        with pytest.raises(ScoreContractError, match="canonical_event_id"):
            RevisionProvenanceV1(
                schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
                source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
                policy_version="test-1",
                event_provenance=(entry, entry),
            )

    def test_for_event_lookup(self) -> None:
        entry = SourceEventProvenanceV1(
            schema_version=SourceEventProvenanceV1.SCHEMA_VERSION,
            canonical_event_id="evt-0000",
            source_channel=3,
            observed_source_string=2,
        )
        provenance = RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
            policy_version="test-1",
            event_provenance=(entry,),
        )
        assert provenance.for_event("evt-0000") is entry
        assert provenance.for_event("evt-9999") is None

    def test_bad_source_kind_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="ScoreSourceKind"):
            RevisionProvenanceV1(
                schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
                source_kind="capture",  # type: ignore[arg-type]
                policy_version="test-1",
            )

    def test_created_at_is_not_content(self) -> None:
        # A3 formalizes this in digest tests; A2 records the intent by proving two
        # revisions differing only in created_at keep the same digest and id.
        early = make_revision(created_at=T0)
        late = make_revision(created_at="2026-12-31T23:59:59Z")
        assert early.content_digest == late.content_digest
        assert early.revision_id == late.revision_id
