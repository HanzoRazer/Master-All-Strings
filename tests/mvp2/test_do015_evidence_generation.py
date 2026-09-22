"""The frozen evidence must be something a reviewer can rebuild.

The verifier proves the record is consistent with the repository. It cannot
prove where the record came from -- a hand-assembled file that happens to be
consistent passes it. For a tranche whose product is evidence, that gap is the
difference between "plausible" and "reproducible", so the generator is
committed and this holds the committed record to it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "mvp2" / "DO015_INTEGRATION_EVIDENCE.json"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("build_do015_certification_evidence")


def test_the_committed_evidence_is_what_the_generator_builds() -> None:
    committed = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert committed == generator.build(), (
        "the frozen evidence is not what the generator produces; re-run "
        "python scripts/build_do015_certification_evidence.py"
    )


def test_the_check_mode_agrees() -> None:
    assert generator.main(["--check"]) == 0


def test_generation_is_deterministic() -> None:
    first = json.dumps(generator.build(), sort_keys=True)
    second = json.dumps(generator.build(), sort_keys=True)
    assert first == second


def test_the_generator_derives_rather_than_restates() -> None:
    built = generator.build()
    artifacts = REPO_ROOT / "docs" / "mvp2" / "do015_artifacts"
    session = json.loads((artifacts / "certified_session.json").read_text(encoding="utf-8"))
    browser = json.loads((artifacts / "browser_smoke_summary.json").read_text(encoding="utf-8"))
    # Facts come out of the artifacts the product wrote, not out of the
    # generator: editing an artifact must move the record.
    assert built["digest_invariants"]["session_digest"] == session["session"]["session_digest"]
    assert built["browser_reproducible"]["attempt_ids"] == browser["attempt_ids"]
    assert built["lesson_transition"]["authoritative_witness"] == session["lesson_transition"]


def test_the_measurements_are_the_only_undeclared_inputs() -> None:
    # Everything else is derived. If this list grows, the record has started
    # carrying claims nobody can reproduce.
    # The CI seal is data, not a measurement: sealing must be a metadata-only
    # commit, so it cannot live in this module.
    assert generator.CI_SEAL.exists()
    assert set(generator.MEASUREMENTS) == {
        "targeted",
        "full",
        "coverage_percent",
        "node",
        "mypy_source_files",
        "stage8",
    }


def test_the_record_states_its_own_source_of_truth() -> None:
    built = generator.build()
    order = built["source_of_truth"]["order"]
    assert len(order) == 4
    assert "suites" in order[0]
    assert "report" in order[-1].lower()
    assert built["source_of_truth"]["reproduce"], "a reader needs the commands"
