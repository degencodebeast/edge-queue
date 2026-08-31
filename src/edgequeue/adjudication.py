"""Append-only human Adjudications and conflict-safe canonical authority."""

from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Iterator, Literal, TextIO

import fcntl

from edgequeue.contracts import (
    ContractValidationError,
    canonical_json,
    digest_contract,
    validate_adjudication_authority,
    validate_resolution_adjudication,
)


Decision = Literal["preserve", "correct", "abstain"]


class AdjudicationError(ValueError):
    """An Adjudication cannot enter the append-only authority history."""


_CONTEXT_FIELDS = (
    "case_id",
    "prior_record_digest",
    "prior_verdict",
    "trajectory_digest",
    "allocation_receipt_digest",
    "corpus_digest",
    "split_digest",
    "rubric_version",
    "prompt_version",
    "feature_version",
    "model_config_digest",
    "evaluation_config_digest",
)


def create_adjudication(
    *,
    context: Mapping[str, str],
    reviewer_manifest: Mapping[str, Any],
    reviewer_id: str,
    action: Decision,
    resulting_verdict: str,
    rationale: str,
    evidence_references: Sequence[Mapping[str, Any]],
    adjudication_id: str,
) -> Mapping[str, Any]:
    """Create one human decision bound to frozen inputs without writing it."""
    missing = [field for field in _CONTEXT_FIELDS if not isinstance(context.get(field), str)]
    if missing:
        raise AdjudicationError(f"Adjudication context omits: {', '.join(missing)}")
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "adjudication_id": adjudication_id,
        "case_id": context["case_id"],
        "action": action,
        "prior_record_digest": context["prior_record_digest"],
        "prior_verdict": context["prior_verdict"],
        "resulting_verdict": resulting_verdict,
        "rationale": rationale,
        "reviewer_id": reviewer_id,
        "reviewer_role": "reviewer",
        "reviewer_manifest_version": reviewer_manifest.get("version"),
        "reviewer_manifest_digest": reviewer_manifest.get("content_digest"),
        "trajectory_schema_version": "1.0",
        "trajectory_digest": context["trajectory_digest"],
        "allocation_receipt_schema_version": "1.0",
        "allocation_receipt_digest": context["allocation_receipt_digest"],
        "evidence_references": [dict(reference) for reference in evidence_references],
        "corpus_digest": context["corpus_digest"],
        "split_digest": context["split_digest"],
        "rubric_version": context["rubric_version"],
        "prompt_version": context["prompt_version"],
        "feature_version": context["feature_version"],
        "model_config_digest": context["model_config_digest"],
        "evaluation_config_digest": context["evaluation_config_digest"],
        "predecessor_digest": context["prior_record_digest"],
    }
    try:
        validate_adjudication_authority(record, reviewer_manifest)
    except ContractValidationError as error:
        raise AdjudicationError(str(error)) from error
    return record


def read_adjudication_history(history_path: Path) -> tuple[Mapping[str, Any], ...]:
    """Read canonical JSONL records without changing the append-only history."""
    if not history_path.exists():
        return ()
    try:
        return tuple(json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line)
    except json.JSONDecodeError as error:
        raise AdjudicationError("Adjudication history is not valid JSONL") from error


def append_adjudication(
    history_path: Path,
    adjudication: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Authorize and append one record without replacing any earlier record."""
    with _locked_history(history_path) as (history, handle):
        _validate_history((*history, adjudication))
        try:
            validate_adjudication_authority(adjudication, reviewer_manifest)
        except ContractValidationError as error:
            raise AdjudicationError(str(error)) from error
        _append_manifest(history_path, reviewer_manifest)
        _write_record(handle, adjudication)
    return adjudication


def append_resolution_adjudication(
    history_path: Path,
    resolution: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
    branch_manifests: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Append an authorized resolution for every recorded competing branch."""
    with _locked_history(history_path) as (history, handle):
        _validate_history((*history, resolution))
        branches = [
            record
            for record in history
            if record.get("case_id") == resolution.get("case_id")
            and record.get("prior_record_digest") == resolution.get("prior_record_digest")
            and "conflict_adjudication_digests" not in record
        ]
        try:
            validate_resolution_adjudication(
                resolution, branches, reviewer_manifest, branch_manifests
            )
        except ContractValidationError as error:
            raise AdjudicationError(str(error)) from error
        _append_manifest(history_path, reviewer_manifest)
        _write_record(handle, resolution)
    return resolution


def canonical_verdict(
    *,
    prior_verdict: str,
    prior_record_digest: str,
    case_id: str,
    history: Sequence[Mapping[str, Any]],
    reviewer_manifests: Sequence[Mapping[str, Any]] = (),
) -> str | None:
    """Return the human-authorized Verdict, or ``None`` while a conflict remains."""
    manifests_by_digest = {
        manifest.get("content_digest"): manifest for manifest in reviewer_manifests
    }
    branches = [
        record
        for record in history
        if record.get("case_id") == case_id
        and record.get("prior_record_digest") == prior_record_digest
        and record.get("action") in {"preserve", "correct", "abstain"}
        and "conflict_adjudication_digests" not in record
        and _is_authorized(record, manifests_by_digest)
    ]
    if not branches:
        return prior_verdict
    results = {record.get("resulting_verdict") for record in branches}
    if len(branches) == 1:
        return next(iter(results))
    branch_digests = {digest_contract("adjudication", branch) for branch in branches}
    resolutions = [
        record
        for record in history
        if record.get("case_id") == case_id
        and record.get("prior_record_digest") == prior_record_digest
        and set(record.get("conflict_adjudication_digests", [])) == branch_digests
        and _is_authorized(record, manifests_by_digest)
    ]
    if not resolutions:
        return None
    return str(resolutions[-1].get("resulting_verdict"))


def _validate_history(history: Sequence[Mapping[str, Any]]) -> None:
    identifiers: set[str] = set()
    for record in history:
        identifier = record.get("adjudication_id")
        if not isinstance(identifier, str) or identifier in identifiers:
            raise AdjudicationError("Adjudication history has an invalid or duplicate identifier")
        identifiers.add(identifier)


def _append_record(history_path: Path, record: Mapping[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(record))
        handle.write("\n")


@contextmanager
def _locked_history(history_path: Path) -> Iterator[tuple[tuple[Mapping[str, Any], ...], TextIO]]:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            history = tuple(json.loads(line) for line in handle if line.strip())
            yield history, handle
        except json.JSONDecodeError as error:
            raise AdjudicationError("Adjudication history is not valid JSONL") from error
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_record(handle: TextIO, record: Mapping[str, Any]) -> None:
    handle.seek(0, 2)
    handle.write(canonical_json(record))
    handle.write("\n")
    handle.flush()


def _append_manifest(history_path: Path, manifest: Mapping[str, Any]) -> None:
    manifest_path = history_path.with_name(f"{history_path.stem}-reviewer-manifests.jsonl")
    existing = read_adjudication_history(manifest_path)
    digest = manifest.get("content_digest")
    if any(record.get("content_digest") == digest for record in existing):
        return
    try:
        from edgequeue.contracts import validate_contract

        validate_contract("reviewer_manifest", manifest)
    except ContractValidationError as error:
        raise AdjudicationError(str(error)) from error
    _append_record(manifest_path, manifest)


def _is_authorized(
    record: Mapping[str, Any], manifests_by_digest: Mapping[Any, Mapping[str, Any]]
) -> bool:
    manifest = manifests_by_digest.get(record.get("reviewer_manifest_digest"))
    if manifest is None:
        return False
    try:
        validate_adjudication_authority(record, manifest)
    except ContractValidationError:
        return False
    return True
