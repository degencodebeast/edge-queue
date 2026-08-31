from dataclasses import dataclass
from typing import Iterable, Literal, Sequence


AssessmentStatus = Literal["risk_finding", "abstention"]


@dataclass(frozen=True)
class CaseAssessment:
    case_id: str
    status: AssessmentStatus
    risk_score: int
    deterministic_score: int


class InvalidReviewBatch(ValueError):
    """The assessments cannot form one authoritative Review Queue."""


def create_review_queue(
    assessments: Sequence[CaseAssessment],
    *,
    review_budget: int,
    known_case_ids: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Return the deterministic, exact-budget prefix of valid assessments."""
    case_ids = [assessment.case_id for assessment in assessments]
    if len(case_ids) != len(set(case_ids)):
        raise InvalidReviewBatch("Case Assessment case identifiers must be unique")
    if review_budget < 1 or review_budget > len(case_ids):
        raise InvalidReviewBatch(
            "Review Budget must select exactly K available Case Assessments"
        )
    if known_case_ids is not None:
        unknown_case_ids = sorted(set(case_ids) - set(known_case_ids))
        if unknown_case_ids:
            raise InvalidReviewBatch(
                "Case Assessments contain unknown case identifiers: "
                + ", ".join(unknown_case_ids)
            )
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
