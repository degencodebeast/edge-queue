"""Validate public claims and required Ticket 22 submission artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


STALE_CLAIMS = ("Recall@8 was 0.80", "Recall at 8: 0.80", "Recall@8 = 0.80")
REQUIRED_PATHS = (
    "README.md",
    "IMPROVEMENT_CHANGELOG.md",
    "REPRODUCTION.md",
    "PREEXISTING.md",
    ".env.example",
    "docs/submission/submission.md",
    "docs/submission/submission.html",
    "docs/submission/video-production.md",
    "docs/trajectories/trace-manifest.json",
    "docs/evidence/ticket-22/submission-readiness.md",
)
PUBLIC_TEXT_PATHS = (
    "README.md",
    "REPRODUCTION.md",
    "PREEXISTING.md",
    "docs/submission/submission.md",
    "docs/submission/submission.html",
    "docs/submission/video-production.md",
)
TOKEN_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,})\b")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")
HOME_PATH_PATTERN = re.compile(r"/Users/[A-Za-z0-9._-]+(?:/|$)")
PRIVATE_PATH_PATTERN = re.compile(r"/private/(?:var|tmp)/[^\\\"'`\s,;|]+")
PRIVATE_ASSIGNMENT = re.compile(r"(?i)^(?:api[_-]?key|token|password|secret)\s*=\s*\S+")
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")
VIDEO_DURATION = re.compile(
    r"(?im)^\s*(?:target\s+)?duration:\s*\**(\d+)\s+minutes?\s+(\d+)\s+seconds?\**\.?\s*$"
)


def duration_at_or_below_five_minutes(video_text: str) -> bool:
    """Accept one declared video duration that does not exceed five minutes."""
    match = VIDEO_DURATION.search(video_text)
    if match is None:
        return False
    minutes, seconds = (int(value) for value in match.groups())
    return seconds < 60 and minutes * 60 + seconds <= 5 * 60


def load_json(path: Path) -> object:
    """Load a required JSON record with a concise validation error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid_json: {path}: {error}") from error


def check_claim_sources(project_root: Path) -> list[str]:
    """Require exact values from the two authoritative public claim sources."""
    errors: list[str] = []
    broad = load_json(project_root / "docs/evidence/ticket-20/claims.json")
    broad_manifest = load_json(project_root / "docs/evidence/ticket-20/claims-manifest.json")
    judge = load_json(project_root / "docs/evidence/ticket-21/artifacts/proof-bundle/claims.json")
    judge_manifest = load_json(project_root / "docs/evidence/ticket-21/artifacts/proof-bundle/claims-manifest.json")
    summary = load_json(project_root / "docs/evidence/ticket-21/artifacts/summary.json")
    if not isinstance(broad, list) or not broad or broad[0].get("value") != 0.3:
        errors.append("claim_source: broad Allocation Holdout claim must equal Recall@8 0.30")
    if not isinstance(broad_manifest, dict) or not broad_manifest.get("evaluation_run_digest"):
        errors.append("claim_source: broad Claims Manifest is incomplete")
    if not isinstance(judge, list) or not judge or judge[0].get("value") != 1.0:
        errors.append("claim_source: Judge Fixture claim must equal Recall@1 1.00")
    if not isinstance(judge_manifest, dict) or not judge_manifest.get("evaluation_run_digest"):
        errors.append("claim_source: Judge Fixture Claims Manifest is incomplete")
    if not isinstance(summary, dict) or summary.get("baseline", {}).get("metrics", {}).get("recall_at_k") != 0.0:
        errors.append("claim_source: Judge Fixture baseline must equal Recall@1 0.00")
    return errors


