"""Score the three Allocation Holdout attempts and apply Ticket 01 thresholds."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from edgequeue.corpus import build_allocation_holdout_cases
from edgequeue.experiment import (
    RankerExperimentCase,
    ScorerExperimentCase,
    compare_allocators,
)
from edgequeue.results import load_case_assessment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "runs" / "allocation-holdout"
REVIEW_BUDGET = 8
RANDOM_SEEDS = tuple(range(1000))
ATTEMPTS = (1, 2, 3)


def comparison_for_attempt(attempt: int):
    ranker_cases = []
    scorer_cases = []
    for corpus_case in build_allocation_holdout_cases():
        ranker_case = corpus_case.ranker_case
        final_output_path = (
            TRACE_ROOT / ranker_case.case_id / f"attempt-{attempt:02d}" / "final.json"
        )
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
        scorer_cases.append(
            ScorerExperimentCase(
                case_id=corpus_case.scorer_case.case_id,
                reference_verdict=corpus_case.scorer_case.reference_verdict,
            )
        )
    return compare_allocators(
        ranker_cases,
        scorer_cases=scorer_cases,
        review_budget=REVIEW_BUDGET,
        random_seeds=RANDOM_SEEDS,
    )


def serialized_result(result) -> dict:
    return {
        "review_queue": result.review_queue,
        "metrics": asdict(result.metrics),
    }


def main() -> int:
    comparisons = {attempt: comparison_for_attempt(attempt) for attempt in ATTEMPTS}
    attempt_artifacts = {
        str(attempt): {
            "fixed": {
                name: serialized_result(result)
                for name, result in comparison.fixed.items()
            },
            "random": [serialized_result(result) for result in comparison.random],
        }
        for attempt, comparison in comparisons.items()
    }
    edgequeue_recalls = [
        comparison.fixed["edgequeue"].metrics.recall_at_k
        for comparison in comparisons.values()
    ]
    baseline_recalls = {
        name: comparison.fixed[name].metrics.recall_at_k
        for name in ("lowest_confidence", "disagreement", "deterministic")
        for comparison in (next(iter(comparisons.values())),)
    }
    strongest_baseline = max(baseline_recalls.values())
    random_recalls = sorted(
        result.metrics.recall_at_k
        for result in next(iter(comparisons.values())).random
    )
    random_p95 = random_recalls[math.ceil(0.95 * len(random_recalls)) - 1]
    mean_recall = sum(edgequeue_recalls) / len(edgequeue_recalls)
    worst_recall = min(edgequeue_recalls)
    go = (
        mean_recall >= 0.70
        and worst_recall >= 0.60
        and mean_recall - strongest_baseline >= 0.20
        and worst_recall - strongest_baseline >= 0.10
        and worst_recall > random_p95
    )
    narrow = not go and mean_recall - strongest_baseline >= 0.10
    decision = "go" if go else "narrow" if narrow else "reject"
    artifact = {
        "split": "AH",
        "review_budget": REVIEW_BUDGET,
        "attempts": ATTEMPTS,
        "random_seed_count": len(RANDOM_SEEDS),
        "attempts_detail": attempt_artifacts,
        "summary": {
            "edgequeue_recalls": edgequeue_recalls,
            "mean_recall": mean_recall,
            "worst_recall": worst_recall,
            "baseline_recalls": baseline_recalls,
            "strongest_baseline": strongest_baseline,
            "random_recall_p95": random_p95,
            "decision": decision,
        },
    }
    output_path = TRACE_ROOT / "evaluation.json"
    output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(output_path), **artifact["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
