"""Run isolated Case Assessments for one frozen Review Batch."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from edgequeue.contracts import (
    ContractValidationError,
    content_digest,
    digest_contract,
    validate_allocation_receipt,
    validate_case_assessment,
    validate_contract,
)
from edgequeue.ranking import CaseAssessment, create_review_queue


Allocator = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class AssessmentValidationError(ValueError):
    """An allocator output cannot support a valid Case Assessment."""


@dataclass(frozen=True)
class AssessmentBatchRun:
    """The immutable result of isolated assessment attempts for one batch."""

    valid: bool
    disposition: Literal["valid", "invalid"]
    assessments: tuple[Mapping[str, Any], ...]
    attempts_by_case: Mapping[str, tuple[str, ...]]
    attempt_records_by_case: Mapping[str, tuple[Mapping[str, Any], ...]]
    invalid_case_id: str | None
    unprocessed_case_ids: tuple[str, ...]


@dataclass(frozen=True)
class SelectionExplanation:
    """The exact ordering values for a selected case and the boundary case."""

    selected_case_id: str
    excluded_case_id: str
    selected_ordering_fields: tuple[str, int, int, str]
    excluded_ordering_fields: tuple[str, int, int, str]
    first_differing_field: str


@dataclass(frozen=True)
class AllocationDecision:
    """The deterministic Review Queue, bound receipt, and boundary explanations."""

    review_queue: tuple[str, ...]
    receipt: Mapping[str, Any]
    explanations: tuple[SelectionExplanation, ...]


def assess_review_batch(
    ranker_cases: Sequence[Mapping[str, Any]], *, allocator: Allocator
) -> AssessmentBatchRun:
    """Create one validated assessment per RankerCase with one retry on failure."""
    _validate_unique_case_ids(ranker_cases)
    assessments: list[Mapping[str, Any]] = []
    attempts_by_case: dict[str, tuple[str, ...]] = {}
    attempt_records_by_case: dict[str, tuple[Mapping[str, Any], ...]] = {}

    for case_index, ranker_case in enumerate(ranker_cases):
        case_id = _case_id(ranker_case)
        frozen_ranker_case = deepcopy(ranker_case)
        outcomes: list[str] = []
        attempt_records: list[Mapping[str, Any]] = []
        for attempt in range(2):
            try:
                assessment = allocator(deepcopy(frozen_ranker_case))
            except Exception as error:
                outcomes.append("execution_failure")
                attempt_records.append(
                    _attempt_record(attempt, "execution_failure", str(error))
                )
            else:
                try:
                    validate_case_assessment(assessment, frozen_ranker_case)
                except ContractValidationError as error:
                    if error.code == "invalid_evidence":
                        raise AssessmentValidationError(
                            "Case Assessment requires verified same-case evidence"
                        ) from error
                    outcomes.append("schema_failure")
                    attempt_records.append(
                        _attempt_record(attempt, "schema_failure", str(error))
                    )
                else:
                    outcomes.append("accepted")
                    attempt_records.append(_attempt_record(attempt, "accepted"))
                    assessments.append(assessment)
                    attempts_by_case[case_id] = tuple(outcomes)
                    attempt_records_by_case[case_id] = tuple(attempt_records)
                    break

            if attempt == 1:
                attempts_by_case[case_id] = tuple(outcomes)
                attempt_records_by_case[case_id] = tuple(attempt_records)
                return AssessmentBatchRun(
                    valid=False,
                    disposition="invalid",
                    assessments=tuple(assessments),
                    attempts_by_case=attempts_by_case,
                    attempt_records_by_case=attempt_records_by_case,
                    invalid_case_id=case_id,
                    unprocessed_case_ids=tuple(
                        _case_id(remaining_case)
                        for remaining_case in ranker_cases[case_index + 1 :]
                    ),
                )

    return AssessmentBatchRun(
        valid=True,
        disposition="valid",
        assessments=tuple(assessments),
        attempts_by_case=attempts_by_case,
        attempt_records_by_case=attempt_records_by_case,
        invalid_case_id=None,
        unprocessed_case_ids=(),
    )


def create_allocation_run_evidence(
    *,
    receipt: Mapping[str, Any],
    assessment_run: AssessmentBatchRun,
    allocation_decision: AllocationDecision,
) -> Mapping[str, Any]:
    """Create source-bound evidence for receipt explanations and runner outcomes."""
    _validate_evidence_sources(receipt, assessment_run, allocation_decision)
    receipt_digest = digest_contract("allocation_receipt", receipt)
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "allocation_receipt_digest": receipt_digest,
        "evaluation_run_id": receipt["evaluation_run_id"],
        "runner_outcomes": _runner_outcome_payloads(assessment_run),
        "selection_explanations": _selection_explanation_payloads(
            allocation_decision
        ),
    }
    payload["content_digest"] = content_digest(
        payload, excluded_keys={"content_digest"}
    )
    validate_allocation_run_evidence(
        payload,
        receipt=receipt,
        assessment_run=assessment_run,
        allocation_decision=allocation_decision,
    )
    return payload


def validate_allocation_run_evidence(
    evidence: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any],
    assessment_run: AssessmentBatchRun,
    allocation_decision: AllocationDecision,
) -> Mapping[str, Any]:
    """Validate the non-authoritative companion against one Allocation Receipt."""
    expected_fields = {
        "schema_version",
        "allocation_receipt_digest",
        "evaluation_run_id",
        "runner_outcomes",
        "selection_explanations",
        "content_digest",
    }
    if set(evidence) != expected_fields:
        raise AssessmentValidationError("Allocation Run Evidence has unsupported fields")
    if evidence["schema_version"] != "1.0":
        raise AssessmentValidationError("Allocation Run Evidence schema version is invalid")
    if evidence["allocation_receipt_digest"] != digest_contract(
        "allocation_receipt", receipt
    ):
        raise AssessmentValidationError("Allocation Run Evidence receipt digest does not match")
    if evidence["evaluation_run_id"] != receipt["evaluation_run_id"]:
        raise AssessmentValidationError("Allocation Run Evidence EvaluationRun does not match")
    if evidence["content_digest"] != content_digest(
        evidence, excluded_keys={"content_digest"}
    ):
        raise AssessmentValidationError("Allocation Run Evidence content digest does not match")

    _validate_evidence_sources(receipt, assessment_run, allocation_decision)
    if evidence["runner_outcomes"] != _runner_outcome_payloads(assessment_run):
        raise AssessmentValidationError(
            "Allocation Run Evidence runner outcomes do not match the assessment run"
        )
    if evidence["selection_explanations"] != _selection_explanation_payloads(
        allocation_decision
    ):
        raise AssessmentValidationError(
            "Allocation Run Evidence selection explanations do not match the allocation decision"
        )
    return evidence


def _attempt_record(
    attempt: int, outcome: str, error: str | None = None
) -> Mapping[str, Any]:
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "attempt": attempt + 1,
        "outcome": outcome,
    }
    if error:
        record["error"] = error
    return record


def _normalized_attempt_record(attempt_record: Mapping[str, Any]) -> Mapping[str, Any]:
    record = {"schema_version": "1.0", **attempt_record}
    if not isinstance(record.get("attempt"), int) or record["attempt"] < 1:
        raise AssessmentValidationError("Runner attempt number is invalid")
    if record.get("outcome") not in {
        "accepted",
        "timeout",
        "malformed",
        "schema_failure",
        "execution_failure",
    }:
        raise AssessmentValidationError("Runner attempt outcome is invalid")
    if "error" in record and not isinstance(record["error"], str):
        raise AssessmentValidationError("Runner attempt error is invalid")
    return record


def _selection_explanation_payload(
    explanation: SelectionExplanation,
) -> Mapping[str, Any]:
    return {
        "selected_case_id": explanation.selected_case_id,
        "excluded_case_id": explanation.excluded_case_id,
        "selected_ordering_fields": list(explanation.selected_ordering_fields),
        "excluded_ordering_fields": list(explanation.excluded_ordering_fields),
        "first_differing_field": explanation.first_differing_field,
    }


def _validate_evidence_sources(
    receipt: Mapping[str, Any],
    assessment_run: AssessmentBatchRun,
    allocation_decision: AllocationDecision,
) -> None:
    if dict(receipt) != dict(allocation_decision.receipt):
        raise AssessmentValidationError(
            "Allocation Run Evidence receipt does not match the allocation decision"
        )
    if not assessment_run.valid:
        raise AssessmentValidationError(
            "Allocation Run Evidence requires a valid assessment run"
        )
    recorded_assessments = [
        {
            "case_id": assessment["case_id"],
            "assessment_digest": digest_contract("case_assessment", assessment),
        }
        for assessment in assessment_run.assessments
    ]
    if receipt["assessments"] != recorded_assessments:
        raise AssessmentValidationError(
            "Allocation Run Evidence assessment run does not match the receipt"
        )
    assessment_case_ids = {assessment["case_id"] for assessment in assessment_run.assessments}
    if set(assessment_run.attempt_records_by_case) != assessment_case_ids:
        raise AssessmentValidationError(
            "Allocation Run Evidence runner outcomes do not cover the assessment run"
        )


def _runner_outcome_payloads(
    assessment_run: AssessmentBatchRun,
) -> list[Mapping[str, Any]]:
    if not assessment_run.attempt_records_by_case:
        raise AssessmentValidationError("Allocation Run Evidence requires runner outcomes")
    return [
        {
            "case_id": case_id,
            "attempts": [
                _normalized_attempt_record(attempt_record)
                for attempt_record in attempt_records
            ],
        }
        for case_id, attempt_records in sorted(
            assessment_run.attempt_records_by_case.items()
        )
    ]


def _selection_explanation_payloads(
    allocation_decision: AllocationDecision,
) -> list[Mapping[str, Any]]:
    return [
        _selection_explanation_payload(explanation)
        for explanation in allocation_decision.explanations
    ]


def invalidate_evaluation_run(
    evaluation_run: Mapping[str, Any], *, batch_run: AssessmentBatchRun
) -> Mapping[str, Any]:
    """Mark one existing EvaluationRun invalid after a second allocator failure."""
    if batch_run.disposition != "invalid" or batch_run.invalid_case_id is None:
        raise AssessmentValidationError("Only an invalid assessment batch can invalidate an EvaluationRun")
    outcomes = batch_run.attempts_by_case[batch_run.invalid_case_id]
    runner_outcome_reference = (
        f"runner-attempts:{batch_run.invalid_case_id}:{','.join(outcomes)}"
    )
    raw_artifact_refs = [*evaluation_run["raw_artifact_refs"]]
    if runner_outcome_reference not in raw_artifact_refs:
        raw_artifact_refs.append(runner_outcome_reference)
    invalid_run = {
        **evaluation_run,
        "disposition": "invalid",
        "exit_code": 1,
        "raw_artifact_refs": raw_artifact_refs,
    }
    validate_contract("evaluation_run", invalid_run)
    return invalid_run


def allocate_review_queue(
    *,
    assessments: Sequence[Mapping[str, Any]],
    ranker_cases: Sequence[Mapping[str, Any]],
    review_budget: int,
    receipt_id: str,
    evaluation_run_id: str,
    corpus_digest: str,
    split_digest: str,
    allocator_config_digest: str,
) -> AllocationDecision:
    """Create the authoritative queue, receipt, and first-excluded explanations."""
    ranker_by_id = {_case_id(ranker_case): ranker_case for ranker_case in ranker_cases}
    if len(ranker_by_id) != len(ranker_cases):
        raise AssessmentValidationError("Review Batch case identifiers must be unique")
    if len(assessments) != len(ranker_by_id):
        raise AssessmentValidationError("Review Batch requires one Case Assessment per RankerCase")

    ranked_assessments = tuple(
        _rankable_assessment(assessment, ranker_by_id) for assessment in assessments
    )
    review_queue = create_review_queue(
        ranked_assessments,
        review_budget=review_budget,
        known_case_ids=ranker_by_id,
    )
    ordered = tuple(sorted(ranked_assessments, key=_ordering_key))
    first_excluded = ordered[review_budget] if review_budget < len(ordered) else None
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_id": receipt_id,
        "evaluation_run_id": evaluation_run_id,
        "corpus_digest": corpus_digest,
        "split_digest": split_digest,
        "allocator_config_digest": allocator_config_digest,
        "review_budget": review_budget,
        "assessments": [
            {
                "case_id": assessment["case_id"],
                "assessment_digest": digest_contract("case_assessment", assessment),
            }
            for assessment in assessments
        ],
        "review_queue": list(review_queue),
        "first_excluded_case_id": (
            first_excluded.case_id if first_excluded is not None else None
        ),
        "selection_boundary": (
            _selection_boundary(first_excluded) if first_excluded is not None else None
        ),
    }
    validate_allocation_receipt(receipt, list(assessments), ranker_cases)
    return AllocationDecision(
        review_queue=review_queue,
        receipt=receipt,
        explanations=_selection_explanations(review_queue, ordered, first_excluded),
    )


def _case_id(ranker_case: Mapping[str, Any]) -> str:
    case_id = ranker_case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise AssessmentValidationError("RankerCase requires a non-empty case identifier")
    return case_id


def _validate_unique_case_ids(ranker_cases: Sequence[Mapping[str, Any]]) -> None:
    case_ids = [_case_id(ranker_case) for ranker_case in ranker_cases]
    if len(case_ids) != len(set(case_ids)):
        raise AssessmentValidationError("Review Batch case identifiers must be unique")


def _rankable_assessment(
    assessment: Mapping[str, Any], ranker_by_id: Mapping[str, Mapping[str, Any]]
) -> CaseAssessment:
    case_id = _case_id(assessment)
    ranker_case = ranker_by_id.get(case_id)
    if ranker_case is None:
        raise AssessmentValidationError("Case Assessment references an unknown case identifier")
    try:
        validate_case_assessment(assessment, ranker_case)
        deterministic_score = ranker_case["deterministic_score"]
        status = assessment["status"]
        risk_score = assessment["risk_score"]
    except (ContractValidationError, KeyError) as error:
        raise AssessmentValidationError("Case Assessment is invalid for its RankerCase") from error
    if not isinstance(deterministic_score, int) or not isinstance(risk_score, int):
        raise AssessmentValidationError("Case Assessment ordering scores must be integers")
    if status not in {"risk_finding", "abstention"}:
        raise AssessmentValidationError("Case Assessment status is invalid")
    return CaseAssessment(case_id, status, risk_score, deterministic_score)


def _ordering_key(assessment: CaseAssessment) -> tuple[int, int, int, str]:
    return (
        0 if assessment.status == "risk_finding" else 1,
        -assessment.risk_score,
        -assessment.deterministic_score,
        assessment.case_id,
    )


def _selection_boundary(assessment: CaseAssessment) -> dict[str, Any]:
    return {
        "excluded_case_id": assessment.case_id,
        "excluded_status": assessment.status,
        "excluded_risk_score": assessment.risk_score,
        "excluded_deterministic_score": assessment.deterministic_score,
    }


def _selection_explanations(
    review_queue: Sequence[str],
    ordered: Sequence[CaseAssessment],
    first_excluded: CaseAssessment | None,
) -> tuple[SelectionExplanation, ...]:
    if first_excluded is None:
        return ()
    by_case_id = {assessment.case_id: assessment for assessment in ordered}
    return tuple(
        _selection_explanation(by_case_id[case_id], first_excluded)
        for case_id in review_queue
    )


def _selection_explanation(
    selected: CaseAssessment, excluded: CaseAssessment
) -> SelectionExplanation:
    selected_fields = _ordering_fields(selected)
    excluded_fields = _ordering_fields(excluded)
    field_names = ("status", "risk_score", "deterministic_score", "case_id")
    first_differing_field = next(
        field_name
        for field_name, selected_value, excluded_value in zip(
            field_names, selected_fields, excluded_fields, strict=True
        )
        if selected_value != excluded_value
    )
    return SelectionExplanation(
        selected_case_id=selected.case_id,
        excluded_case_id=excluded.case_id,
        selected_ordering_fields=selected_fields,
        excluded_ordering_fields=excluded_fields,
        first_differing_field=first_differing_field,
    )


def _ordering_fields(assessment: CaseAssessment) -> tuple[str, int, int, str]:
    return (
        assessment.status,
        assessment.risk_score,
        assessment.deterministic_score,
        assessment.case_id,
    )
