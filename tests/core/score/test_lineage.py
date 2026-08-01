"""Revision lineage invariants (DO-007A A2).

Lineage is what makes a revision history trustworthy rather than a bag of snapshots. A
gap in the numbering means a revision was lost; a parent from another document means
two works have been spliced. Both are refused at construction.

Cross-document and cross-revision resolution — that a parent actually exists, and that
a document's current revision belongs to it — needs more than one object in hand and is
the revision service's job in A4. What is enforced here is everything visible from a
single revision.
"""

from __future__ import annotations

import dataclasses

import pytest

from conftest import DOCUMENT_ID, make_event, make_revision  # type: ignore[import-not-found]
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.models import (
    FIRST_REVISION_NUMBER,
    CanonicalScoreRevisionV1,
)


class TestOriginRevision:
    def test_revision_one_has_no_parent(
        self, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        assert origin_revision.revision_number == FIRST_REVISION_NUMBER
        assert origin_revision.parent_revision_id is None
        assert origin_revision.is_origin is True

    def test_revision_one_with_a_parent_is_rejected(self) -> None:
        # An origin with a parent claims a history that does not exist.
        with pytest.raises(ScoreContractError, match="revision 1 is the origin"):
            make_revision(revision_number=1, parent_revision_id="rev-" + "a" * 24)


class TestChildRevisions:
    def test_revision_two_requires_a_parent(self) -> None:
        with pytest.raises(ScoreContractError, match="requires a parent_revision_id"):
            make_revision(revision_number=2, parent_revision_id=None)

    def test_revision_two_with_a_parent_is_valid(
        self, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        child = make_revision(
            revision_number=2,
            parent_revision_id=origin_revision.revision_id,
            digest_label="child",
        )
        assert child.parent_revision_id == origin_revision.revision_id
        assert child.is_origin is False

    @pytest.mark.parametrize("number", [2, 3, 17, 999])
    def test_any_later_revision_requires_a_parent(self, number: int) -> None:
        with pytest.raises(ScoreContractError, match="requires a parent_revision_id"):
            make_revision(revision_number=number, parent_revision_id=None)

    def test_a_revision_cannot_be_its_own_parent(self) -> None:
        revision = make_revision(
            revision_number=2, parent_revision_id="rev-" + "a" * 24, digest_label="self"
        )
        with pytest.raises(ScoreContractError, match="own parent"):
            dataclasses.replace(revision, parent_revision_id=revision.revision_id)

    def test_blank_parent_id_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="parent_revision_id"):
            make_revision(revision_number=2, parent_revision_id="   ")

    def test_zero_revision_number_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="revision_number"):
            make_revision(revision_number=0)

    def test_negative_revision_number_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="revision_number"):
            make_revision(revision_number=-1)

    def test_bool_revision_number_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="revision_number"):
            make_revision(revision_number=True)  # type: ignore[arg-type]


class TestLineageChain:
    def test_a_three_revision_chain_is_representable(self) -> None:
        first = make_revision(revision_number=1, digest_label="r1")
        second = make_revision(
            revision_number=2, parent_revision_id=first.revision_id, digest_label="r2"
        )
        third = make_revision(
            revision_number=3, parent_revision_id=second.revision_id, digest_label="r3"
        )
        assert [r.revision_number for r in (first, second, third)] == [1, 2, 3]
        assert third.parent_revision_id == second.revision_id
        assert second.parent_revision_id == first.revision_id
        assert first.parent_revision_id is None

    def test_each_revision_in_a_chain_has_a_distinct_identity(self) -> None:
        first = make_revision(revision_number=1, digest_label="r1")
        second = make_revision(
            revision_number=2, parent_revision_id=first.revision_id, digest_label="r2"
        )
        assert first.revision_id != second.revision_id
        assert first.content_digest != second.content_digest

    def test_same_content_yields_the_same_identity(self) -> None:
        # Content-addressed identity: two revisions with identical content are the same
        # revision, which is what makes idempotent ingestion possible in A5.
        left = make_revision(events=(make_event(0),), digest_label="same")
        right = make_revision(events=(make_event(0),), digest_label="same")
        assert left.revision_id == right.revision_id

    def test_all_revisions_share_the_document_id(self) -> None:
        first = make_revision(revision_number=1, digest_label="r1")
        second = make_revision(
            revision_number=2, parent_revision_id=first.revision_id, digest_label="r2"
        )
        assert first.document_id == second.document_id == DOCUMENT_ID


class TestRevisionNumberIsNotCallerChosen:
    def test_the_contract_validates_structurally_only(self) -> None:
        # A2 can only see one revision, so it cannot know whether 7 is the next number
        # for this document. Contiguity is the revision service's invariant (A4); what
        # A2 guarantees is that whatever number arrives is a positive integer with
        # lineage consistent with itself.
        seventh = make_revision(
            revision_number=7, parent_revision_id="rev-" + "a" * 24, digest_label="r7"
        )
        assert seventh.revision_number == 7

    def test_no_public_constructor_advances_a_document(self) -> None:
        # A revision cannot move a document's pointer; only the service composes both.
        assert not hasattr(CanonicalScoreRevisionV1, "next_revision")
        assert not hasattr(CanonicalScoreRevisionV1, "create_child")
