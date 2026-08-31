"""Public CLI checks for the Ticket 22 submission package."""

from __future__ import annotations

import subprocess
import sys
import zipfile
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_script(script_name: str, *arguments: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run a submission CLI through its supported command-line interface."""
    return subprocess.run(
        [sys.executable, f"scripts/{script_name}", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_submission_validator_rejects_stale_broad_claim(tmp_path: Path) -> None:
    """The public validator rejects the retracted 0.80 holdout result."""
    readme = tmp_path / "README.md"
    readme.write_text("Allocation Holdout Recall@8 was 0.80.", encoding="utf-8")

    result = run_script("verify_submission.py", "--text", str(readme))

    assert result.returncode == 1
    assert "stale_claim" in result.stdout


def test_submission_validator_accepts_the_complete_package() -> None:
    """The public validator accepts the checked-in qualification package."""
    result = run_script("verify_submission.py", "--project-root", str(PROJECT_ROOT))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "submission-check: pass" in result.stdout


def test_release_builder_creates_identical_sha_bound_archives(tmp_path: Path) -> None:
    """The public archive CLI reads one commit and excludes repository metadata."""
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = run_script(
        "build_release.py", "--sha", source_sha, "--output-dir", str(first)
    )
    second_result = run_script(
        "build_release.py", "--sha", source_sha, "--output-dir", str(second)
    )

    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    assert second_result.returncode == 0, second_result.stdout + second_result.stderr
    first_archive = next(first.glob("*.zip"))
    second_archive = next(second.glob("*.zip"))
    assert first_archive.read_bytes() == second_archive.read_bytes()
    with zipfile.ZipFile(first_archive) as archive:
        names = archive.namelist()
        assert "RELEASE_MANIFEST.json" in names
        assert all(
            not name.startswith((".git/", ".venv/", "runs/", "docs/evidence/ticket-20/traces/"))
            for name in names
        )
        assert "docs/evidence/ticket-20/claims.json" in names
        assert "docs/evidence/ticket-20/frozen-traces/EQ-F01-AH-01/attempt-01/metadata.json" in names
        assert "docs/evidence/ticket-21/artifacts/video-data.json" in names
        assert source_sha in archive.read("RELEASE_MANIFEST.json").decode("utf-8")


def test_trajectory_export_covers_ledger_sources_and_redacts_private_values(tmp_path: Path) -> None:
    """The public exporter keeps meaningful events while removing private strings."""
    raw_events = tmp_path / "rollout-01a00000-0000-0000-0000-000000000000.jsonl"
    raw_events.write_text(
        '{"type":"response_item","payload":{"text":"Use /Users/alice/private and sk-secret-value","rate_limits":{"credits":{"balance":12}},"last_token_usage":99,"encrypted_content":"private blob","approved_command_prefixes":["curl -H apikey: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"]}}\n',
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "| Agent | Role | Scope | Pane | Source | Export status |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"| Worker session `01a00000-0000-0000-0000-000000000000` | Worker | Fixture | `worker` | `{raw_events}` | pending |\n"
        "| Internal reviewers | Internal review | Fixture | Worker subagents | Worker source `01a00000-0000-0000-0000-000000000000` records reviewer identifiers. | pending |\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "trajectories"

    result = run_script(
        "export_trajectories.py", "--ledger", str(ledger), "--output-dir", str(output_dir)
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((output_dir / "trace-manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_count"] == 2
    assert manifest["ledger_entry_count"] == 2
    assert "Internal reviewers" in {entry["agent"] for entry in manifest["ledger_entries"]}
    assert {record["role"] for record in manifest["records"]} == {"Worker", "Internal review"}
    exported = next(output_dir.glob("*.md")).read_text(encoding="utf-8")
    assert "<USER_HOME>" in exported
    assert "sk-secret-value" not in exported
    assert "rate_limits" not in exported
    assert "last_token_usage" not in exported
    assert "encrypted_content" not in exported
    assert "approved_command_prefixes" not in exported
    assert "eyJhbGciOiJIUzI1NiJ9" not in exported
