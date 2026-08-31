from edgequeue.experiment import (
    RankerExperimentCase,
    ScorerExperimentCase,
    compare_allocators,
)
from edgequeue.ranking import CaseAssessment


def test_compares_allocators_on_the_same_cases_and_budget() -> None:
    ranker_cases = [
        RankerExperimentCase(
            "case-a",
            "PASS",
            95,
            ("PASS", "PASS", "PASS"),
            10,
            CaseAssessment("case-a", "risk_finding", 95, 10),
        ),
        RankerExperimentCase(
            "case-b",
            "PASS",
            10,
            ("PASS", "FAIL", "PASS"),
            80,
            CaseAssessment("case-b", "risk_finding", 80, 80),
        ),
        RankerExperimentCase(
            "case-c",
            "PASS",
            5,
            ("PASS", "FAIL", "UNDETERMINED"),
            100,
            CaseAssessment("case-c", "risk_finding", 20, 100),
        ),
        RankerExperimentCase(
            "case-d",
            "FAIL",
            20,
            ("FAIL", "FAIL", "FAIL"),
            30,
            CaseAssessment("case-d", "abstention", 0, 30),
        ),
        RankerExperimentCase(
            "case-e",
            "FAIL",
            90,
            ("FAIL", "FAIL", "FAIL"),
            20,
            CaseAssessment("case-e", "risk_finding", 90, 20),
        ),
    ]
    scorer_cases = [
        ScorerExperimentCase("case-a", "FAIL"),
        ScorerExperimentCase("case-b", "FAIL"),
        ScorerExperimentCase("case-c", "PASS"),
        ScorerExperimentCase("case-d", "FAIL"),
        ScorerExperimentCase("case-e", "PASS"),
    ]

    result = compare_allocators(
        ranker_cases,
        scorer_cases=scorer_cases,
        review_budget=2,
        random_seeds=(11, 29),
    )

    assert result.fixed["edgequeue"].review_queue == ("case-a", "case-e")
    assert result.fixed["lowest_confidence"].review_queue == ("case-c", "case-b")
    assert result.fixed["disagreement"].review_queue == ("case-c", "case-b")
    assert result.fixed["deterministic"].review_queue == ("case-c", "case-b")
    assert result.fixed["oracle"].review_queue == ("case-a", "case-b")
    assert result.fixed["edgequeue"].metrics.recall_at_k == 2 / 3
    assert result.fixed["lowest_confidence"].metrics.recall_at_k == 1 / 3
    assert len(result.random) == 2
