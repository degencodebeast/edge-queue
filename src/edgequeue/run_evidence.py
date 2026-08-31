"""Preserve non-authoritative trace evidence for an EvaluationRun."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import AbstractSet, Any

from edgequeue.contracts import content_digest
from edgequeue.integrity import ScorerLeakageDetected, reject_scorer_leakage


class ScorerLeakageError(ValueError):
    """A submitted trace or allocation artifact exposes scorer-only content."""


def reject_submitted_scorer_leakage(
    *,
    traces: Sequence[Mapping[str, Any]],
    allocation_artifacts: Sequence[Mapping[str, Any]] = (),
    forbidden_field_names: AbstractSet[str],
    scorer_sentinels: AbstractSet[str],
) -> None:
    """Reject all submitted allocator-visible trace and allocation artifacts."""
    try:
        reject_scorer_leakage(
            {"traces": list(traces), "allocation_artifacts": list(allocation_artifacts)},
            forbidden_field_names=forbidden_field_names,
            scorer_sentinels=scorer_sentinels,
        )
    except ScorerLeakageDetected as error:
        raise ScorerLeakageError(str(error)) from error


def build_trace_manifest(
    *,
    evaluation_run_digest: str,
    traces: Sequence[Mapping[str, Any]],
    forbidden_field_names: AbstractSet[str],
    scorer_sentinels: AbstractSet[str],
    allocation_artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Bind representative prompts, events, outputs, retries, and costs."""
    reject_submitted_scorer_leakage(
        traces=traces,
        allocation_artifacts=allocation_artifacts,
        forbidden_field_names=forbidden_field_names,
        scorer_sentinels=scorer_sentinels,
    )
    required = {
        "case_id",
        "prompt",
        "events",
        "final_output",
        "retries",
        "runtime_seconds",
        "request_count",
        "token_count",
        "available_cost",
        "metadata",
    }
    for trace in traces:
        missing = required - set(trace)
        if missing:
            raise ValueError(f"Trace is missing required fields: {sorted(missing)}")
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "evaluation_run_digest": evaluation_run_digest,
        "traces": [dict(trace) for trace in traces],
        "content_digest": "0" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    return manifest
