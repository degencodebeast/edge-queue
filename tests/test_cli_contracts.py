import subprocess
import sys


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
