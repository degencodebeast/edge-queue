"""Regression coverage for the public scorer-leakage command."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_leakage_check_scans_current_frozen_evidence(tmp_path: Path) -> None:
    """The release command scans all frozen Holdout trace files."""
    # Regression: the source archive excludes historical runs, so the public
    # command scanned zero files and returned a meaningless clean result.
    # Found by /qa on 2026-09-01.
    project_root = tmp_path / "project"
    (project_root / "scripts").mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "scripts" / "check_holdout_leakage.py",
        project_root / "scripts" / "check_holdout_leakage.py",
    )
    evidence_root = project_root / "docs" / "evidence" / "ticket-20"
    evidence_root.parent.mkdir(parents=True)
    shutil.copytree(PROJECT_ROOT / "docs" / "evidence" / "ticket-20", evidence_root)
    environment = os.environ | {"PYTHONPATH": str(PROJECT_ROOT / "src")}

    result = subprocess.run(
        [sys.executable, "scripts/check_holdout_leakage.py"],
        cwd=project_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "checked_files=600 leakage=none\n"
