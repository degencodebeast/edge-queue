"""Preserve non-authoritative trace evidence for an EvaluationRun."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import AbstractSet, Any

from edgequeue.contracts import content_digest
from edgequeue.integrity import ScorerLeakageDetected, reject_scorer_leakage


class ScorerLeakageError(ValueError):
    """A submitted trace or allocation artifact exposes scorer-only content."""


def build_archived_trace_copy(
    *,
    prompt: str,
    events_jsonl: str,
    final_output: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy one archived trace and bind its exact source content by digest."""
    events = [json.loads(line) for line in events_jsonl.splitlines() if line]
    if not events:
        raise ValueError("Archived trace must contain at least one event")
    case_id = str(metadata["case_id"])
    if final_output.get("case_id") != case_id:
        raise ValueError("Archived final output must match the metadata case identifier")
    usage = _trace_usage(events)
    request_count = sum(event.get("type") == "turn.started" for event in events)
    return {
        "case_id": case_id,
        "prompt": prompt,
        "events": events,
        "events_jsonl": events_jsonl,
        "final_output": dict(final_output),
        "retries": [
            {
                "attempt": metadata["attempt"],
                "outcome": "accepted" if metadata["return_code"] == 0 else "execution_failure",
                "return_code": metadata["return_code"],
            }
        ],
        "runtime_seconds": metadata["elapsed_seconds"],
        "request_count": request_count,
        "token_count": usage["input_tokens"] + usage["output_tokens"],
        "token_usage": usage,
        "available_cost": metadata.get("available_cost"),
        "metadata": dict(metadata),
        "source_digests": {
            "prompt": content_digest(prompt),
            "events_jsonl": content_digest(events_jsonl),
            "final_output": content_digest(final_output),
            "metadata": content_digest(metadata),
        },
    }


def _trace_usage(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    completed = [
        event["usage"]
        for event in events
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), Mapping)
    ]
    if len(completed) != 1:
        raise ValueError("Archived trace must contain one completed-turn usage record")
    usage = completed[0]
    required = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    if any(not isinstance(usage.get(name), int) for name in required):
        raise ValueError("Archived trace usage is malformed")
    return {name: int(usage[name]) for name in required}


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
        "scorer_sentinel_digests": sorted(content_digest(sentinel) for sentinel in scorer_sentinels),
        "content_digest": "0" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    return manifest
