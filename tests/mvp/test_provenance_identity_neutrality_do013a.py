"""Provenance changes must not move musical identity (DO-013A rulings 2 and 3).

Two provenance edits landed together: the policy token became
``AUTHORED_LESSON_REVISION_V1``, and ``created_at`` stopped being a module
constant and became each lesson's own ``provenance.created_at_utc``.

Both were argued to be identity-neutral because Core excludes ``created_at`` and
``provenance`` from the content digest. That argument is only worth as much as
its evidence, so the digests below were captured from the running build
*immediately before* either edit and frozen here verbatim. A test that recomputed
the "before" values from the current code would prove nothing at all -- it would
agree with itself no matter what broke.

If this file fails, a provenance edit reached musical identity and the exported
corpus is no longer the same music it was.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from master_all_strings.core.projections.serialization import canonical_projection_digest
from master_all_strings.lesson.canonicalization import (
    AUTHORED_LESSON_POLICY_VERSION,
    build_authored_lesson_revision,
)
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest


@dataclass(frozen=True)
class FrozenIdentity:
    """One lesson's musical identity as it stood before the provenance edits."""

    revision_id: str
    content_digest: str
    tab_digest: str
    notation_digest: str


#: Captured from the build at the commit preceding the provenance rename, with
#: ``created_at`` still the hard-coded ``2026-01-01T00:00:00Z`` constant and
#: ``policy_version`` still ``AUTHORED_LESSON_CONSTRUCTION_V1``.
BEFORE: dict[str, FrozenIdentity] = {
    "ascending_scale": FrozenIdentity(
        revision_id="rev-cc28c4e1b3a1e2ae9d130332",
        content_digest="cc28c4e1b3a1e2ae9d130332100c35700733fa23ceb97b310b354790f39f21e3",
        tab_digest="sha256:7c1cf893229aba298f221d27b6f6e88149ea110bb44fdec35807cfefcb573010",
        notation_digest="sha256:935cd7300c6d7858ab3559a020b8602bb958e06a251d9a790417c2241884b69b",
    ),
    "descending_scale": FrozenIdentity(
        revision_id="rev-16bc98c2d96b53da107f3690",
        content_digest="16bc98c2d96b53da107f3690be9ef51aa6af700316ff5371217c917ed183b336",
        tab_digest="sha256:35de3a8327bf85c36c52a4b041240d889e4079ecbc1c124b4d9f788a277b5896",
        notation_digest="sha256:ee560af3cf7592e01ce6358631a52aaa742a32d08ca0a7adbd8bab2f4fe1c668",
    ),
    "first_position": FrozenIdentity(
        revision_id="rev-5eec3b4504d674f0ce971aa7",
        content_digest="5eec3b4504d674f0ce971aa7301fecf786575d8aae57d365470980eb5f21a55d",
        tab_digest="sha256:64f6aac989632a1ae21b710447165549a677aa6284e1527ea75a83975bab312e",
        notation_digest="sha256:c1f0900ead78547f5d6f60fa9d4a44de2deabc98de74fd0de897a6400b293105",
    ),
    "half_steps_one_string": FrozenIdentity(
        revision_id="rev-b85e77022251b045cfe38b7d",
        content_digest="b85e77022251b045cfe38b7d00f6157e4ea5f618758b6433177a3949b7a4f8f3",
        tab_digest="sha256:0c72945fa09e8f50ff713b6bfd8ebccc05442e5bf2547a050f7399dca07ac62c",
        notation_digest="sha256:ad3640d694eb2e9d899344b012f48c74af4ff7eb5645ed81baaf127a98afdf54",
    ),
    "multiple_candidates": FrozenIdentity(
        revision_id="rev-439ed305bd1c6a1d54d5f266",
        content_digest="439ed305bd1c6a1d54d5f2667e2d5cca4f018975cce876823dd17e386bdc0d4a",
        tab_digest="sha256:82003f15c6c83c7a1eda8963079d7bd2fea3441842b4912d3186e3bcaae88131",
        notation_digest="sha256:41d44ce12a40339ed5253319f0aad6de29525a21261793e32a0cbb01e3174703",
    ),
    "open_strings": FrozenIdentity(
        revision_id="rev-30e24696b277044941fa4aa8",
        content_digest="30e24696b277044941fa4aa8861180586f947dd39c61be422c5f1cfb270cca11",
        tab_digest="sha256:c44de3f953ac3f5c39b4c02f1a8f75a20cb72644eb4a6e2e5c65066007023c0f",
        notation_digest="sha256:135736a94b88f09870c8bef06f049b56d20f1aa5ed444d9dfd8bec6fe0420227",
    ),
    "position_shift": FrozenIdentity(
        revision_id="rev-40b97b84994cc778ab7237ae",
        content_digest="40b97b84994cc778ab7237aee1aff8c312294c0b271c9621a1e69af5773d6540",
        tab_digest="sha256:657cdfc9bdaa48762acfe4e8475f751852198de3033c343da173ebd848b2a3be",
        notation_digest="sha256:71691774467e5e2df0347e09491da7a260ae29b7c8603cde99edbfb191aba902",
    ),
    "simultaneous_notes": FrozenIdentity(
        revision_id="rev-3b5be15df289a8483a0f57b9",
        content_digest="3b5be15df289a8483a0f57b96ca4cc4870a080973d22950e22b4d658738f8ecd",
        tab_digest="sha256:4ccfe4dfad96be0a60ff73533015a019686cdddbd692d1d69638f5606a9ea0a2",
        notation_digest="sha256:14d240d2a9efa51b06d8e2dd926331e8cf5e43210fbe2853a782f76b84a6dd15",
    ),
    "string_crossing": FrozenIdentity(
        revision_id="rev-9ac1cd971dfe054ebf07ecea",
        content_digest="9ac1cd971dfe054ebf07eceaca135fade56f45483a583d546face8683c935eac",
        tab_digest="sha256:3824a9c0d2d83f09325fc4f76477949fca33a7814042add402451f2e56fb0773",
        notation_digest="sha256:b6e4dd67fc5b3f546e92fa6d28b4ded74650c66747a6809fb3c7a225a4e2602e",
    ),
    "teacher_override": FrozenIdentity(
        revision_id="rev-e3b0a1db2e0285d09fc33422",
        content_digest="e3b0a1db2e0285d09fc3342288f83a72dd553bdc47d037566d428b27fc223393",
        tab_digest="sha256:555f802b1c4017c27744bd94940feb6d41eaeb78d96c7e7bac3ee2b88f9f11d0",
        notation_digest="sha256:aeb7af1ab7e1a83807a6c54d8015afa93aebe98480554b5b32fbb9543afdf38e",
    ),
    "unplayable_note": FrozenIdentity(
        revision_id="rev-5336c8b3c6698b26e579fc48",
        content_digest="5336c8b3c6698b26e579fc4897a623b94a575a54b73e1d9432efa0f1ea99c7e9",
        tab_digest="sha256:e9399f07d9ea16029780b48333776a9143b97033cb8ef21f1fac4cd72071a299",
        notation_digest="sha256:f25eca3e0579ca0891235c8f6a908617757a3fbb85b68c3b82572b3a03fecf17",
    ),
}

