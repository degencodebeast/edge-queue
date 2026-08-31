from dataclasses import dataclass
from typing import Sequence

from edgequeue.baselines import (
    allocate_deterministic,
    allocate_disagreement,
    allocate_lowest_confidence,
    allocate_oracle,
    allocate_random,
)
from edgequeue.ranking import CaseAssessment, create_review_queue
from edgequeue.scoring import AllocationMetrics, score_review_queue


@dataclass(frozen=True)
class RankerExperimentCase:
    case_id: str
    current_verdict: str
    primary_confidence: int
    evaluator_verdicts: tuple[str, str, str]
    deterministic_score: int
    edgequeue_assessment: CaseAssessment


@dataclass(frozen=True)
class ScorerExperimentCase:
    case_id: str
    reference_verdict: str


@dataclass(frozen=True)
class AllocatorResult:
    review_queue: tuple[str, ...]
    metrics: AllocationMetrics


@dataclass(frozen=True)
class ExperimentComparison:
    fixed: dict[str, AllocatorResult]
    random: tuple[AllocatorResult, ...]


def compare_allocators(
    ranker_cases: Sequence[RankerExperimentCase],
    *,
    scorer_cases: Sequence[ScorerExperimentCase],
    review_budget: int,
    random_seeds: Sequence[int],
) -> ExperimentComparison:
    current_verdicts = {
        case.case_id: case.current_verdict for case in ranker_cases
    }
    reference_verdicts = {
        case.case_id: case.reference_verdict for case in scorer_cases
    }

    def result_for(review_queue: tuple[str, ...]) -> AllocatorResult:
        return AllocatorResult(
            review_queue=review_queue,
            metrics=score_review_queue(
                review_queue=review_queue,
                current_verdicts=current_verdicts,
                reference_verdicts=reference_verdicts,
                review_budget=review_budget,
            ),
        )

    fixed_queues = {
        "edgequeue": create_review_queue(
            [case.edgequeue_assessment for case in ranker_cases],
            review_budget=review_budget,
        ),
        "lowest_confidence": allocate_lowest_confidence(
            confidence_by_case={
                case.case_id: case.primary_confidence for case in ranker_cases
            },
            review_budget=review_budget,
        ),
        "disagreement": allocate_disagreement(
            verdicts_by_case={
                case.case_id: case.evaluator_verdicts for case in ranker_cases
            },
            review_budget=review_budget,
        ),
        "deterministic": allocate_deterministic(
            risk_by_case={
                case.case_id: case.deterministic_score for case in ranker_cases
            },
            review_budget=review_budget,
        ),
        "oracle": allocate_oracle(
            current_verdicts=current_verdicts,
            reference_verdicts=reference_verdicts,
            review_budget=review_budget,
        ),
    }

    random_results = tuple(
        result_for(
            allocate_random(
                case_ids=tuple(current_verdicts),
                review_budget=review_budget,
                seed=seed,
            )
        )
        for seed in random_seeds
    )

    return ExperimentComparison(
        fixed={name: result_for(queue) for name, queue in fixed_queues.items()},
        random=random_results,
    )
