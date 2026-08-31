import random
from typing import Mapping, Sequence


class InvalidBaselineInput(ValueError):
    """Baseline inputs do not describe one complete Review Batch."""


def allocate_lowest_confidence(
    *, confidence_by_case: Mapping[str, int], review_budget: int
) -> tuple[str, ...]:
    ordered_case_ids = sorted(
        confidence_by_case,
        key=lambda case_id: (confidence_by_case[case_id], case_id),
    )
    return tuple(ordered_case_ids[:review_budget])


def allocate_disagreement(
    *, verdicts_by_case: Mapping[str, Sequence[str]], review_budget: int
) -> tuple[str, ...]:
    def pairwise_disagreement(case_id: str) -> int:
        verdicts = verdicts_by_case[case_id]
        return sum(
            verdicts[left] != verdicts[right]
            for left in range(len(verdicts))
            for right in range(left + 1, len(verdicts))
        )

    ordered_case_ids = sorted(
        verdicts_by_case,
        key=lambda case_id: (-pairwise_disagreement(case_id), case_id),
    )
    return tuple(ordered_case_ids[:review_budget])


def allocate_deterministic(
    *, risk_by_case: Mapping[str, int], review_budget: int
) -> tuple[str, ...]:
    ordered_case_ids = sorted(
        risk_by_case,
        key=lambda case_id: (-risk_by_case[case_id], case_id),
    )
    return tuple(ordered_case_ids[:review_budget])


def allocate_random(
    *, case_ids: Sequence[str], review_budget: int, seed: int
) -> tuple[str, ...]:
    random_generator = random.Random(seed)
    return tuple(random_generator.sample(sorted(case_ids), review_budget))


def allocate_oracle(
    *,
    current_verdicts: Mapping[str, str],
    reference_verdicts: Mapping[str, str],
    review_budget: int,
) -> tuple[str, ...]:
    ordered_case_ids = sorted(
        current_verdicts,
        key=lambda case_id: (
            current_verdicts[case_id] == reference_verdicts[case_id],
            case_id,
        ),
    )
    return tuple(ordered_case_ids[:review_budget])


def allocate_fair_baselines(
    *,
    confidence_by_case: Mapping[str, int],
    verdicts_by_case: Mapping[str, Sequence[str]],
    deterministic_scores_by_case: Mapping[str, int],
    current_verdicts: Mapping[str, str],
    reference_verdicts: Mapping[str, str],
    review_budget: int,
    random_seed: int,
) -> dict[str, tuple[str, ...]]:
    """Allocate every required baseline over the same cases and Review Budget."""
    case_ids = set(current_verdicts)
    all_case_sets = (
        set(confidence_by_case),
        set(verdicts_by_case),
        set(deterministic_scores_by_case),
        set(reference_verdicts),
    )
    if not case_ids or any(candidate_ids != case_ids for candidate_ids in all_case_sets):
        raise InvalidBaselineInput("Baseline inputs must use the same non-empty case identifiers")
    if review_budget < 1 or review_budget > len(case_ids):
        raise InvalidBaselineInput("Review Budget must be within the Review Batch size")

    ordered_case_ids = tuple(sorted(case_ids))
    return {
        "seeded_random": allocate_random(
            case_ids=ordered_case_ids,
            review_budget=review_budget,
            seed=random_seed,
        ),
        "lowest_confidence": allocate_lowest_confidence(
            confidence_by_case=confidence_by_case,
            review_budget=review_budget,
        ),
        "disagreement_only": allocate_disagreement(
            verdicts_by_case=verdicts_by_case,
            review_budget=review_budget,
        ),
        "deterministic_only": allocate_deterministic(
            risk_by_case=deterministic_scores_by_case,
            review_budget=review_budget,
        ),
        "oracle": allocate_oracle(
            current_verdicts=current_verdicts,
            reference_verdicts=reference_verdicts,
            review_budget=review_budget,
        ),
    }