MANIFEST = load_demo_manifest()
PROFILE_BY_DEMO = {entry.demo_id: entry.instrument_profile_id for entry in MANIFEST}
DEMO_IDS = sorted(PROFILE_BY_DEMO)


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_the_provenance_edits_did_not_move_musical_identity(
    app: MvpApplication, demo_id: str
) -> None:
    response = app.run_demo(demo_id, instrument_profile_id=PROFILE_BY_DEMO[demo_id])
    assert response.score is not None
    expected = BEFORE[demo_id]

    assert response.score.revision.revision_id == expected.revision_id
    assert response.score.revision.content_digest == expected.content_digest
    assert canonical_projection_digest(response.score.tab_payload) == expected.tab_digest
    assert (
        canonical_projection_digest(response.score.notation_payload)
        == expected.notation_digest
    )


def test_the_frozen_table_covers_the_whole_corpus() -> None:
    """A neutrality claim that skipped a lesson would not be a claim about the corpus."""

    assert set(BEFORE) == {entry.demo_id for entry in MANIFEST}


# --- the edits themselves actually happened ----------------------------------


def test_the_policy_token_is_the_settled_vocabulary() -> None:
    assert AUTHORED_LESSON_POLICY_VERSION == "AUTHORED_LESSON_REVISION_V1"


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_each_revision_carries_its_own_lessons_stamp(demo_id: str) -> None:
    """Per-lesson, not one shared constant -- otherwise the switch was cosmetic."""

    assignment = load_demo_assignment(demo_id)
    revision = build_authored_lesson_revision(
        resolve_lesson_assignment(assignment),
        created_at=assignment.provenance.created_at_utc,
    ).revision
    assert revision.created_at == assignment.provenance.created_at_utc
    assert revision.created_at != "2026-01-01T00:00:00Z"


@pytest.mark.parametrize("demo_id", DEMO_IDS)
def test_changing_created_at_alone_leaves_identity_untouched(demo_id: str) -> None:
    """The mechanism the neutrality claim rests on, asserted directly."""

    resolved = resolve_lesson_assignment(load_demo_assignment(demo_id))
    a = build_authored_lesson_revision(resolved, created_at="2026-08-17T00:00:00Z")
    b = build_authored_lesson_revision(resolved, created_at="2099-12-31T23:59:59Z")

    assert a.revision.created_at != b.revision.created_at
    assert a.revision.revision_id == b.revision.revision_id
    assert a.revision.content_digest == b.revision.content_digest
