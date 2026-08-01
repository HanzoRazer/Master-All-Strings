"""Tests for the engine-boundary validator.

The committed registry must be clean; deliberately corrupted copies must each raise
the specific violation they model, so a real future regression cannot pass.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from master_all_strings.governance import engine_boundaries as eb


@pytest.fixture
def registry() -> dict[str, Any]:
    return eb.load_registry()


def _codes(reg: dict[str, Any]) -> set[str]:
    return {v.code for v in eb.validate_registry(reg)}


class TestCommittedRegistryIsClean:
    def test_committed_registry_has_no_violations(self, registry: dict[str, Any]) -> None:
        assert eb.validate_registry(registry) == []

    def test_cli_reports_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert eb.main([]) == 0
        assert "OK" in capsys.readouterr().out


class TestEngineInvariants:
    def test_missing_engine_fails(self, registry: dict[str, Any]) -> None:
        registry["engines"] = registry["engines"][:3]
        assert "ENGINES" in _codes(registry)

    def test_wrong_engine_id_fails(self, registry: dict[str, Any]) -> None:
        registry["engines"][1]["id"] = "PEDAGOGY_ENGINE"
        assert "ENGINES" in _codes(registry)

    def test_core_not_marked_independent_fails(self, registry: dict[str, Any]) -> None:
        for e in registry["engines"]:
            if e["id"] == "MUSICAL_CORE":
                e["depends_on_none"] = False
        assert "CORE_INDEPENDENT" in _codes(registry)

    def test_two_independent_engines_fails(self, registry: dict[str, Any]) -> None:
        for e in registry["engines"]:
            if e["id"] == "EDUCATIONAL_ENGINE":
                e["depends_on_none"] = True
        assert "CORE_INDEPENDENT" in _codes(registry)


class TestDependencyDirection:
    def test_core_depending_on_educational_fails(self, registry: dict[str, Any]) -> None:
        for r in registry["dependency_rules"]:
            if r["from"] == "MUSICAL_CORE" and r["to"] == "EDUCATIONAL_ENGINE":
                r["relation"] = "depends"
        assert "CORE_DEPENDS" in _codes(registry)

    def test_incomplete_matrix_fails(self, registry: dict[str, Any]) -> None:
        registry["dependency_rules"] = registry["dependency_rules"][:-1]
        assert "MATRIX" in _codes(registry)

    def test_duplicate_rule_fails(self, registry: dict[str, Any]) -> None:
        registry["dependency_rules"].append(copy.deepcopy(registry["dependency_rules"][0]))
        assert "MATRIX" in _codes(registry)


class TestCapabilityOwnership:
    def test_duplicate_capability_id_fails(self, registry: dict[str, Any]) -> None:
        registry["capabilities"].append(copy.deepcopy(registry["capabilities"][0]))
        assert "CAP_DUP" in _codes(registry)

    def test_consumer_that_cannot_depend_on_owner_fails(self, registry: dict[str, Any]) -> None:
        # curriculum is Educational-owned; Performance cannot depend on Educational.
        for cap in registry["capabilities"]:
            if cap["id"] == "curriculum":
                cap["permitted_consumers"] = ["PERFORMANCE_ENGINE"]
        assert "CAP_DEP" in _codes(registry)

    def test_owner_listed_as_own_consumer_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "curriculum":
                cap["permitted_consumers"] = ["EDUCATIONAL_ENGINE"]
        assert "CAP_SELF" in _codes(registry)


class TestClassificationAndSeams:
    def test_interpretation_owned_by_core_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "candidate-generation":
                cap["classification"] = "interpretation"
        assert "CLASS" in _codes(registry)

    def test_evidence_owned_by_creative_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "composition":
                cap["classification"] = "evidence"
        assert "CLASS" in _codes(registry)

    def test_performance_owning_interpretation_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "telemetry":
                cap["classification"] = "interpretation"
        # PERF_POLICY (performance may not own interpretation) fires; CLASS also fires.
        assert "PERF_POLICY" in _codes(registry)

    def test_spatial_evidence_reassigned_off_core_fails(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "SpatialEvidenceV1":
                con["owning_engine"] = "EDUCATIONAL_ENGINE"
                con["versioning_authority"] = "EDUCATIONAL_ENGINE"
                con["classification"] = "interpretation"
        assert "SEAM" in _codes(registry)

    def test_missing_required_seam_contract_fails(self, registry: dict[str, Any]) -> None:
        registry["contracts"] = [
            c for c in registry["contracts"] if c["name"] != "CoachingRecommendationV1"
        ]
        assert "SEAM" in _codes(registry)


class TestContractInvariants:
    def test_versioning_authority_not_owner_fails(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "LearningObject":
                con["versioning_authority"] = "MUSICAL_CORE"
        assert "CON_VERSION" in _codes(registry)

    def test_contract_consumer_wrong_direction_fails(self, registry: dict[str, Any]) -> None:
        # EducationalInterpretationV1 is Educational-owned; Performance cannot consume it.
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["consumers"] = ["PERFORMANCE_ENGINE"]
        assert "CON_DEP" in _codes(registry)

    def test_interpretation_must_cite_evidence(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["cites"] = "LearningObject"  # not an evidence contract
        assert "CON_CITE" in _codes(registry)

    def test_owner_consuming_own_contract_is_allowed(self, registry: dict[str, Any]) -> None:
        # ProjectionRequest is Core-owned and Core-consumed; this must NOT be flagged.
        names = {v.detail for v in eb.validate_registry(registry) if v.code == "CON_DEP"}
        assert not any("ProjectionRequest" in d for d in names)


class TestAdrAssignments:
    def test_adr_0005_reassigned_fails(self, registry: dict[str, Any]) -> None:
        for a in registry["adr_assignments"]:
            if a["adr"] == "ADR-0005":
                a["status"] = "accepted"
                a["owner"] = "DO-005"
        assert "ADR_0005" in _codes(registry)

    def test_adr_number_reuse_fails(self, registry: dict[str, Any]) -> None:
        registry["adr_assignments"].append(
            {"adr": "ADR-0006", "title": "dup", "status": "accepted"}
        )
        assert "ADR_DUP" in _codes(registry)

    def test_adr_0006_not_accepted_fails(self, registry: dict[str, Any]) -> None:
        for a in registry["adr_assignments"]:
            if a["adr"] == "ADR-0006":
                a["status"] = "proposed"
        assert "ADR_0006" in _codes(registry)


class TestRemainingBranches:
    """Direct coverage for the defensive and CLI branches."""

    def test_duplicate_engine_id(self, registry: dict[str, Any]) -> None:
        registry["engines"].append(copy.deepcopy(registry["engines"][0]))
        assert "ENGINES" in _codes(registry)

    def test_duplicate_contract_name(self, registry: dict[str, Any]) -> None:
        registry["contracts"].append(copy.deepcopy(registry["contracts"][0]))
        assert "CON_DUP" in _codes(registry)

    def test_cite_unknown_contract(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["cites"] = "NoSuchContract"
        assert "CON_CITE" in _codes(registry)

    def test_non_interpretation_that_cites_is_flagged(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "SelectedSpatialPath":  # classification 'evidence'
                con["cites"] = "SpatialEvidenceV1"
        assert "CON_CITE" in _codes(registry)

    def test_relation_returns_none_for_self_pair(self, registry: dict[str, Any]) -> None:
        assert eb._relation(registry, "MUSICAL_CORE", "MUSICAL_CORE") is None

    def test_violation_str_is_readable(self) -> None:
        assert str(eb.Violation("CODE", "detail")) == "[CODE] detail"

    def test_format_with_violations(self) -> None:
        out = eb._format([eb.Violation("A", "x")])
        assert "violations" in out and "[A] x" in out

    def test_cli_write_views_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Idempotent: rewrites the already-generated views with identical content.
        assert eb.main(["--write-views"]) == 0
        assert "wrote" in capsys.readouterr().out

    def test_cli_nonzero_on_violation(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = eb.load_registry()
        broken["engines"] = broken["engines"][:3]
        (tmp_path / "reg.json").write_text(__import__("json").dumps(broken), encoding="utf-8")
        monkeypatch.setattr(eb, "REGISTRY_PATH", tmp_path / "reg.json")
        assert eb.main([]) == 1
        assert "violations" in capsys.readouterr().out


class TestPrimaryContractReferences:
    """A capability's ``primary_contract`` must resolve and be coherent with it.

    Closes the gap tracked in issue #9: the JSON schema only requires a non-empty
    string, so before this check a capability could name a contract that does not
    exist and the registry would still validate clean. That asymmetry mattered because
    a contract's ``cites`` reference *was* already validated.

    Two of the rules are deliberately weaker than "must match exactly". The registry
    contains counterexamples to the stricter reading, and rejecting those would be a
    worse defect than the gap being closed.
    """

    def _capability(self, reg: dict[str, Any], cid: str) -> dict[str, Any]:
        for cap in reg["capabilities"]:
            if cap["id"] == cid:
                return cap
        raise AssertionError(f"capability {cid!r} not found")

    def test_committed_registry_resolves_every_primary_contract(
        self, registry: dict[str, Any]
    ) -> None:
        names = {c["name"] for c in registry["contracts"]}
        referenced = [
            cap["primary_contract"]
            for cap in registry["capabilities"]
            if cap.get("primary_contract")
        ]
        assert referenced, "expected at least one capability to name a primary contract"
        assert set(referenced) <= names

    def test_unknown_primary_contract_fails(self, registry: dict[str, Any]) -> None:
        self._capability(registry, "coaching")["primary_contract"] = "TotallyMadeUpContractXYZ"
        assert "CAP_CONTRACT" in _codes(registry)

    def test_non_string_primary_contract_fails(self, registry: dict[str, Any]) -> None:
        # The schema catches this first in normal use; the validator must not depend
        # on having been run in the right order.
        self._capability(registry, "coaching")["primary_contract"] = 7
        assert "CAP_CONTRACT" in _codes(registry)

    def test_capability_without_a_primary_contract_is_unaffected(
        self, registry: dict[str, Any]
    ) -> None:
        capability = self._capability(registry, "curriculum")
        assert "primary_contract" not in capability
        assert eb.validate_registry(registry) == []


class TestPrimaryContractEngineRule:
    """The owner must be the contract's owner *or* its producer."""

    def _capability(self, reg: dict[str, Any], cid: str) -> dict[str, Any]:
        for cap in reg["capabilities"]:
            if cap["id"] == cid:
                return cap
        raise AssertionError(f"capability {cid!r} not found")

    def test_unrelated_engine_fails(self, registry: dict[str, Any]) -> None:
        # Naming a contract this engine neither owns nor produces would let a
        # capability claim authority over a record it does not control.
        self._capability(registry, "coaching")["primary_contract"] = "SpatialEvidenceV1"
        assert "CAP_CONTRACT_ENGINE" in _codes(registry)

    def test_owning_engine_is_accepted(self, registry: dict[str, Any]) -> None:
        assert "CAP_CONTRACT_ENGINE" not in _codes(registry)

    def test_producing_engine_is_accepted(self, registry: dict[str, Any]) -> None:
        # ScoreEditCommandSet is owned by Musical Core and produced by Creative --
        # the established pattern where Core owns the vocabulary for changing the
        # canonical model and another engine speaks it. A Creative capability naming
        # the command set it produces is correct, and an owner-only rule would
        # wrongly reject it.
        capability = self._capability(registry, "semantic-edit-proposals")
        capability["primary_contract"] = "ScoreEditCommandSet"
        assert "CAP_CONTRACT_ENGINE" not in _codes(registry)

    def test_the_registry_really_contains_that_asymmetry(
        self, registry: dict[str, Any]
    ) -> None:
        # Guards the rationale above: if the asymmetry ever disappears, the weaker
        # rule loses its justification and should be revisited rather than kept out
        # of habit.
        split = [
            c["name"]
            for c in registry["contracts"]
            if c["owning_engine"] not in c["producers"]
        ]
        assert "ScoreEditCommandSet" in split
        assert "ProjectionRequestV1" in split


