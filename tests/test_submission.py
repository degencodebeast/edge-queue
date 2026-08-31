"""Public CLI checks for the Ticket 22 submission package."""

from __future__ import annotations

import subprocess
import sys
import zipfile
import json
import os
import hashlib
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
    """The archive binds an extracted judge replay to its declared source tree."""
    if not (PROJECT_ROOT / ".git").exists():
        _assert_release_manifest(PROJECT_ROOT)
        return

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
        manifest = json.loads(archive.read("RELEASE_MANIFEST.json"))
        assert manifest["source_sha"] == source_sha
        _assert_release_manifest_values(manifest)
        assert any(entry["path"] == "src/edgequeue/judge.py" for entry in manifest["files"])
        extracted = tmp_path / "extracted"
        archive.extractall(extracted)

    _assert_release_manifest(extracted)

    judge_output = extracted / "judge-output"
    environment = os.environ | {
        "PYTHONPATH": str(extracted / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
    }
    edgequeue_command = str(Path(sys.executable).with_name("edgequeue"))
    extracted_result = subprocess.run(
        [edgequeue_command, "judge", "--output-dir", str(judge_output)],
        cwd=extracted,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert extracted_result.returncode == 0, extracted_result.stdout + extracted_result.stderr
    evaluation_run = json.loads((judge_output / "proof-bundle/evaluation-run.json").read_text(encoding="utf-8"))
    assert evaluation_run["code_commit"] == source_sha
    assert evaluation_run["git_tree"] == manifest["source_tree"]
    assert evaluation_run["dirty_state"] is False

    judge_source = extracted / "src/edgequeue/judge.py"
    judge_source.write_bytes(judge_source.read_bytes() + b"\n")
    tampered_result = subprocess.run(
        [edgequeue_command, "judge", "--output-dir", str(extracted / "tampered-output")],
        cwd=extracted,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert tampered_result.returncode == 2
    assert "Release manifest digest mismatch: src/edgequeue/judge.py" in tampered_result.stderr


def _assert_release_manifest(project_root: Path) -> None:
    """Validate the self-contained source binding in an extracted package."""
    manifest = json.loads((project_root / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    _assert_release_manifest_values(manifest)
    files = manifest["files"]
    assert manifest["tracked_file_count"] == len(files)
    paths: set[str] = set()
    for entry in files:
        path_text = entry["path"]
        digest = entry["sha256"]
        relative_path = Path(path_text)
        assert not relative_path.is_absolute()
        assert ".." not in relative_path.parts
        assert path_text not in paths
        paths.add(path_text)
        assert len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)
        assert hashlib.sha256((project_root / relative_path).read_bytes()).hexdigest() == digest


def _assert_release_manifest_values(manifest: dict[str, object]) -> None:
    """Validate required release identity fields before archive-specific checks."""
    for field in ("source_sha", "source_tree"):
        value = manifest[field]
        assert isinstance(value, str)
        assert len(value) == 40 and all(character in "0123456789abcdef" for character in value)
    assert isinstance(manifest["tracked_file_count"], int)
    assert isinstance(manifest["files"], list)


def test_trajectory_export_covers_ledger_sources_and_redacts_private_values(tmp_path: Path) -> None:
    """The public exporter keeps meaningful events while removing private strings."""
    raw_events = tmp_path / "rollout-01a00000-0000-0000-0000-000000000000.jsonl"
    synthetic_home = "/" + "Users" + "/alice/private"
    synthetic_token = "sk-" + "secret-value"
    synthetic_jwt = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiJ0ZXN0In0.signature"
    raw_events.write_text(
        '{"type":"response_item","payload":{"text":"Use '
        + synthetic_home
        + ' and '
        + synthetic_token
        + '","rate_limits":{"credits":{"balance":12}},"last_token_usage":99,"encrypted_content":"private blob","approved_command_prefixes":["curl -H apikey: '
        + synthetic_jwt
        + '"]}}\n',
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
    assert synthetic_token not in exported
    assert "rate_limits" not in exported
    assert "last_token_usage" not in exported
    assert "encrypted_content" not in exported
    assert "approved_command_prefixes" not in exported
    assert synthetic_jwt not in exported
