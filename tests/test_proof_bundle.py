from __future__ import annotations

from edgequeue.proof_bundle import build_proof_bundle
from edgequeue.verification import verify_proof_bundle


def _minimal_artifacts() -> dict[str, object]:
    digest = "a" * 64
    return {
        "evaluation-configuration.json": {
            "corpus_digest": digest,
            "split": "DEV",
            "split_digest": digest,
            "review_budget": 1,
            "calibration_pack_version": None,
        },
        "ranker-cases.jsonl": [
            {"case_id": "EQ-F01-DEV-01", "split": "DEV", "current_verdict": "PASS"}
        ],
        "scorer-cases.jsonl": [
            {
                "case_id": "EQ-F01-DEV-01",
                "reference_verdict": "FAIL",
                "scorer_sentinel": "scorer-only-01",
            }
        ],
        "baseline-rankings.json": {"random": ["EQ-F01-DEV-01"]},
        "edgequeue-ranking.json": {"review_queue": ["EQ-F01-DEV-01"]},
        "allocation-receipt.json": {
            "corpus_digest": digest,
            "split_digest": digest,
            "review_budget": 1,
            "review_queue": ["EQ-F01-DEV-01"],
        },
        "adjudications.jsonl": [],
        "metrics.json": {"recall_at_k": 1.0, "precision_at_k": 1.0},
        "claims-manifest.json": {
            "claims": [
                {
                    "metric": "recall_at_k",
                    "value": 1.0,
                    "supporting_artifact": "metrics.json",
                }
            ]
        },
    }


def test_verifies_a_minimal_manifest_bound_proof_bundle(tmp_path) -> None:
    bundle = tmp_path / "bundle"

    build_proof_bundle(bundle, _minimal_artifacts())

    result = verify_proof_bundle(bundle)

    assert result.valid is True
    assert result.failures == ()
    assert result.offline is True
    assert result.read_only is True