class TestPrimaryContractClassificationRule:
    """Only the direct evidence/interpretation contradiction is rejected."""

    def _capability(self, reg: dict[str, Any], cid: str) -> dict[str, Any]:
        for cap in reg["capabilities"]:
            if cap["id"] == cid:
                return cap
        raise AssertionError(f"capability {cid!r} not found")

    def test_evidence_capability_naming_an_interpretation_contract_fails(
        self, registry: dict[str, Any]
    ) -> None:
        capability = self._capability(registry, "live-capture")
        capability["primary_contract"] = "CoachingRecommendationV1"
        assert "CAP_CONTRACT_CLASS" in _codes(registry)

    def test_interpretation_capability_naming_an_evidence_contract_fails(
        self, registry: dict[str, Any]
    ) -> None:
        capability = self._capability(registry, "educational-interpretation")
        capability["primary_contract"] = "SpatialEvidenceV1"
        assert "CAP_CONTRACT_CLASS" in _codes(registry)

    def test_neither_capability_may_name_an_evidence_contract(
        self, registry: dict[str, Any]
    ) -> None:
        # A mechanism that emits evidence is not itself evidence. Requiring exact
        # equality would reject this, which is stronger than the seam rule needs.
        capability = self._capability(registry, "candidate-generation")
        capability["classification"] = "neither"
        capability["primary_contract"] = "SpatialEvidenceV1"
        assert "CAP_CONTRACT_CLASS" not in _codes(registry)

    def test_matching_classifications_pass(self, registry: dict[str, Any]) -> None:
        assert "CAP_CONTRACT_CLASS" not in _codes(registry)

    def test_contradiction_helper_is_symmetric(self) -> None:
        assert eb._contradicts("evidence", "interpretation") is True
        assert eb._contradicts("interpretation", "evidence") is True
        assert eb._contradicts("neither", "evidence") is False
        assert eb._contradicts("evidence", "neither") is False
        assert eb._contradicts("evidence", "evidence") is False