def check_trajectories(project_root: Path) -> list[str]:
    """Check ledger coverage, readable records, raw excerpts, and redaction."""
    errors: list[str] = []
    directory = project_root / "docs/trajectories"
    manifest = load_json(directory / "trace-manifest.json")
    if not isinstance(manifest, dict):
        return ["trajectory_coverage: trace manifest must be an object"]
    records = manifest.get("records")
    if not isinstance(records, list) or manifest.get("source_count") != len(records) or not records:
        return ["trajectory_coverage: trace manifest source count is invalid"]
    roles = {record.get("role") for record in records if isinstance(record, dict)}
    if not {"Controller", "Worker", "Gate", "Internal review"} <= roles:
        errors.append("trajectory_coverage: required agent roles are missing")
    for record in records:
        if not isinstance(record, dict):
            errors.append("trajectory_coverage: invalid trace record")
            continue
        for field in ("readable_path", "raw_excerpt_path"):
            value = record.get(field)
            if not isinstance(value, str) or not (directory / value).is_file():
                errors.append(f"trajectory_coverage: missing {field}")
    ledger_entries = manifest.get("ledger_entries")
    if not isinstance(ledger_entries, list) or manifest.get("ledger_entry_count") != len(ledger_entries):
        errors.append("trajectory_coverage: ledger binding is invalid")
    else:
        exported_agents = {(record.get("agent"), record.get("role")) for record in records if isinstance(record, dict)}
        for entry in ledger_entries:
            if not isinstance(entry, dict) or (entry.get("agent"), entry.get("role")) not in exported_agents:
                errors.append("trajectory_coverage: a ledger entry has no exported record")
                break
    return errors


def check_private_data(project_root: Path) -> list[str]:
    """Reject secrets and unredacted home paths from tracked package content."""
    errors: list[str] = []
    for path in project_root.rglob("*"):
        relative = path.relative_to(project_root)
        excluded_legacy_trace = relative.parts[:1] == ("runs",) or relative.parts[:4] == ("docs", "evidence", "ticket-20", "traces")
        if not path.is_file() or excluded_legacy_trace or any(part in {".git", ".venv", "__pycache__", ".pytest_cache", "tests"} for part in path.parts):
            continue
        if path.suffix in {".pyc", ".zip"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if HOME_PATH_PATTERN.search(content):
            errors.append(f"private_data: user-home path in {path.relative_to(project_root)}")
        if PRIVATE_PATH_PATTERN.search(content):
            errors.append(f"private_data: private local path in {path.relative_to(project_root)}")
        if TOKEN_PATTERN.search(content) or JWT_PATTERN.search(content):
            errors.append(f"secret: token-like value in {path.relative_to(project_root)}")
        if path.name == ".env.example" and any(PRIVATE_ASSIGNMENT.match(line) for line in content.splitlines()):
            errors.append("secret: .env.example must contain no values")
    return errors


def check_public_text(project_root: Path) -> list[str]:
    """Reject retracted claims and check local Markdown links in public text."""
    errors: list[str] = []
    for relative in PUBLIC_TEXT_PATHS:
        path = project_root / relative
        content = path.read_text(encoding="utf-8")
        if any(stale_claim in content for stale_claim in STALE_CLAIMS):
            errors.append(f"stale_claim: rejected retracted Allocation Holdout Recall@8 = 0.80 in {relative}")
        for link in MARKDOWN_LINK.findall(content):
            if "://" in link or link.startswith("mailto:"):
                continue
            if not (path.parent / link).resolve().exists():
                errors.append(f"broken_link: {relative} -> {link}")
    return errors


def validate_package(project_root: Path) -> list[str]:
    """Validate the complete submission package through stable public artifacts."""
    errors = [f"required_file: {relative}" for relative in REQUIRED_PATHS if not (project_root / relative).is_file()]
    if errors:
        return errors
    errors.extend(check_claim_sources(project_root))
    errors.extend(check_trajectories(project_root))
    errors.extend(check_private_data(project_root))
    errors.extend(check_public_text(project_root))
    video_data = load_json(project_root / "docs/evidence/ticket-21/artifacts/video-data.json")
    video_text = (project_root / "docs/submission/video-production.md").read_text(encoding="utf-8")
    if not isinstance(video_data, dict) or str(video_data.get("fixture_path")) not in video_text:
        errors.append("video_binding: video plan must name the Ticket 21 fixture path")
    if not duration_at_or_below_five_minutes(video_text):
        errors.append("video_duration: plan must state a duration at or below five minutes")
    return errors


def main() -> int:
    """Run the submission validator CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", type=Path, help="Check one public text file for retracted claims.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    if arguments.text is not None:
        content = arguments.text.read_text(encoding="utf-8")
        if any(stale_claim in content for stale_claim in STALE_CLAIMS):
            print("stale_claim: rejected retracted Allocation Holdout Recall@8 = 0.80")
            return 1
        print("submission-check: pass")
        return 0
    errors = validate_package(arguments.project_root.resolve())
    if errors:
        print("submission-check: fail")
        print("\n".join(errors))
        return 1
    print("submission-check: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
