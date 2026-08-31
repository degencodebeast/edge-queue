import pytest

from edgequeue.contracts import content_digest
from edgequeue.run_evidence import ScorerLeakageError, build_trace_manifest


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
