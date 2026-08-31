import pytest

from edgequeue.integrity import ScorerLeakageDetected, reject_scorer_leakage


def test_rejects_an_intentional_scorer_sentinel_leak() -> None:
    allocator_artifacts = {
        "prompt": "Assess case-a without hidden labels.",
        "risk_finding": {"explanation": "Observed marker EQ-SECRET-case-a"},
    }

    with pytest.raises(
        ScorerLeakageDetected,
        match="Scorer-only content found: EQ-SECRET-case-a",
    ):
        reject_scorer_leakage(
            allocator_artifacts,
            forbidden_field_names={"reference_verdict"},
            scorer_sentinels={"EQ-SECRET-case-a"},
        )