class TestDuplicateContractNames:
    """A duplicate name must not produce a misleading capability violation."""

    def _first(self, reg: dict[str, Any], name: str) -> dict[str, Any]:
        for con in reg["contracts"]:
            if con["name"] == name:
                return con
        raise AssertionError(f"contract {name!r} not found")

    def test_duplicate_contract_name_is_reported_as_con_dup(
        self, registry: dict[str, Any]
    ) -> None:
        shadow = copy.deepcopy(self._first(registry, "SpatialEvidenceV1"))
        shadow["owning_engine"] = "EDUCATIONAL_ENGINE"
        # `producers`, not `producer`: the singular key the rename left behind here set
        # a field nothing reads, so the shadow silently kept the original engine's
        # producer list while claiming to be a different engine's contract.
        shadow["producers"] = ["EDUCATIONAL_ENGINE"]
        shadow["versioning_authority"] = "EDUCATIONAL_ENGINE"
        registry["contracts"].append(shadow)
        codes = _codes(registry)
        assert "CON_DUP" in codes
        # spatial-evidence names SpatialEvidenceV1. Validating it against an
        # arbitrary winner would emit an engine mismatch that is noise, not signal.
        assert "CAP_CONTRACT_ENGINE" not in codes

    def test_index_reports_the_duplicated_name(self, registry: dict[str, Any]) -> None:
        registry["contracts"].append(copy.deepcopy(self._first(registry, "SpatialEvidenceV1")))
        _, ambiguous = eb._index_contracts(registry)
        assert ambiguous == frozenset({"SpatialEvidenceV1"})

    def test_index_keeps_the_first_occurrence(self, registry: dict[str, Any]) -> None:
        shadow = copy.deepcopy(self._first(registry, "SpatialEvidenceV1"))
        shadow["classification"] = "neither"
        registry["contracts"].append(shadow)
        by_name, _ = eb._index_contracts(registry)
        assert by_name["SpatialEvidenceV1"]["classification"] == "evidence"

    def test_no_duplicates_yields_an_empty_ambiguous_set(
        self, registry: dict[str, Any]
    ) -> None:
        _, ambiguous = eb._index_contracts(registry)
        assert ambiguous == frozenset()


