import pytest

from edgequeue.scoring import (
    PRIMARY_RANKING_METRIC,
    InvalidReviewQueue,
    InvalidScorerInput,
    score_review_queue,
)


def test_scores_label_error_recovery_at_fixed_budget() -> None:
    current_verdicts = {
        "case-a": "PASS",
        "case-b": "PASS",
        "case-c": "FAIL",
        "case-d": "FAIL",
    }
    reference_verdicts = {
        "case-a": "FAIL",
        "case-b": "PASS",
        "case-c": "PASS",
        "case-d": "FAIL",
    }

    result = score_review_queue(
        review_queue=["case-a", "case-b"],
        current_verdicts=current_verdicts,
        reference_verdicts=reference_verdicts,
        review_budget=2,
    )

    assert result.recall_at_k == 0.5
    assert result.precision_at_k == 0.5
    assert result.false_negative_ids == ("case-c",)
    assert result.oracle_regret == 1


def test_rejects_a_queue_without_k_unique_cases() -> None:
    with pytest.raises(
        InvalidReviewQueue,
        match="Review Queue must contain exactly 2 unique case identifiers",
    ):
        score_review_queue(
            review_queue=["case-a", "case-a"],
            current_verdicts={"case-a": "PASS", "case-b": "FAIL"},
            reference_verdicts={"case-a": "FAIL", "case-b": "FAIL"},
            review_budget=2,
        )


def test_rejects_an_unknown_case_identifier() -> None:
    with pytest.raises(
        InvalidReviewQueue,
        match="Review Queue contains unknown case identifiers: case-x",
    ):
        score_review_queue(
            review_queue=["case-a", "case-x"],
            current_verdicts={"case-a": "PASS", "case-b": "FAIL"},
            reference_verdicts={"case-a": "FAIL", "case-b": "FAIL"},
            review_budget=2,
        )


def test_rejects_mismatched_current_and_reference_case_sets() -> None:
    with pytest.raises(
        InvalidScorerInput,
        match="Current and reference case identifiers must match",
    ):
        score_review_queue(
            review_queue=["case-a"],
            current_verdicts={"case-a": "PASS"},
            reference_verdicts={"case-b": "FAIL"},
            review_budget=1,
        )


def test_declares_recall_at_k_as_the_only_primary_ranking_metric() -> None:
    assert PRIMARY_RANKING_METRIC == "recall_at_k"
