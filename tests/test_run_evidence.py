import json
from pathlib import Path

import pytest

from edgequeue.contracts import content_digest, digest_contract
from edgequeue.run_evidence import (
    ScorerLeakageError,
    build_archived_trace_copy,
    build_trace_manifest,
)


def test_builds_a_trace_manifest_with_execution_accounting() -> None:
    manifest = build_trace_manifest(
        evaluation_run_digest=content_digest({"run": "20"}),
        traces=[
            {
                "case_id": "case-1",
                "prompt": "Assess the visible case evidence.",
                "events": [{"event": "tool_result", "content": "visible evidence"}],
                "final_output": {"status": "risk_finding"},
                "retries": [{"attempt": 1, "outcome": "timeout"}, {"attempt": 2, "outcome": "accepted"}],
                "runtime_seconds": 1.25,
                "request_count": 2,
                "token_count": 45,
                "available_cost": None,
                "metadata": {"model": "offline-fixture"},
            }
        ],
        forbidden_field_names={"reference_verdict", "scorer_sentinel"},
        scorer_sentinels=set(),
    )

    assert manifest["evaluation_run_digest"] == content_digest({"run": "20"})
    assert manifest["traces"][0]["request_count"] == 2
    assert manifest["traces"][0]["retries"][0]["outcome"] == "timeout"
    assert len(manifest["content_digest"]) == 64


def test_rejects_scorer_leakage_in_a_trace() -> None:
    with pytest.raises(ScorerLeakageError, match="SCORER_ONLY_CASE_1"):
        build_trace_manifest(
            evaluation_run_digest=content_digest({"run": "20"}),
            traces=[
                {
                    "case_id": "case-1",
                    "prompt": "SCORER_ONLY_CASE_1",
                    "events": [],
                    "final_output": {},
                    "retries": [],
                    "runtime_seconds": 0.0,
                    "request_count": 0,
                    "token_count": 0,
                    "available_cost": 0.0,
                    "metadata": {},
                }
            ],
            forbidden_field_names={"reference_verdict"},
            scorer_sentinels={"SCORER_ONLY_CASE_1"},
        )


def test_copies_the_archived_trace_with_its_real_accounting() -> None:
    root = Path("runs/allocation-holdout/EQ-F01-AH-01/attempt-01")
    trace = build_archived_trace_copy(
        prompt=root.joinpath("prompt.txt").read_text(encoding="utf-8"),
        events_jsonl=root.joinpath("events.jsonl").read_text(encoding="utf-8"),
        final_output=json.loads(root.joinpath("final.json").read_text(encoding="utf-8")),
        metadata=json.loads(root.joinpath("metadata.json").read_text(encoding="utf-8")),
    )

    assert trace["case_id"] == "EQ-F01-AH-01"
    assert trace["prompt"].startswith("You are the EdgeQueue allocator.")
    assert trace["events"][3]["item"]["type"] == "agent_message"
    assert trace["final_output"]["risk_score"] == 95
    assert trace["metadata"]["elapsed_seconds"] == 13.356252193450928
    assert trace["runtime_seconds"] == 13.356252193450928
    assert trace["request_count"] == 1
    assert trace["token_count"] == 16270
    assert trace["token_usage"] == {
        "input_tokens": 16007,
        "cached_input_tokens": 15104,
        "cache_write_input_tokens": 0,
        "output_tokens": 263,
        "reasoning_output_tokens": 48,
    }
    assert trace["available_cost"] is None
    assert set(trace["source_digests"]) == {"prompt", "events_jsonl", "final_output", "metadata"}

    trace["source_path"] = str(root)
    trace["copy_paths"] = {
        "prompt": "traces/EQ-F01-AH-01/attempt-01/prompt.txt",
        "events_jsonl": "traces/EQ-F01-AH-01/attempt-01/events.jsonl",
        "final_output": "traces/EQ-F01-AH-01/attempt-01/final.json",
        "metadata": "traces/EQ-F01-AH-01/attempt-01/metadata.json",
    }
    evaluation_run = json.loads(Path("docs/evidence/ticket-20/evaluation-run.json").read_text(encoding="utf-8"))
    scorer_case = json.loads(Path("corpus/scorer/allocation-holdout/EQ-F01-AH-01.json").read_text(encoding="utf-8"))
    expected_manifest = build_trace_manifest(
        evaluation_run_digest=digest_contract("evaluation_run", evaluation_run),
        traces=[trace],
        forbidden_field_names={"reference_verdict", "scorer_sentinel", "decisive_evidence"},
        scorer_sentinels={scorer_case["scorer_sentinel"]},
    )
    assert expected_manifest["scorer_sentinel_digests"] == [content_digest(scorer_case["scorer_sentinel"])]
    assert json.loads(Path("docs/evidence/ticket-20/trace-manifest.json").read_text(encoding="utf-8")) == expected_manifest
