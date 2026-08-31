from dataclasses import dataclass
from typing import Mapping, Sequence


PRIMARY_RANKING_METRIC = "recall_at_k"


@dataclass(frozen=True)
class AllocationMetrics:
    recall_at_k: float
    precision_at_k: float
    false_negative_ids: tuple[str, ...]
    oracle_regret: int


class InvalidReviewQueue(ValueError):
    """The Review Queue violates a non-compensating validity rule."""


class InvalidScorerInput(ValueError):
    """The scorer inputs do not describe one complete case set."""


def score_review_queue(
    *,
    review_queue: Sequence[str],
    current_verdicts: Mapping[str, str],
    reference_verdicts: Mapping[str, str],
    review_budget: int,
) -> AllocationMetrics:
    if set(current_verdicts) != set(reference_verdicts):
        raise InvalidScorerInput(
            "Current and reference case identifiers must match"
        )

    if len(review_queue) != review_budget or len(set(review_queue)) != review_budget:
        raise InvalidReviewQueue(
            f"Review Queue must contain exactly {review_budget} unique case identifiers"
        )

    unknown_case_ids = sorted(set(review_queue) - set(current_verdicts))
    if unknown_case_ids:
        joined_case_ids = ", ".join(unknown_case_ids)
        raise InvalidReviewQueue(
            f"Review Queue contains unknown case identifiers: {joined_case_ids}"
        )

    label_error_ids = {
        case_id
        for case_id, current_verdict in current_verdicts.items()
        if current_verdict != reference_verdicts[case_id]
    }
    selected_error_ids = label_error_ids.intersection(review_queue)
    false_negative_ids = tuple(sorted(label_error_ids - selected_error_ids))

    recall_at_k = len(selected_error_ids) / len(label_error_ids)
    precision_at_k = len(selected_error_ids) / review_budget
    oracle_recovery = min(review_budget, len(label_error_ids))

    return AllocationMetrics(
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        false_negative_ids=false_negative_ids,
        oracle_regret=oracle_recovery - len(selected_error_ids),
    )
