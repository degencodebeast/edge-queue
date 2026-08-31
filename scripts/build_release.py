"""Build a deterministic, SHA-bound source archive outside the repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


MAX_UPLOAD_BYTES = 50 * 1024 * 1024
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "secrets",
    "venv",
}
HOME_PATH_PATTERN = re.compile(rb"/Users/[A-Za-z0-9._-]+(?:/|$)")
TOKEN_PATTERN = re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,})\b")
JWT_PATTERN = re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")
PRIVATE_ASSIGNMENT = re.compile(rb"(?im)^(?:api[_-]?key|token|password|secret)\s*=\s*\S+")


def git(project_root: Path, *arguments: str) -> str:
    """Run Git in the selected project and return its UTF-8 output."""
    result = subprocess.run(
        ["git", "-C", str(project_root), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "Git command failed")
    return result.stdout


def is_excluded(relative_path: PurePosixPath) -> bool:
    """Return whether a tracked path is unsafe or irrelevant in a source archive."""
    if relative_path.parts[:1] == ("runs",):
        return True
    if relative_path.parts[:4] == ("docs", "evidence", "ticket-20", "traces"):
        return True
    if any(part in EXCLUDED_NAMES for part in relative_path.parts):
        return True
    if relative_path.name == ".env" or relative_path.suffix in {".key", ".p12", ".pem", ".pyc", ".zip"}:
        return True
    return relative_path.suffix == ".sha256"


def tracked_files(project_root: Path, source_sha: str) -> list[tuple[PurePosixPath, bytes]]:
    """Read archive input only from tracked blobs at one exact commit."""
    names = git(project_root, "ls-tree", "-r", "--name-only", "-z", source_sha).split("\0")
    files: list[tuple[PurePosixPath, bytes]] = []
    for name in sorted(item for item in names if item):
        relative_path = PurePosixPath(name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"Unsafe tracked path: {name}")
        if is_excluded(relative_path):
            continue
        payload = subprocess.run(
            ["git", "-C", str(project_root), "show", f"{source_sha}:{name}"],
            capture_output=True,
            check=False,
        )
        if payload.returncode != 0:
            raise ValueError(f"Cannot read tracked blob: {name}")
        if HOME_PATH_PATTERN.search(payload.stdout) or TOKEN_PATTERN.search(payload.stdout) or JWT_PATTERN.search(payload.stdout) or PRIVATE_ASSIGNMENT.search(payload.stdout):
            raise ValueError(f"Private value found outside approved legacy exclusions: {name}")
        files.append((relative_path, payload.stdout))
    return files


def canonical_json(value: object) -> bytes:
    """Create stable JSON for the generated release manifest."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def zip_info(name: str) -> zipfile.ZipInfo:
    """Create stable ZIP metadata without local timestamps or permissions."""
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_archive(project_root: Path, source_sha: str, output_dir: Path) -> tuple[Path, Path, str]:
    """Write one deterministic archive and its external SHA-256 sidecar."""
    resolved_sha = git(project_root, "rev-parse", "--verify", f"{source_sha}^{{commit}}").strip()
    if source_sha != resolved_sha:
        raise ValueError("--sha must be one exact 40-character commit SHA")
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(project_root.resolve()):
        raise ValueError("--output-dir must be outside the Git repository")
    output_dir.mkdir(parents=True, exist_ok=True)

    files = tracked_files(project_root, resolved_sha)
    manifest = {
        "archive_format": "edgequeue-source-v1",
        "source_sha": resolved_sha,
        "tracked_file_count": len(files),
        "files": [
            {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
            for path, payload in files
        ],
        "excluded": ["Git metadata", "environments", "caches", "bytecode", "secrets", "build outputs"],
        "legacy_excluded_prefixes": {
            "runs/**": "legacy path-bearing run records; current proof is under docs/evidence/ticket-20/",
            "docs/evidence/ticket-20/traces/**": "superseded path-bearing trace; current proof is under development-traces and frozen-traces",
        },
        "archive_checksum": "external SHA-256 sidecar; omitted to avoid a self-checksum cycle",
    }
    archive_path = output_dir / f"edgequeue-{resolved_sha[:12]}-source.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, payload in files:
            archive.writestr(zip_info(str(path)), payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        archive.writestr(
            zip_info("RELEASE_MANIFEST.json"),
            canonical_json(manifest),
            compress_type=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        )
    size = archive_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        archive_path.unlink()
        raise ValueError(f"Archive exceeds 50 MB upload limit: {size} bytes")
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    sidecar_path = archive_path.with_suffix(".zip.sha256")
    sidecar_path.write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, sidecar_path, checksum


def main() -> int:
    """Run the deterministic archive CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="Exact 40-character Git commit SHA.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Existing or new directory outside Git.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    try:
        archive_path, sidecar_path, checksum = build_archive(
            arguments.project_root.resolve(), arguments.sha, arguments.output_dir
        )
    except ValueError as error:
        print(f"release-build: fail: {error}")
        return 1
    print(f"release-build: pass source_sha={arguments.sha}")
    print(f"archive={archive_path} bytes={archive_path.stat().st_size}")
    print(f"checksum={checksum} sidecar={sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
