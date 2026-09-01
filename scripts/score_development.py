"""Score saved Development Split Case Assessments with the canonical scorer."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from edgequeue.corpus import build_development_cases
from edgequeue.experiment import (
    RankerExperimentCase,
    ScorerExperimentCase,
    compare_allocators,
)
from edgequeue.results import load_case_assessment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "docs" / "evidence" / "ticket-20" / "development-traces"
REVIEW_BUDGET = 4
RANDOM_SEEDS = tuple(range(1000))


def main() -> int:
    corpus_cases = build_development_cases()
    ranker_cases = []
    scorer_cases = []
    for corpus_case in corpus_cases:
        ranker_case = corpus_case.ranker_case
        final_output_path = TRACE_ROOT / ranker_case.case_id / "attempt-01" / "final.json"
        assessment = load_case_assessment(
            final_output_path,
            deterministic_score=ranker_case.deterministic_score,
        )
        ranker_cases.append(
            RankerExperimentCase(
                case_id=ranker_case.case_id,
                current_verdict=ranker_case.current_verdict,
                primary_confidence=ranker_case.primary_confidence,
                evaluator_verdicts=ranker_case.evaluator_verdicts,
                deterministic_score=ranker_case.deterministic_score,
                edgequeue_assessment=assessment,
            )
        )
        scorer_case = corpus_case.scorer_case
        scorer_cases.append(
            ScorerExperimentCase(
                case_id=scorer_case.case_id,
                reference_verdict=scorer_case.reference_verdict,
            )
        )

    comparison = compare_allocators(
        ranker_cases,
        scorer_cases=scorer_cases,
        review_budget=REVIEW_BUDGET,
        random_seeds=RANDOM_SEEDS,
    )
    random_recalls = sorted(result.metrics.recall_at_k for result in comparison.random)
    p95_index = math.ceil(0.95 * len(random_recalls)) - 1
    artifact = {
        "split": "DEV",
        "review_budget": REVIEW_BUDGET,
        "random_seed_count": len(RANDOM_SEEDS),
        "fixed": {
            name: {
                "review_queue": result.review_queue,
                "metrics": asdict(result.metrics),
            }
            for name, result in comparison.fixed.items()
        },
        "random": {
            "recall_at_k_mean": sum(random_recalls) / len(random_recalls),
            "recall_at_k_p95": random_recalls[p95_index],
            "runs": [
                {
                    "review_queue": result.review_queue,
                    "metrics": asdict(result.metrics),
                }
                for result in comparison.random
            ],
        },
    }
    print(
        json.dumps(
            {
                "source": str(TRACE_ROOT),
                "edgequeue": artifact["fixed"]["edgequeue"],
                "lowest_confidence": artifact["fixed"]["lowest_confidence"],
                "disagreement": artifact["fixed"]["disagreement"],
                "deterministic": artifact["fixed"]["deterministic"],
                "random": {
                    "recall_at_k_mean": artifact["random"]["recall_at_k_mean"],
                    "recall_at_k_p95": artifact["random"]["recall_at_k_p95"],
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
