"""End-to-end checks for the frozen four-case Judge Fixture."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from edgequeue.contracts import content_digest
from edgequeue.judge import JudgeFixtureError, load_judge_fixture
from edgequeue.corpus import freeze_complete_corpus


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "corpus/fixtures/judge-fixture-v1.json"


def test_freeze_emits_the_checked_in_four_case_judge_fixture(tmp_path: Path) -> None:
    """The public Corpus Freeze seam must reproduce the judge fixture exactly."""
    expected = {
        "fixture_id": "judge-fixture-v1",
        "split": "DEV",
        "review_budget": 1,
        "cases": [
            {"case_id": "EQ-F01-DEV-01", "role": "confident_label_error"},
            {"case_id": "EQ-F02-DEV-01", "role": "misleading_hard_control"},
            {"case_id": "EQ-F01-DEV-02", "role": "ordinary_control"},
            {"case_id": "EQ-F02-DEV-02", "role": "ordinary_control"},
        ],
    }

    freeze_complete_corpus(tmp_path / "frozen-corpus")
    generated = json.loads(
        (tmp_path / "frozen-corpus/fixtures/judge-fixture-v1.json").read_text(
            encoding="utf-8"
        )
    )
    checked_in = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert checked_in == expected
    assert generated == expected


def test_judge_fixture_requires_the_exact_four_case_roles() -> None:
    """Reject a fixture that has no misleading Hard Control."""
    path = ROOT / "tests/fixtures/ticket-21/invalid-role-count.json"

    with pytest.raises(JudgeFixtureError, match="misleading_hard_control"):
        load_judge_fixture(path)


def test_judge_cli_runs_offline_and_proves_the_complete_fixture(tmp_path: Path) -> None:
    """Run the public judge command and assert its independently visible results."""
    output_dir = tmp_path / "judge-output"
    result = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "judge", "--output-dir", str(output_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Baseline deterministic_only: EQ-F02-DEV-01" in result.stdout
    assert "EdgeQueue: EQ-F01-DEV-01" in result.stdout
    assert "Calibration Candidate: accepted; not promoted; no PCH claim" in result.stdout
    assert "Proof Bundle: valid" in result.stdout
    assert "Tamper result: metric_recomputation_mismatch" in result.stdout
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["offline_replay"]["model_cost_usd"] == 0.0
    assert summary["requests"] == 0
    assert summary["tokens"] == 0
    assert summary["calibration"]["promotion_status"] == "not_promoted"
    assert (output_dir / "review-packet.html").is_file()
    assert (output_dir / "proof-bundle" / "manifest.json").is_file()
    assert "metric_recomputation_mismatch" in summary["tamper_verification"]["failure_codes"]
    calibration = json.loads((output_dir / "calibration.json").read_text(encoding="utf-8"))
    assert calibration["comparisons"]["DEV"]["case_count"] == 20
    assert calibration["comparisons"]["AH"]["case_count"] == 40
    assert calibration["comparisons"]["AH"]["candidate_recall_at_k"] == 0.4
    assert calibration["comparisons"]["DEV"]["candidate_review_queue"] == [
        "EQ-F01-DEV-01",
        "EQ-F03-DEV-01",
        "EQ-F05-DEV-01",
        "EQ-F07-DEV-01",
    ]
    assert calibration["controls"]["model_digest"] != "1" * 64
    assert calibration["controls"]["scorer_digest"] != "2" * 64
    assert calibration["controls"]["metrics_digest"] != "3" * 64
    assert calibration["controls"]["post_calibration_holdout_digest"] != "4" * 64
    evaluation_run = json.loads(
        (output_dir / "proof-bundle/evaluation-run.json").read_text(encoding="utf-8")
    )
    assert evaluation_run["code_commit"] != "offline-fixture"
    assert evaluation_run["git_tree"] != "offline-fixture"
    video_data = json.loads((output_dir / "video-data.json").read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert video_data["fixture_digest"] == content_digest(fixture)
    assert video_data["summary_digest"] == content_digest(summary)
    assert video_data["artifact_paths_digest"] == content_digest(summary["artifact_paths"])
    assert video_data["command_output_digest"] == sha256(
        (output_dir / "command-output.txt").read_bytes()
    ).hexdigest()
    rerun = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "judge", "--output-dir", str(output_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rerun.returncode == 0, rerun.stderr


def test_judge_live_route_records_unavailable_provider_without_proof(tmp_path: Path) -> None:
    """The separate live route records its unavailable provider state offline."""
    output_dir = tmp_path / "live-output"
    result = subprocess.run(
        [sys.executable, "-m", "edgequeue.cli", "judge", "--live", "--output-dir", str(output_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    record = json.loads((output_dir / "live-run.json").read_text(encoding="utf-8"))
    assert record["status"] == "unavailable"
    assert record["request_count"] == 0
    assert not (output_dir / "proof-bundle").exists()


def test_judge_fixture_does_not_open_network_connections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-process Offline Replay must not access the network."""
    from edgequeue.judge import run_judge_fixture

    def fail_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("Offline Replay must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = run_judge_fixture(FIXTURE, tmp_path / "judge-output")

    assert result.request_count == 0
    assert result.token_count == 0
    assert result.model_cost_usd == 0.0
