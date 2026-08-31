from dataclasses import dataclass
from typing import Literal, Sequence


AssessmentStatus = Literal["risk_finding", "abstention"]


@dataclass(frozen=True)
class CaseAssessment:
    case_id: str
    status: AssessmentStatus
    risk_score: int
    deterministic_score: int


def create_review_queue(
    assessments: Sequence[CaseAssessment], *, review_budget: int
) -> tuple[str, ...]:
    ordered_assessments = sorted(
        assessments,
        key=lambda assessment: (
            0 if assessment.status == "risk_finding" else 1,
            -assessment.risk_score,
            -assessment.deterministic_score,
            assessment.case_id,
        ),
    )
    return tuple(
        assessment.case_id for assessment in ordered_assessments[:review_budget]
    )
