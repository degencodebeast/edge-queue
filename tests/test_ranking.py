from edgequeue.ranking import CaseAssessment, create_review_queue


def test_orders_findings_by_risk_then_deterministic_score() -> None:
    assessments = [
        CaseAssessment("case-a", "abstention", 100, 90),
        CaseAssessment("case-b", "risk_finding", 50, 10),
        CaseAssessment("case-c", "risk_finding", 50, 80),
        CaseAssessment("case-d", "risk_finding", 70, 0),
    ]

    review_queue = create_review_queue(assessments, review_budget=3)

    assert review_queue == ("case-d", "case-c", "case-b")
