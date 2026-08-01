"""Document identity authorities (DO-007A A3).

A document id survives every revision, so it cannot be content-addressed. It has to come
from somewhere, and these tests fix that the somewhere is injected rather than reached
for globally -- which is what makes an ingestion run reproducible.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from master_all_strings.core.score import ids as ids_module
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.ids import (
    DOCUMENT_ID_PREFIX,
    DeterministicDocumentIdAuthority,
    DocumentIdAuthority,
    FixedDocumentIdAuthority,
    UuidDocumentIdAuthority,
    format_document_id,
)


class TestProtocol:
    @pytest.mark.parametrize(
        "authority",
        [
            UuidDocumentIdAuthority(),
            DeterministicDocumentIdAuthority(),
            FixedDocumentIdAuthority("score-fixed"),
        ],
    )
    def test_every_authority_satisfies_the_protocol(self, authority: object) -> None:
        assert isinstance(authority, DocumentIdAuthority)


class TestDeterministicAuthority:
    def test_ids_are_sequential(self) -> None:
        authority = DeterministicDocumentIdAuthority()
        assert authority.next_document_id() == "score-test-0001"
        assert authority.next_document_id() == "score-test-0002"

    def test_two_authorities_replay_the_same_sequence(self) -> None:
        # Reproducible by construction: a test asserting on a document id does not have
        # to match a pattern.
        left = DeterministicDocumentIdAuthority()
        right = DeterministicDocumentIdAuthority()
        assert [left.next_document_id() for _ in range(3)] == [
            right.next_document_id() for _ in range(3)
        ]

    def test_prefix_and_start_are_configurable(self) -> None:
        authority = DeterministicDocumentIdAuthority(prefix="take", start=7, width=2)
        assert authority.next_document_id() == "score-take-07"

    def test_issued_ids_are_recorded(self) -> None:
        authority = DeterministicDocumentIdAuthority()
        authority.next_document_id()
        authority.next_document_id()
        assert authority.issued == ["score-test-0001", "score-test-0002"]

    def test_blank_prefix_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="prefix"):
            DeterministicDocumentIdAuthority(prefix="  ")

    def test_zero_start_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="start"):
            DeterministicDocumentIdAuthority(start=0)

    def test_zero_width_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="width"):
            DeterministicDocumentIdAuthority(width=0)


class TestUuidAuthority:
    def test_ids_are_prefixed(self) -> None:
        assert UuidDocumentIdAuthority().next_document_id().startswith(DOCUMENT_ID_PREFIX)

    def test_ids_are_distinct(self) -> None:
        authority = UuidDocumentIdAuthority()
        assert len({authority.next_document_id() for _ in range(100)}) == 100

    def test_id_shape_is_hex(self) -> None:
        suffix = UuidDocumentIdAuthority().next_document_id().removeprefix(DOCUMENT_ID_PREFIX)
        assert len(suffix) == 32
        assert all(c in "0123456789abcdef" for c in suffix)


class TestFixedAuthority:
    def test_the_preset_id_is_returned(self) -> None:
        assert FixedDocumentIdAuthority("score-abc").next_document_id() == "score-abc"

    def test_a_second_request_is_refused(self) -> None:
        # An accidental second document is a real ingestion defect, and a silent second
        # id would hide it.
        authority = FixedDocumentIdAuthority("score-abc")
        authority.next_document_id()
        with pytest.raises(ScoreContractError, match="second id"):
            authority.next_document_id()

    def test_blank_id_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="document_id"):
            FixedDocumentIdAuthority("   ")


class TestFormatting:
    def test_suffix_is_prefixed(self) -> None:
        assert format_document_id("abc") == "score-abc"

    def test_blank_suffix_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="suffix"):
            format_document_id("  ")

    def test_whitespace_suffix_rejected(self) -> None:
        with pytest.raises(ScoreContractError, match="whitespace"):
            format_document_id(" abc ")


class TestNoHiddenRandomnessOrClock:
    def test_only_the_uuid_authority_touches_uuid(self) -> None:
        # Randomness in an identity path is the kind of thing that works until it has
        # to be audited.
        tree = ast.parse(textwrap.dedent(inspect.getsource(ids_module)))
        callers: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if any(
                    isinstance(inner, ast.Attribute) and inner.attr == "uuid4"
                    for inner in ast.walk(node)
                ):
                    callers.append(node.name)
        assert callers == ["UuidDocumentIdAuthority"]

    def test_no_timestamp_is_used_as_identity(self) -> None:
        source = inspect.getsource(ids_module)
        for forbidden in ("datetime", "time.time", "monotonic", "now("):
            assert forbidden not in source, forbidden

    def test_no_randomness_outside_a_class(self) -> None:
        # Module-level randomness would run at import time and be unreachable to
        # injection. Checked on the tree body only, so the docstring cannot match.
        tree = ast.parse(textwrap.dedent(inspect.getsource(ids_module)))
        top_level = [n for n in tree.body if not isinstance(n, ast.ClassDef)]
        calls = [
            inner
            for node in top_level
            for inner in ast.walk(node)
            if isinstance(inner, ast.Attribute) and inner.attr == "uuid4"
        ]
        assert calls == []
