"""Codex execution and trace capture for EdgeQueue Case Assessments."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from edgequeue.corpus import RankerCase
from edgequeue.prompting import render_case_assessment_prompt


@dataclass(frozen=True)
class TraceBundle:
    case_id: str
    attempt: int
    directory: Path
    prompt_path: Path
    events_path: Path
    final_output_path: Path
    stderr_path: Path
    metadata_path: Path
    return_code: int
    elapsed_seconds: float


def codex_exec_command(
    *,
    schema_path: Path,
    final_output_path: Path,
    model: str,
    reasoning_effort: str,
) -> tuple[str, ...]:
    """Build the read-only Codex command that emits JSONL thread events."""
    return (
        "codex",
        "exec",
        "--ignore-user-config",
        "--disable",
        "plugins",
        "--disable",
        "skill_search",
        "--disable",
        "apps",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--json",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(final_output_path),
        "-",
    )


def run_case_assessment(
    case: RankerCase,
    *,
    project_root: Path,
    trace_root: Path,
    schema_path: Path,
    model: str,
    reasoning_effort: str,
    attempt: int = 1,
) -> TraceBundle:
    """Run one Case Assessment and save its complete trace bundle."""
    directory = trace_root / case.case_id / f"attempt-{attempt:02d}"
    directory.mkdir(parents=True, exist_ok=True)
    prompt_path = directory / "prompt.txt"
    events_path = directory / "events.jsonl"
    final_output_path = directory / "final.json"
    stderr_path = directory / "stderr.txt"
    metadata_path = directory / "metadata.json"
    prompt = render_case_assessment_prompt(case)
    prompt_path.write_text(prompt, encoding="utf-8")
    command = codex_exec_command(
        schema_path=schema_path,
        final_output_path=final_output_path,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    started = time.time()
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        cwd=project_root,
        check=False,
    )
    elapsed_seconds = time.time() - started
    events_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "case_id": case.case_id,
                "attempt": attempt,
                "command": command,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "return_code": completed.returncode,
                "elapsed_seconds": elapsed_seconds,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TraceBundle(
        case_id=case.case_id,
        attempt=attempt,
        directory=directory,
        prompt_path=prompt_path,
        events_path=events_path,
        final_output_path=final_output_path,
        stderr_path=stderr_path,
        metadata_path=metadata_path,
        return_code=completed.returncode,
        elapsed_seconds=elapsed_seconds,
    )
