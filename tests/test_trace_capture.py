from pathlib import Path

from edgequeue.trace_capture import codex_exec_command


def test_builds_a_read_only_jsonl_codex_command() -> None:
    command = codex_exec_command(
        schema_path=Path("schemas/case-assessment.schema.json"),
        final_output_path=Path("runs/case-a/final.json"),
        model="gpt-5.6-luna",
        reasoning_effort="low",
    )

    assert command[0:2] == ("codex", "exec")
    assert "--json" in command
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--output-schema") + 1] == "schemas/case-assessment.schema.json"
    assert command[command.index("--output-last-message") + 1] == "runs/case-a/final.json"
    assert command[-1] == "-"
