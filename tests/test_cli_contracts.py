import subprocess
import sys
import json
from pathlib import Path

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
            "metrics.json": {"recall_at_k": 1.0, "precision_at_k": 1.0, "false_negative_ids": [], "oracle_regret": 0},
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


def test_adjudicate_appends_one_local_authorized_record(tmp_path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures/ticket-18"
    manifest = json.loads((fixture_dir / "reviewer-manifest.json").read_text())
    context = json.loads((fixture_dir / "adjudication-context.json").read_text())
    ticket_16_input = json.loads(
        (Path(__file__).parent / "fixtures/ticket-16/fixed-batch-input.json").read_text()
    )
    receipt = json.loads(
        (Path(__file__).parents[1] / "docs/evidence/ticket-16/fixed-batch-allocation-receipt.json").read_text()
    )
    review_input = {
        "context": context,
        "ranker_case": ticket_16_input["ranker_cases"][0],
        "allocation_receipt": receipt,
    }
    manifest_path, input_path, history_path = (tmp_path / "manifest.json", tmp_path / "context.json", tmp_path / "history.jsonl")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    input_path.write_text(json.dumps(review_input), encoding="utf-8")
    evidence = json.dumps({"case_id": "EQ-F01-DEV-01", "event_id": "E1", "relation": "contradicts_current", "claim": "Verified event contradicts current Verdict.", "status": "verified"})

    result = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "adjudicate", "--case-id", "EQ-F01-DEV-01", "--reviewer-id", "human-1", "--decision", "correct", "--input", str(input_path), "--prior-record-digest", context["prior_record_digest"], "--reviewer-manifest", str(manifest_path), "--rationale", "Verified evidence supports correction.", "--evidence", evidence, "--resulting-verdict", "PASS", "--adjudication-id", "adj-cli-1", "--output", str(history_path)],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0
    record = json.loads(history_path.read_text())
    assert record["resulting_verdict"] == "PASS"
    assert record["prior_verdict"] == "FAIL"
