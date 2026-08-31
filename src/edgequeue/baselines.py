import random
from typing import Mapping, Sequence


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
