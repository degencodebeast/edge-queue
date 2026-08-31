"""Export readable, redacted agent trajectories from the EdgeQueue source ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_PATTERN = re.compile(r"/(?:Users|private)/[^` ;|]+\.jsonl")
SESSION_ID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}")
HOME_PATTERN = re.compile(r"/Users/\s*[^/\\\"\s]+")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
TOKEN_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,})\b")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")
APIKEY_PATTERN = re.compile(r"(?i)(?:api[_-]?key|authorization|bearer)\s*[:=]\s*(?:bearer\s+)?[^\s,;\"']+")
SECRET_VALUE_PATTERN = re.compile(
    r'(?i)("(?:api[_-]?key|token|password|secret|authorization)"\s*:\s*")[^"]+("|$)'
)
SIGNAL_WORDS = ("retry", "feedback", "checkpoint", "error", "failed", "blocker", "pass", "human")
PRIVATE_EVENT_FIELDS = {"account", "approved_command_prefixes", "balance", "billing", "credits", "encrypted_content", "last_token_usage", "model_context_window", "permission_profile", "permissions", "plan_type", "rate_limit", "rate_limits", "raw_content", "reset_at", "reset_seconds", "sandbox_policy", "total_token_usage", "world_state"}


@dataclass(frozen=True)
class LedgerSource:
    """One source record extracted from the agent trajectory ledger."""

    agent: str
    role: str
    scope: str
    pane: str
    source: Path


def redact_text(value: str) -> str:
    """Remove user-home paths, credentials, and personal addresses from text."""
    value = HOME_PATTERN.sub("<USER_HOME>", value)
    value = EMAIL_PATTERN.sub("<REDACTED_EMAIL>", value)
    value = TOKEN_PATTERN.sub("<REDACTED_TOKEN>", value)
    value = JWT_PATTERN.sub("<REDACTED_TOKEN>", value)
    value = APIKEY_PATTERN.sub("<REDACTED_SECRET>", value)
    return SECRET_VALUE_PATTERN.sub(r'\1<REDACTED_SECRET>\2', value)


def redact(value: Any) -> Any:
    """Recursively redact a JSON-compatible event value."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {
            redact_text(str(key)): redact(item)
            for key, item in value.items()
            if redact_text(str(key)).lower() not in PRIVATE_EVENT_FIELDS
        }
    return value


def compact(value: Any) -> Any:
    """Bound each raw-event excerpt while retaining its opening evidence."""
    if isinstance(value, str):
        return value[:6000] + ("… [excerpt truncated]" if len(value) > 6000 else "")
    if isinstance(value, list):
        return [compact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): compact(item) for key, item in value.items()}
    return value


def parse_ledger(ledger_path: Path) -> tuple[list[LedgerSource], list[dict[str, str]]]:
    """Parse source paths from the ledger's stable Markdown table."""
    rows: list[tuple[str, str, str, str, str]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] in {"Agent", "---"}:
            continue
        rows.append((cells[0], cells[1], cells[2], cells[3], cells[4]))
    sources: list[LedgerSource] = []
    source_by_session: dict[str, Path] = {}
    for agent, role, scope, pane, source_cell in rows:
        for source_text in SOURCE_PATTERN.findall(source_cell):
            source = Path(source_text)
            sources.append(
                LedgerSource(
                    agent=agent.strip("`"), role=role.strip("`"), scope=scope.strip("`"), pane=pane.strip("`"), source=source
                )
            )
            for session_id in SESSION_ID_PATTERN.findall(source_text):
                source_by_session[session_id] = source
    for agent, role, scope, pane, source_cell in rows:
        if SOURCE_PATTERN.search(source_cell):
            continue
        session_ids = SESSION_ID_PATTERN.findall(source_cell)
        if len(session_ids) == 1 and session_ids[0] in source_by_session:
            sources.append(
                LedgerSource(
                    agent=agent.strip("`"), role=role.strip("`"), scope=scope.strip("`"), pane=pane.strip("`"), source=source_by_session[session_ids[0]]
                )
            )
    if not sources:
        raise ValueError("No JSONL trajectory sources found in the ledger")
    entries = [
        {"agent": agent.strip("`"), "role": role.strip("`"), "scope": scope.strip("`"), "pane": pane.strip("`")}
        for agent, role, scope, pane, _ in rows
    ]
    return sources, entries


