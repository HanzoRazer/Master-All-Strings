"""Revision digest and derived identity (DO-007A A3).

The digest is what makes a revision citable. These tests fix two things: that identity
follows content, and that the inclusion policy is exactly what ADR-0008 says rather than
whatever the implementation happens to hash.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from conftest import make_event, make_revision  # type: ignore[import-not-found]
from master_all_strings.core.score.digest import (
    CONTENT_SERIALIZATION_VERSION,
    DIGEST_DERIVED_FIELDS,
    DIGEST_EXCLUDED_DOCUMENT_FIELDS,
    DIGEST_EXCLUDED_FIELDS,
    DIGEST_INCLUDED_FIELDS,
    compute_revision_digest,
    derive_revision_id,
    serialize_revision_content,
    verify_revision_digest,
)
from master_all_strings.core.score.errors import (
    DIGEST_LENGTH,
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
    ScoreContractError,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.score.tempo import tempo_from_bpm

METER_4_4 = MeterChangeV1(
    schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
)
BASE = {
    "document_id": "score-0001",
    "revision_number": 1,
    "parent_revision_id": None,
    "ticks_per_quarter": 960,
    "tempo_changes": (tempo_from_bpm(120.0),),
    "meter_changes": (METER_4_4,),
}


def digest(**overrides: object) -> str:
    payload = {**BASE, "events": (make_event(0),)}
    payload.update(overrides)
    return compute_revision_digest(**payload)  # type: ignore[arg-type]


class TestDigestShape:
    def test_digest_is_lowercase_sha256_hex(self) -> None:
        value = digest()
        assert len(value) == DIGEST_LENGTH
        assert value == value.lower()
        assert all(c in "0123456789abcdef" for c in value)

    def test_digest_is_deterministic(self) -> None:
        assert digest() == digest()

    def test_serialization_pins_a_version(self) -> None:
        # Bumping it changes every revision id, so it must be a deliberate act rather
        # than an accident of refactoring.
        serialized = serialize_revision_content(**BASE, events=(make_event(0),))  # type: ignore[arg-type]
        assert serialized.startswith(f'["{CONTENT_SERIALIZATION_VERSION}"')

    def test_serialization_is_ascii_and_compact(self) -> None:
        serialized = serialize_revision_content(**BASE, events=(make_event(0),))  # type: ignore[arg-type]
        assert ", " not in serialized
        assert serialized.isascii()


class TestContentChangesTheDigest:
    def test_changed_pitch_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0, midi_note=60),)) != digest(
            events=(make_event(0, midi_note=61),)
        )

    def test_changed_start_tick_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0, start_tick=0),)) != digest(
            events=(make_event(0, start_tick=1),)
        )

    def test_changed_duration_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0, duration_ticks=480),)) != digest(
            events=(make_event(0, duration_ticks=481),)
        )

    def test_changed_velocity_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0, velocity=90),)) != digest(
            events=(make_event(0, velocity=91),)
        )

    def test_changed_voice_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0, voice_id=None),)) != digest(
            events=(make_event(0, voice_id="alto"),)
        )

    def test_changed_cents_offset_changes_the_digest(self) -> None:
        base = make_event(0)
        detuned = dataclasses.replace(base, cents_offset=25.0)
        assert digest(events=(base,)) != digest(events=(detuned,))

    def test_changed_event_id_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0),)) != digest(events=(make_event(1),))

    def test_changed_tempo_changes_the_digest(self) -> None:
        assert digest(tempo_changes=(tempo_from_bpm(120.0),)) != digest(
            tempo_changes=(tempo_from_bpm(90.0),)
        )

    def test_changed_meter_changes_the_digest(self) -> None:
        three_four = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=3, denominator=4
        )
        assert digest(meter_changes=(METER_4_4,)) != digest(meter_changes=(three_four,))

    def test_changed_ppq_changes_the_digest(self) -> None:
        assert digest(ticks_per_quarter=960) != digest(ticks_per_quarter=480)

    def test_added_event_changes_the_digest(self) -> None:
        assert digest(events=(make_event(0),)) != digest(
            events=(make_event(0), make_event(1, start_tick=480))
        )


class TestLineageIsInsideTheDigest:
    def test_document_id_changes_the_digest(self) -> None:
        # Without this, identical music in two documents would share a revision id and
        # get_revision would be ambiguous.
        assert digest(document_id="score-0001") != digest(document_id="score-0002")

    def test_revision_number_changes_the_digest(self) -> None:
        # Reverting a document to earlier content must not reproduce the original
        # revision's id while carrying a different number.
        assert digest(revision_number=1, parent_revision_id=None) != digest(
            revision_number=2, parent_revision_id="rev-" + "a" * 24
        )

    def test_parent_changes_the_digest(self) -> None:
        left = digest(revision_number=2, parent_revision_id="rev-" + "a" * 24)
        right = digest(revision_number=2, parent_revision_id="rev-" + "b" * 24)
        assert left != right

    def test_the_included_field_list_is_the_documented_one(self) -> None:
        assert DIGEST_INCLUDED_FIELDS == (
            "document_id",
            "revision_number",
            "parent_revision_id",
            "ticks_per_quarter",
            "events",
            "tempo_changes",
            "meter_changes",
        )


class TestExclusionsDoNotChangeTheDigest:
    def test_created_at_is_excluded(self) -> None:
        # The same music ingested twice must produce the same identity.
        early = make_revision(created_at="2026-07-29T10:00:00Z")
        late = make_revision(created_at="2027-01-01T00:00:00Z")
        assert early.content_digest == late.content_digest

    def test_provenance_is_excluded(self) -> None:
        # Provenance is evidence about the derivation, not the content: two revisions
        # of identical music differing only in rounding residue are the same music.
        from master_all_strings.core.score.provenance import (
            RevisionProvenanceV1,
            ScoreSourceKind,
        )

        other = RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.IMPORT,
            policy_version="other-9",
        )
        assert make_revision().content_digest == make_revision(provenance=other).content_digest

    def test_the_excluded_field_list_is_the_documented_one(self) -> None:
        assert DIGEST_EXCLUDED_FIELDS == ("created_at", "provenance")

    def test_document_metadata_is_excluded(self) -> None:
        assert DIGEST_EXCLUDED_DOCUMENT_FIELDS == ("title", "description")


class TestFieldPolicyCoverage:
    """Every revision field must have a recorded digest decision.

    The failure this prevents is silent. Adding a field to ``CanonicalScoreRevisionV1``
    without touching ``digest`` does not raise, does not change any existing id, and
    leaves the new field simply outside identity — so two revisions differing only in it
    would share one ``revision_id`` and one of them would be unreachable. Nothing else
    in the suite would notice, because every existing test asserts on fields that were
    already decided. This test fails on the *next* field instead.
    """

    def test_every_revision_field_is_included_excluded_or_derived(self) -> None:
        decided = set(DIGEST_INCLUDED_FIELDS) | set(DIGEST_EXCLUDED_FIELDS) | set(
            DIGEST_DERIVED_FIELDS
        )
        actual = {f.name for f in dataclasses.fields(CanonicalScoreRevisionV1)}
        assert actual - decided == set(), (
            "a revision field has no recorded digest decision; add it to "
            "DIGEST_INCLUDED_FIELDS, DIGEST_EXCLUDED_FIELDS, or DIGEST_DERIVED_FIELDS "
            "and say why in the module docstring"
        )
        assert decided - actual == set(), "the digest policy names a field that no longer exists"

    def test_the_included_fields_are_what_the_digest_actually_reads(self) -> None:
        # The list is only worth asserting if it matches the function's real signature.
        parameters = set(inspect.signature(compute_revision_digest).parameters)
        assert parameters == set(DIGEST_INCLUDED_FIELDS)


class TestOrderIndependence:
    def test_reordered_events_yield_the_same_digest(self) -> None:
        forward = (make_event(0), make_event(1, start_tick=480), make_event(2, start_tick=960))
        assert digest(events=forward) == digest(events=tuple(reversed(forward)))

    def test_reordered_tempo_changes_yield_the_same_digest(self) -> None:
        changes = (tempo_from_bpm(120.0), tempo_from_bpm(90.0, tick=960))
        assert digest(tempo_changes=changes) == digest(tempo_changes=tuple(reversed(changes)))

    def test_reordered_meter_changes_yield_the_same_digest(self) -> None:
        second = MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION, tick=3840, numerator=3, denominator=4
        )
        changes = (METER_4_4, second)
        assert digest(meter_changes=changes) == digest(meter_changes=tuple(reversed(changes)))

    def test_a_reordered_chord_yields_the_same_digest(self) -> None:
        chord = tuple(make_event(i, midi_note=60 + i * 4) for i in range(3))
        assert digest(events=chord) == digest(events=tuple(reversed(chord)))


class TestDerivedRevisionId:
    def test_id_is_the_prefixed_digest(self) -> None:
        value = digest()
        assert derive_revision_id(value) == REVISION_ID_PREFIX + value[:REVISION_ID_DIGEST_PREFIX]

    def test_id_length_is_stable(self) -> None:
        assert len(derive_revision_id(digest())) == len(REVISION_ID_PREFIX) + 24

    def test_the_full_digest_is_recoverable_from_the_revision(self) -> None:
        # The public id is shortened; the revision always stores the whole digest.
        revision = make_revision()
        assert len(revision.content_digest) == DIGEST_LENGTH
        assert revision.revision_id.endswith(
            revision.content_digest[:REVISION_ID_DIGEST_PREFIX]
        )

    def test_id_prefix_maps_back_to_its_digest(self) -> None:
        value = digest()
        assert derive_revision_id(value).removeprefix(REVISION_ID_PREFIX) == value[:24]

    def test_distinct_content_yields_distinct_ids(self) -> None:
        # A prefix collision check over a realistic population: 24 hex characters is
        # 96 bits, so any collision here would indicate a derivation defect.
        ids = {
            derive_revision_id(digest(events=(make_event(i, midi_note=40 + i % 60),)))
            for i in range(500)
        }
        assert len(ids) == 500

    def test_short_digest_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="content_digest"):
            derive_revision_id("abc")

    def test_uppercase_digest_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="lowercase hex"):
            derive_revision_id(digest().upper())


class TestVerification:
    def test_a_consistent_revision_verifies(self) -> None:
        revision = make_revision(events=(make_event(0),), digest_label="verify")
        # The fixture digest is a stand-in, so recompute a real one first.
        real = compute_revision_digest(
            document_id=revision.document_id,
            revision_number=revision.revision_number,
            parent_revision_id=revision.parent_revision_id,
            ticks_per_quarter=revision.ticks_per_quarter,
            events=revision.events,
            tempo_changes=revision.tempo_changes,
            meter_changes=revision.meter_changes,
        )
        consistent = dataclasses.replace(
            revision, content_digest=real, revision_id=derive_revision_id(real)
        )
        assert verify_revision_digest(consistent) is True

    def test_a_tampered_revision_fails_verification(self) -> None:
        revision = make_revision(events=(make_event(0),), digest_label="tamper")
        assert verify_revision_digest(revision) is False

    def test_malformed_input_returns_false_rather_than_raising(self) -> None:
        # A corrupt record is a verification failure, not a programming error at the
        # call site.
        class Broken:
            document_id = ""

        assert verify_revision_digest(Broken()) is False  # type: ignore[arg-type]

    def test_blank_document_id_rejected_by_serialization(self) -> None:
        with pytest.raises(ScoreContractError, match="document_id"):
            serialize_revision_content(**{**BASE, "document_id": "  "}, events=())  # type: ignore[arg-type]
