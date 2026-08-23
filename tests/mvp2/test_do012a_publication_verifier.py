"""DO-012A publication verifier: classification logic.

The verifier's job is to make "we remembered not to" into something a machine
re-checks. That only works if the classification itself is tested, so these feed
it synthetic inputs rather than whatever branch happens to exist locally -- a
check that can only run against one ephemeral branch is a check nobody can prove
works.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_do012a_publication.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_do012a_publication", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier() -> ModuleType:
    return _load()


# --- the forbidden-file scope guard ------------------------------------------
#
# DO-012 and DO-012A both defer three hygiene changes. Each is defensible
# engineering, which is exactly why a reviewer might wave one through; this is
# the guard that does not.


def test_a_clean_delta_carries_no_deferred_hygiene(verifier: ModuleType) -> None:
    clean = [
        "src/master_all_strings/presentation/timeline.py",
        "web/mvp1/teaching-timeline.js",
        "docs/mvp2/DO012_RELEASE_REPORT.md",
    ]
    assert verifier.deferred_hygiene_in(clean) == ()


@pytest.mark.parametrize(
    "path",
    [
        ".gitattributes",
        ".github/workflows/verify.yml",
        "scripts/verify_mvp1_release_lineage.py",
    ],
)
def test_each_deferred_hygiene_path_is_caught(verifier: ModuleType, path: str) -> None:
    delta = ["src/master_all_strings/presentation/timeline.py", path]
    assert verifier.deferred_hygiene_in(delta) == (path,)


def test_several_deferred_paths_are_all_reported_sorted(verifier: ModuleType) -> None:
    delta = [
        "scripts/verify_mvp1_release_lineage.py",
        "web/mvp1/app.js",
        ".gitattributes",
    ]
    assert verifier.deferred_hygiene_in(delta) == (
        ".gitattributes",
        "scripts/verify_mvp1_release_lineage.py",
    )


def test_a_similarly_named_path_is_not_caught(verifier: ModuleType) -> None:
    """Only the exact deferred paths. A prefix match would ban real work."""

    delta = [
        "docs/.gitattributes.md",
        ".github/workflows/verify-something-else.yml",
        "scripts/verify_do012a_publication.py",
    ]
    assert verifier.deferred_hygiene_in(delta) == ()


def test_the_live_alignment_delta_is_clean(verifier: ModuleType) -> None:
    """The guard, applied to the change set actually under review."""

    delta = verifier.changed_paths("origin/main", "HEAD")
    assert verifier.deferred_hygiene_in(delta) == ()


# --- evidence completeness ---------------------------------------------------


def test_a_complete_evidence_pack_reports_nothing_missing(verifier: ModuleType) -> None:
    payload = {name: "value" for name in verifier.REQUIRED_EVIDENCE_FIELDS}
    assert verifier.missing_evidence_fields(payload) == ()


def test_an_absent_field_is_missing(verifier: ModuleType) -> None:
    payload = {name: "value" for name in verifier.REQUIRED_EVIDENCE_FIELDS}
    del payload["do009_digest"]
    assert verifier.missing_evidence_fields(payload) == ("do009_digest",)


def test_a_null_placeholder_counts_as_missing(verifier: ModuleType) -> None:
    """A key holding None is the shape a half-finished pack has."""

    payload = {name: "value" for name in verifier.REQUIRED_EVIDENCE_FIELDS}
    payload["sync_health_samples"] = None
    assert verifier.missing_evidence_fields(payload) == ("sync_health_samples",)


def test_publication_fields_are_only_required_when_asked(verifier: ModuleType) -> None:
    payload = {name: "value" for name in verifier.REQUIRED_EVIDENCE_FIELDS}
    assert verifier.missing_evidence_fields(payload) == ()
    required = list(verifier.REQUIRED_EVIDENCE_FIELDS) + list(
        verifier.PUBLICATION_EVIDENCE_FIELDS
    )
    assert verifier.missing_evidence_fields(payload, required=required) == tuple(
        verifier.PUBLICATION_EVIDENCE_FIELDS
    )


def test_the_checked_in_evidence_pack_is_complete(verifier: ModuleType) -> None:
    payload = json.loads(
        (REPO_ROOT / "docs" / "mvp2" / "DO012_INTEGRATION_EVIDENCE.json").read_text(
            encoding="utf-8"
        )
    )
    assert verifier.missing_evidence_fields(payload) == ()


# --- baseline identity consistency -------------------------------------------


def _identities(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"do012_base_sha": "2695993a601f6cc7b526294bdaac50ec5650cc23"}
    payload.update(overrides)
    return payload


def test_matching_base_and_no_publication_fields_is_consistent(verifier: ModuleType) -> None:
    assert verifier.inconsistent_baseline_fields(_identities()) == ()


def test_a_wrong_do012_base_is_reported(verifier: ModuleType) -> None:
    payload = _identities(do012_base_sha="0" * 40)
    problems = verifier.inconsistent_baseline_fields(payload)
    assert any("do012_base_sha" in p for p in problems)


def test_post_merge_main_must_be_the_merge_commit(verifier: ModuleType) -> None:
    payload = _identities(alignment_merge_sha="a" * 40, post_merge_main_sha="b" * 40)
    problems = verifier.inconsistent_baseline_fields(payload)
    assert any("post_merge_main_sha" in p for p in problems)


def test_baseline_equal_to_the_merge_is_reported(verifier: ModuleType) -> None:
    """The baseline is the documentation closeout, which lands after the merge."""

    payload = _identities(
        alignment_merge_sha="a" * 40,
        post_merge_main_sha="a" * 40,
        mvp2b_baseline_sha="a" * 40,
    )
    problems = verifier.inconsistent_baseline_fields(payload)
    assert any("mvp2b_baseline_sha" in p for p in problems)


def test_a_baseline_without_a_merge_is_reported(verifier: ModuleType) -> None:
    payload = _identities(mvp2b_baseline_sha="c" * 40)
    problems = verifier.inconsistent_baseline_fields(payload)
    assert any("without alignment_merge_sha" in p for p in problems)


def test_a_correctly_ordered_publication_is_consistent(verifier: ModuleType) -> None:
    payload = _identities(
        alignment_merge_sha="a" * 40,
        post_merge_main_sha="a" * 40,
        mvp2b_baseline_sha="d" * 40,
    )
    assert verifier.inconsistent_baseline_fields(payload) == ()


# --- boundary and surface guards ---------------------------------------------


def test_no_presentation_contract_declares_a_revision_id(verifier: ModuleType) -> None:
    from master_all_strings.presentation import contracts

    assert verifier.contracts_declaring_revision_id(contracts) == ()


def test_a_contract_that_grew_a_revision_id_would_be_caught(verifier: ModuleType) -> None:
    """The guard has to fail on the thing it guards against, or it proves nothing."""

    from dataclasses import dataclass
    from types import SimpleNamespace

    @dataclass(frozen=True)
    class LeakyProjectionV1:
        canonical_revision_id: str

    module = SimpleNamespace(LeakyProjectionV1=LeakyProjectionV1)
    assert verifier.contracts_declaring_revision_id(module) == ("LeakyProjectionV1",)


def test_the_named_timeline_utilities_are_importable(verifier: ModuleType) -> None:
    from master_all_strings.presentation import synchronization, timeline

    assert verifier.missing_named_utilities(timeline, verifier.NAMED_TIMELINE_UTILITIES) == ()
    assert (
        verifier.missing_named_utilities(
            synchronization, verifier.NAMED_SYNCHRONIZATION_UTILITIES
        )
        == ()
    )


def test_a_renamed_utility_would_be_caught(verifier: ModuleType) -> None:
    from types import SimpleNamespace

    module = SimpleNamespace(tick_to_seconds_from_anchors=lambda: None)
    missing = verifier.missing_named_utilities(
        module, ("tick_to_seconds_from_anchors", "seconds_to_tick_from_anchors")
    )
    assert missing == ("seconds_to_tick_from_anchors",)


# --- CLI ---------------------------------------------------------------------


def test_the_verifier_passes_against_the_current_head(verifier: ModuleType) -> None:
    assert verifier.main(["--base", "origin/main", "--head", "HEAD"]) == 0


def test_requiring_publication_fields_fails_before_publication(
    verifier: ModuleType,
) -> None:
    """Before the merge those fields are legitimately unset, and must not pass."""

    assert (
        verifier.main(
            ["--base", "origin/main", "--head", "HEAD", "--require-publication"]
        )
        == 1
    )


def test_load_evidence_rejects_a_non_object(verifier: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "evidence.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        verifier.load_evidence(bad)


# Fixed points in history, not HEAD. A pull_request CI run checks out the
# ephemeral refs/pull/N/merge commit, so HEAD there has two parents while a local
# branch tip has one -- asserting on it tests the runner, not the function.
KNOWN_MERGE_SHA = "dfeb4dc"  # Merge pull request #19
KNOWN_LINEAR_SHA = "2695993"  # docs(mvp2a): finalize DO-011A publication evidence


def test_a_two_parent_merge_is_recognised(verifier: ModuleType) -> None:
    assert verifier.merge_parent_count(KNOWN_MERGE_SHA) == 2


def test_a_single_parent_commit_is_recognised(verifier: ModuleType) -> None:
    assert verifier.merge_parent_count(KNOWN_LINEAR_SHA) == 1


def test_an_unknown_ref_reports_no_parents_rather_than_raising(
    verifier: ModuleType,
) -> None:
    """The verifier reports; it is not the place a bad ref explodes."""

    assert verifier.merge_parent_count("0000000000000000000000000000000000000000") == 0
