#!/usr/bin/env python3
# ruff: noqa: E402
"""Build a deterministic DO-010 Educational evaluation evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from master_all_strings.education.serialization import to_dict  # noqa: E402
from master_all_strings.mvp.education_api import (  # noqa: E402
    GOLDEN_DEMO_ATTEMPTS,
    LocalPracticeEvaluationApi,
)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    api = LocalPracticeEvaluationApi()
    golden = api.handle("golden_demo", {})
    attempts = []
    for filename, expected in GOLDEN_DEMO_ATTEMPTS:
        fixture_path = (
            ROOT / "resources" / "education" / "examples" / "evaluation" / filename
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        # Re-evaluate each fixture independently for portable digests.
        single = LocalPracticeEvaluationApi()
        result = single.handle("evaluate", fixture)
        attempts.append(
            {
                "fixture": filename,
                "expected_primary_action": expected.value,
                "actual_primary_action": result["evaluation"]["primary_next_action"][
                    "action_type"
                ],
                "evaluation_digest": result["evaluation"]["evaluation_digest"],
                "actionable_finding_count": result["evaluation"]["summary"][
                    "actionable_finding_count"
                ],
                "finding_types": sorted(
                    {finding["finding_type"] for finding in result["evaluation"]["findings"]}
                ),
            }
        )
        (args.output / f"{Path(filename).stem}.evaluation.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    policy = to_dict(
        __import__(
            "master_all_strings.education.contracts",
            fromlist=["PracticeEvaluationPolicyV1"],
        ).PracticeEvaluationPolicyV1.mvp_defaults()
    )
    pack = {
        "dev_order": "DO-010",
        "product_base_do009_sha": "92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec",
        "base_do008_sha": "f9018213fb9097cb716a8c91670ae03f7ed1b514",
        "ownership": [
            "PerformanceSessionEvidenceV1",
            "education/",
            "PracticeEvaluationResultV1",
        ],
        "contracts": [
            "PracticeEvaluationPolicyV1",
            "PracticeFindingV1",
            "PracticeAttemptSummaryV1",
            "PracticeNextActionV1",
            "PracticeEvaluationResultV1",
        ],
        "deferred_contract": "EducationalInterpretationV1",
        "policy": policy,
        "golden_demo": golden,
        "attempts": attempts,
        "hardware_status": {
            "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
            "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
        },
        "continue_claims_mastery": False,
        "performance_contracts_modified_for_grading": False,
    }
    pack["evidence_digest"] = _digest(
        {
            "attempts": attempts,
            "contracts": pack["contracts"],
            "deferred_contract": pack["deferred_contract"],
            "dev_order": pack["dev_order"],
            "golden_sequence": golden["sequence"],
            "hardware_status": pack["hardware_status"],
            "policy": policy,
            "product_base_do009_sha": pack["product_base_do009_sha"],
            "base_do008_sha": pack["base_do008_sha"],
        }
    )
    (args.output / "DO010_EVALUATION_EVIDENCE.json").write_text(
        json.dumps(pack, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "evidence_digest": pack["evidence_digest"],
                "sequence": golden["sequence"],
                "attempts": [a["actual_primary_action"] for a in attempts],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
