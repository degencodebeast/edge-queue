import subprocess
import sys

from edgequeue.proof_bundle import build_proof_bundle


def test_judge_adjudicate_and_verify_help_interfaces_are_available() -> None:
    for command in ("judge", "adjudicate", "verify"):
        result = subprocess.run(
            [sys.executable, "-m", "edgequeue.cli", command, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert command in result.stdout


def test_root_help_lists_frozen_commands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert all(command in result.stdout for command in ("judge", "adjudicate", "verify"))


def test_verify_prints_a_machine_readable_offline_result(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    digest = "a" * 64
    build_proof_bundle(
        bundle,
        {
            "evaluation-configuration.json": {"corpus_digest": digest, "split": "DEV", "split_digest": digest, "review_budget": 1, "calibration_pack_version": None},
            "ranker-cases.jsonl": [{"case_id": "EQ-F01-DEV-01", "split": "DEV", "current_verdict": "PASS"}],
            "scorer-cases.jsonl": [{"case_id": "EQ-F01-DEV-01", "reference_verdict": "FAIL", "scorer_sentinel": "scorer-only-01"}],
            "baseline-rankings.json": {"random": ["EQ-F01-DEV-01"]},
            "edgequeue-ranking.json": {"review_queue": ["EQ-F01-DEV-01"]},
            "allocation-receipt.json": {"corpus_digest": digest, "split_digest": digest, "review_budget": 1, "review_queue": ["EQ-F01-DEV-01"]},
            "adjudications.jsonl": [],
            "metrics.json": {"recall_at_k": 1.0, "precision_at_k": 1.0},
            "claims-manifest.json": {"claims": [{"metric": "recall_at_k", "value": 1.0, "supporting_artifact": "metrics.json"}]},
        },
    )

    result = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "verify", str(bundle), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"valid":true' in result.stdout
