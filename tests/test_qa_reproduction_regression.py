"""Regression coverage for the public evaluation reproduction commands."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_scoring_reproduces_the_accepted_read_only_results(
    tmp_path: Path,
) -> None:
    """Public scoring uses current frozen evidence without rewriting archives."""
    # Regression: the documented scoring commands read superseded runs, printed
    # the removed 0.80 result, and rewrote two tracked evaluation artifacts.
    # Found by /qa on 2026-09-01.
    project_root = tmp_path / "project"
    (project_root / "scripts").mkdir(parents=True)
    for script_name in ("score_development.py", "score_allocation_holdout.py"):
        shutil.copy2(
            PROJECT_ROOT / "scripts" / script_name,
            project_root / "scripts" / script_name,
        )
    shutil.copytree(PROJECT_ROOT / "runs", project_root / "runs")
    evidence_root = project_root / "docs" / "evidence" / "ticket-20"
    evidence_root.parent.mkdir(parents=True)
    shutil.copytree(PROJECT_ROOT / "docs" / "evidence" / "ticket-20", evidence_root)

    archived_paths = (
        project_root / "runs" / "development" / "evaluation.json",
        project_root / "runs" / "allocation-holdout" / "evaluation.json",
    )
    before = {path: path.read_bytes() for path in archived_paths}
    environment = os.environ | {"PYTHONPATH": str(PROJECT_ROOT / "src")}

    development = subprocess.run(
        [sys.executable, "scripts/score_development.py"],
        cwd=project_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    holdout = subprocess.run(
        [sys.executable, "scripts/score_allocation_holdout.py"],
        cwd=project_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert development.returncode == 0, development.stdout + development.stderr
    assert holdout.returncode == 0, holdout.stdout + holdout.stderr
    development_result = json.loads(development.stdout)
    holdout_result = json.loads(holdout.stdout)
    observed = {
        "development_recall": development_result["edgequeue"]["metrics"]["recall_at_k"],
        "holdout_recalls": holdout_result["edgequeue_recalls"],
        "archived_runs_unchanged": all(
            path.read_bytes() == content for path, content in before.items()
        ),
    }

    assert observed == {
        "development_recall": 0.2,
        "holdout_recalls": [0.3, 0.4, 0.3],
        "archived_runs_unchanged": True,
    }
