import subprocess
import sys
from pathlib import Path


def test_built_wheel_imports_contracts_and_exposes_cli_help(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheel"
    build = subprocess.run(
        ["uv", "build", "--offline", "--wheel", "--out-dir", str(wheel_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    wheel = next(wheel_dir.glob("edgequeue-*.whl"))

    environment = tmp_path / "environment"
    create_environment = subprocess.run(
        [sys.executable, "-m", "venv", str(environment)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert create_environment.returncode == 0, create_environment.stderr
    python = environment / "bin" / "python"
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    imported = subprocess.run(
        [str(python), "-I", "-c", "import edgequeue.contracts"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr
    help_result = subprocess.run(
        [str(python), "-I", "-m", "edgequeue.cli", "judge", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