class TestContractProducers:
    """``producers`` is a list, because a contract can have more than one issuer.

    ``ProjectionRequestV1`` is the reason: Creative requests a projection while
    authoring, Educational while interpreting, and Performance after ingesting a
    capture. A single ``producer`` field forced the registry to state that only
    Creative may request a projection, which the accepted architecture contradicts.
    """

    def _contract(self, reg: dict[str, Any], name: str) -> dict[str, Any]:
        for con in reg["contracts"]:
            if con["name"] == name:
                return con
        raise AssertionError(f"contract {name!r} not found")

    def test_every_contract_declares_a_producer_list(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            assert isinstance(con["producers"], list), con["name"]
            assert con["producers"], con["name"]

    def test_empty_producer_list_fails(self, registry: dict[str, Any]) -> None:
        self._contract(registry, "MusicalEvent")["producers"] = []
        assert "CON_PRODUCER" in _codes(registry)

    def test_duplicate_producer_fails(self, registry: dict[str, Any]) -> None:
        self._contract(registry, "MusicalEvent")["producers"] = [
            "MUSICAL_CORE",
            "MUSICAL_CORE",
        ]
        assert "CON_PRODUCER" in _codes(registry)

    def test_a_producer_violating_dependency_direction_fails(
        self, registry: dict[str, Any]
    ) -> None:
        # Performance producing a Core-owned contract is legal -- Performance depends
        # on Core, which is how CanonicalIngestionRequestV1 works. The prohibited
        # direction is the reverse: Core may not depend on Educational, so Core
        # cannot produce an Educational-owned contract.
        self._contract(registry, "LearningObject")["producers"] = ["MUSICAL_CORE"]
        assert "CON_DEP" in _codes(registry)

    def test_performance_producing_a_core_owned_contract_is_permitted(
        self, registry: dict[str, Any]
    ) -> None:
        # The established asymmetry: Core owns the vocabulary, another engine speaks
        # it. Rejecting this would break the DO-006 ingestion seam.
        self._contract(registry, "SpatialEvidenceV1")["producers"] = ["PERFORMANCE_ENGINE"]
        assert "CON_DEP" not in _codes(registry)

    def test_every_producer_of_every_contract_is_permitted(
        self, registry: dict[str, Any]
    ) -> None:
        assert "CON_DEP" not in _codes(registry)


class TestProjectionContractRename:
    """The unversioned names are gone and the V1 names carry correct authority."""

    def test_obsolete_unversioned_names_are_absent(self, registry: dict[str, Any]) -> None:
        names = [c["name"] for c in registry["contracts"]]
        assert "ProjectionRequest" not in names
        assert "ProjectionResult" not in names

    def test_versioned_names_appear_exactly_once(self, registry: dict[str, Any]) -> None:
        names = [c["name"] for c in registry["contracts"]]
        assert names.count("ProjectionRequestV1") == 1
        assert names.count("ProjectionResultV1") == 1

    def test_three_engines_may_request_a_projection(self, registry: dict[str, Any]) -> None:
        request = next(
            c for c in registry["contracts"] if c["name"] == "ProjectionRequestV1"
        )
        assert set(request["producers"]) == {
            "CREATIVE_ENGINE",
            "EDUCATIONAL_ENGINE",
            "PERFORMANCE_ENGINE",
        }
        assert request["owning_engine"] == "MUSICAL_CORE"
        assert request["consumers"] == ["MUSICAL_CORE"]

    def test_only_musical_core_produces_a_projection_result(
        self, registry: dict[str, Any]
    ) -> None:
        # A projection result is Core stating what the revision looks like. Another
        # engine producing one would be a second interpretation authority.
        result = next(c for c in registry["contracts"] if c["name"] == "ProjectionResultV1")
        assert result["producers"] == ["MUSICAL_CORE"]
        assert set(result["consumers"]) == {
            "CREATIVE_ENGINE",
            "EDUCATIONAL_ENGINE",
            "PERFORMANCE_ENGINE",
        }

    def test_no_document_still_refers_to_the_unversioned_names(self) -> None:
        # A rename that leaves prose behind is a rename that did not happen.
        import re

        root = eb.REGISTRY_PATH.parents[1]
        stale: list[str] = []
        for path in list((root / "docs").rglob("*.md")) + [eb.REGISTRY_PATH]:
            if "handoff" in path.parts:
                continue  # preserved historical text, deliberately not rewritten
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\bProjection(?:Request|Result)\b(?!V1)", text):
                stale.append(f"{path.name}: {match.group(0)}")
        assert stale == []


class TestCanonicalMusicStatus:
    """``canonical-music`` was overstated before DO-007, and is earned after it.

    A1 corrected it to ``partial`` because only an atomic ``MusicalEvent`` existed. A5
    returns it to ``implemented`` -- but only because the things it claims now exist,
    which is what this test checks rather than taking the status at its word.
    """

    def test_canonical_music_is_implemented(self, registry: dict[str, Any]) -> None:
        capability = next(
            c for c in registry["capabilities"] if c["id"] == "canonical-music"
        )
        assert capability["implementation_status"] == "implemented"

    def test_the_status_is_backed_by_real_code(self) -> None:
        # Every claim the promotion rests on, imported rather than assumed.
        from master_all_strings.core.ingestion.service import CanonicalIngestionService
        from master_all_strings.core.score.digest import compute_revision_digest
        from master_all_strings.core.score.models import (
            CanonicalScoreRevisionV1,
            ScoreDocumentV1,
        )
        from master_all_strings.core.score.repository import (
            CanonicalScoreRepositoryPort,
        )
        from master_all_strings.core.score.revision_service import (
            CanonicalRevisionService,
        )

        for thing in (
            ScoreDocumentV1,
            CanonicalScoreRevisionV1,
            compute_revision_digest,
            CanonicalScoreRepositoryPort,
            CanonicalRevisionService,
            CanonicalIngestionService,
        ):
            assert thing is not None

    def test_the_registry_records_the_new_core_contracts(
        self, registry: dict[str, Any]
    ) -> None:
        names = {c["name"] for c in registry["contracts"]}
        for expected in (
            "ScoreDocumentV1",
            "CanonicalScoreRevisionV1",
            "CanonicalIngestionResultV1",
        ):
            assert expected in names

    def test_musical_core_owns_every_new_score_contract(
        self, registry: dict[str, Any]
    ) -> None:
        for name in (
            "ScoreDocumentV1",
            "CanonicalScoreRevisionV1",
            "CanonicalIngestionResultV1",
        ):
            contract = next(c for c in registry["contracts"] if c["name"] == name)
            assert contract["owning_engine"] == "MUSICAL_CORE"
            assert contract["producers"] == ["MUSICAL_CORE"]

    def test_no_score_capability_claims_more_than_it_delivers(
        self, registry: dict[str, Any]
    ) -> None:
        for cid in (
            "piano-roll-projection",
            "notation-projection",
            "tab-projection",
            "midi-projection",
        ):
            capability = next(c for c in registry["capabilities"] if c["id"] == cid)
            assert capability["implementation_status"] == "planned"