def load_events(source: Path) -> list[dict[str, Any]]:
    """Read JSONL events without retaining malformed private lines verbatim."""
    events: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            events.append({"type": "unparseable_event", "text": redact_text(line)})
            continue
        if isinstance(value, dict):
            events.append(compact(redact(value)))
    return events


def event_summary(event: dict[str, Any]) -> str:
    """Produce a short readable description while keeping raw excerpts separately."""
    event_type = str(event.get("type", "event"))
    raw = json.dumps(event, ensure_ascii=False, sort_keys=True)
    return raw[:800] + ("…" if len(raw) > 800 else "") if raw else event_type


def select_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep setup, action, feedback, retry, and completion evidence in a bounded excerpt."""
    if len(events) <= 80:
        return events
    selected_indices = set(range(60)) | set(range(max(60, len(events) - 20), len(events)))
    for index, event in enumerate(events):
        if any(word in event_summary(event).lower() for word in SIGNAL_WORDS):
            selected_indices.add(index)
    return [events[index] for index in sorted(selected_indices)[:120]]


def slug(value: str) -> str:
    """Create a stable safe file-name component."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "agent"


def write_export(record: LedgerSource, index: int, output_dir: Path) -> dict[str, object]:
    """Write one readable Markdown trajectory and its raw-event excerpt."""
    if not record.source.is_file():
        raise ValueError(f"Missing ledger source: {record.source}")
    raw_bytes = record.source.read_bytes()
    events = select_events(load_events(record.source))
    filename = f"trajectory-{index:02d}-{slug(record.agent)}"
    raw_path = output_dir / "raw" / f"{filename}.jsonl"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")
    readable_path = output_dir / f"{filename}.md"
    lines = [
        f"# {record.agent}",
        "",
        f"- Role: {record.role}",
        f"- Scope: {record.scope}",
        f"- Pane: {record.pane}",
        f"- Source digest: `{hashlib.sha256(raw_bytes).hexdigest()}`", 
        f"- Supporting raw-event excerpt: [`raw/{raw_path.name}`](raw/{raw_path.name})",
        "",
        "## Event excerpt",
        "",
    ]
    for event in events:
        lines.extend([f"### {event.get('type', 'event')}", "", event_summary(event), ""])
    readable_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "agent": record.agent,
        "role": record.role,
        "scope": record.scope,
        "pane": record.pane,
        "source_digest": hashlib.sha256(raw_bytes).hexdigest(),
        "event_count": len(events),
        "readable_path": readable_path.name,
        "raw_excerpt_path": str(Path("raw") / raw_path.name),
    }


def export(ledger_path: Path, output_dir: Path) -> Path:
    """Export every ledger source and return the trace manifest path."""
    records, ledger_entries = parse_ledger(ledger_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_records = [write_export(record, index, output_dir) for index, record in enumerate(records, start=1)]
    manifest = {
        "schema_version": "1.0",
        "ledger_digest": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "ledger_entry_count": len(ledger_entries),
        "ledger_entries": ledger_entries,
        "source_count": len(records),
        "records": manifest_records,
        "redaction": ["credentials", "private values", "user-home paths", "email addresses"],
    }
    manifest_path = output_dir / "trace-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    """Run the trajectory export CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        manifest_path = export(arguments.ledger, arguments.output_dir)
    except ValueError as error:
        print(f"trajectory-export: fail: {redact_text(str(error))}")
        return 1
    print(f"trajectory-export: pass manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
