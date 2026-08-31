from dataclasses import asdict
import json
from pathlib import Path

import pytest

from edgequeue.allocation import (
    AssessmentValidationError,
    allocate_review_queue,
    assess_review_batch,
    invalidate_evaluation_run,
)
from edgequeue.contracts import (
    content_digest,
    digest_contract,
    validate_allocation_receipt,
    validate_contract,
)
from edgequeue.corpus import build_development_cases
from edgequeue.ranking import CaseAssessment, InvalidReviewBatch, create_review_queue


def test_orders_findings_by_risk_then_deterministic_score() -> None:
    assessments = [
        CaseAssessment("case-a", "abstention", 100, 90),
        CaseAssessment("case-b", "risk_finding", 50, 10),
        CaseAssessment("case-c", "risk_finding", 50, 80),
        CaseAssessment("case-d", "risk_finding", 70, 0),
    ]

    review_queue = create_review_queue(assessments, review_budget=3)

    assert review_queue == ("case-d", "case-c", "case-b")


def _ranker_case() -> dict[str, object]:
    return asdict(build_development_cases()[0].ranker_case)


def _test_digest(name: str) -> str:
    return content_digest({"ticket": "16", "test_record": name})


def _risk_finding(
    ranker_case: dict[str, object], *, allocator_config_digest: str | None = None
) -> dict[str, object]:
    case_id = str(ranker_case["case_id"])
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "status": "risk_finding",
        "risk_score": 82,
        "reason_codes": ["evidence_conflict"],
        "rubric_clause_ids": ["R1"],
        "evidence_references": [
            {
                "case_id": case_id,
                "event_id": "E1",
                "relation": "contradicts_current",
                "claim": "The task record contradicts the current Verdict.",
                "status": "verified",
            }
        ],
        "explanation": "Verified same-case evidence may contradict the current Verdict.",
        "abstention_reason": None,
        "allocator_config_digest": allocator_config_digest
        or _test_digest("risk-finding-allocator-config"),
        "input_digest": digest_contract("ranker_case", ranker_case),
        "output_digest": content_digest({"case_id": case_id, "output": "risk_finding"}),
        "attempts": [
            {"schema_version": "1.0", "attempt": 1, "outcome": "accepted"}
        ],
    }


def _abstention(ranker_case: dict[str, object]) -> dict[str, object]:
    case_id = str(ranker_case["case_id"])
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "status": "abstention",
        "risk_score": 0,
        "reason_codes": ["insufficient_evidence"],
        "rubric_clause_ids": [],
        "evidence_references": [
            {
                "case_id": case_id,
                "event_id": "E1",
                "relation": "insufficient",
                "claim": "The available evidence cannot support a Risk Finding.",
                "status": "unavailable",
            }
        ],
        "explanation": "The allocator cannot verify a Risk Finding.",
        "abstention_reason": "Verified evidence is insufficient.",
        "allocator_config_digest": _test_digest("abstention-allocator-config"),
        "input_digest": digest_contract("ranker_case", ranker_case),
        "output_digest": content_digest({"case_id": case_id, "output": "abstention"}),
        "attempts": [
            {"schema_version": "1.0", "attempt": 1, "outcome": "accepted"}
        ],
    }


def _evaluation_run(case_ids: list[str]) -> dict[str, object]:
    reference_names = (
        "corpus_manifest",
        "split_manifest",
        "ranker_case_bundle",
        "rubric_snapshot",
        "initial_evaluation_snapshot",
        "evidence_validation_manifest",
        "allocator_prompt",
        "allocator_model_config",
        "feature_version",
        "ranking_policy",
        "evaluation_config",
        "scorer_reference_manifest",
        "canonical_scorer",
        "runtime_dependency_manifest",
        "risk_findings",
        "review_queue",
        "allocation_receipt",
        "raw_run_outputs",
    )
    return {
        "schema_version": "1.0",
        "evaluation_run_id": "ticket-16-invalid-run",
        "corpus_digest": _test_digest("evaluation-run-corpus"),
        "split_digest": _test_digest("evaluation-run-split"),
        "evaluation_config_digest": _test_digest("evaluation-run-config"),
        "allocator_config_digest": _test_digest("evaluation-run-allocator"),
        "scorer_version": "1.0",
        "command_digest": _test_digest("evaluation-run-command"),
        "code_commit": "ticket-16",
        "git_tree": "ticket-16-tree",
        "dirty_state": False,
        "tested_working_tree_digest": _test_digest("evaluation-run-tree"),
        "evaluation_core": {
            **{
                name: {"name": name, "digest": _test_digest(name)}
                for name in reference_names
            },
            "optional_absences": [],
        },
        "exit_code": 0,
        "review_budget": 1,
        "case_ids": case_ids,
        "review_queue": [],
        "allocation_receipt_digest": _test_digest("evaluation-run-receipt"),
        "disposition": "valid",
        "raw_artifact_refs": [],
    }


def test_assesses_each_case_with_verified_same_case_evidence() -> None:
    ranker_case = _ranker_case()

    run = assess_review_batch(
        [ranker_case],
        allocator=lambda case: _risk_finding(case),
    )

    assert run.valid is True
    assert [assessment["case_id"] for assessment in run.assessments] == [
        "EQ-F01-DEV-01"
    ]
    assert run.attempts_by_case["EQ-F01-DEV-01"] == ("accepted",)


def test_accepts_an_agent_abstention_for_one_ranker_case() -> None:
    ranker_case = _ranker_case()

    run = assess_review_batch([ranker_case], allocator=lambda case: _abstention(case))

    assert run.valid is True
    assert run.assessments[0]["status"] == "abstention"


def test_rejects_risk_finding_with_other_case_evidence() -> None:
    ranker_case = _ranker_case()
    invalid = _risk_finding(ranker_case)
    invalid["evidence_references"] = [
        {
            "case_id": "EQ-F02-DEV-01",
            "event_id": "E1",
            "relation": "contradicts_current",
            "claim": "This evidence is from another case.",
            "status": "verified",
        }
    ]

    with pytest.raises(AssessmentValidationError, match="verified same-case evidence"):
        assess_review_batch([ranker_case], allocator=lambda _: invalid)


def test_retries_one_identical_execution_failure_then_invalidates_second() -> None:
    ranker_case = _ranker_case()
    received_case_ids: list[str] = []
    received_cases: list[dict[str, object]] = []
    received_deterministic_scores: list[int] = []

    def failing_allocator(case: dict[str, object]) -> dict[str, object]:
        received_case_ids.append(str(case["case_id"]))
        received_cases.append(case)
        received_deterministic_scores.append(int(case["deterministic_score"]))
        case["deterministic_score"] = 0
        raise RuntimeError("offline allocator failure")

    run = assess_review_batch([ranker_case], allocator=failing_allocator)

    assert received_case_ids == ["EQ-F01-DEV-01", "EQ-F01-DEV-01"]
    assert received_cases[0] is not received_cases[1]
    assert received_deterministic_scores == [72, 72]
    assert ranker_case["deterministic_score"] == 72
    assert run.valid is False
    assert run.disposition == "invalid"
    assert run.invalid_case_id == "EQ-F01-DEV-01"
    assert run.assessments == ()
    assert run.attempts_by_case["EQ-F01-DEV-01"] == (
        "execution_failure",
        "execution_failure",
    )


def test_retries_a_schema_failure_then_accepts_the_second_assessment() -> None:
    ranker_case = _ranker_case()
    invalid = {**_risk_finding(ranker_case), "unexpected": "schema failure"}
    outputs = iter((invalid, _risk_finding(ranker_case)))

    run = assess_review_batch([ranker_case], allocator=lambda _: next(outputs))

    assert run.disposition == "valid"
    assert run.attempts_by_case["EQ-F01-DEV-01"] == (
        "schema_failure",
        "accepted",
    )


def test_marks_the_evaluation_run_invalid_and_preserves_remaining_batch_state() -> None:
    ranker_cases = [
        asdict(build_development_cases()[0].ranker_case),
        asdict(build_development_cases()[1].ranker_case),
    ]
    calls: list[str] = []

    def failing_allocator(case: dict[str, object]) -> dict[str, object]:
        calls.append(str(case["case_id"]))
        raise RuntimeError("offline allocator failure")

    batch_run = assess_review_batch(ranker_cases, allocator=failing_allocator)
    evaluation_run = invalidate_evaluation_run(
        _evaluation_run([str(case["case_id"]) for case in ranker_cases]),
        batch_run=batch_run,
    )

    assert calls == ["EQ-F01-DEV-01", "EQ-F01-DEV-01"]
    assert batch_run.unprocessed_case_ids == ("EQ-F01-DEV-02",)
    assert evaluation_run["disposition"] == "invalid"
    assert evaluation_run["raw_artifact_refs"] == [
        "runner-attempts:EQ-F01-DEV-01:execution_failure,execution_failure"
    ]
    assert validate_contract("evaluation_run", evaluation_run) == evaluation_run


def test_create_review_queue_rejects_duplicate_unknown_and_wrong_budget_cases() -> None:
    assessments = [
        CaseAssessment("case-a", "risk_finding", 80, 20),
        CaseAssessment("case-a", "risk_finding", 70, 30),
    ]

    with pytest.raises(InvalidReviewBatch, match="unique"):
        create_review_queue(assessments, review_budget=1)

    with pytest.raises(InvalidReviewBatch, match="unknown"):
        create_review_queue(
            [CaseAssessment("case-x", "risk_finding", 80, 20)],
            review_budget=1,
            known_case_ids=("case-a",),
        )

    with pytest.raises(InvalidReviewBatch, match="exactly"):
        create_review_queue(
            [CaseAssessment("case-a", "risk_finding", 80, 20)],
            review_budget=2,
        )


def test_binds_all_assessments_and_explains_the_first_excluded_case() -> None:
    ranker_cases = [
        asdict(build_development_cases()[0].ranker_case),
        asdict(build_development_cases()[1].ranker_case),
    ]
    allocator_config_digest = _test_digest("allocation-decision-config")
    assessments = [
        _risk_finding(case, allocator_config_digest=allocator_config_digest)
        for case in ranker_cases
    ]
    assessments[1]["risk_score"] = 51

    decision = allocate_review_queue(
        assessments=assessments,
        ranker_cases=ranker_cases,
        review_budget=1,
        receipt_id="ticket-16-receipt",
        evaluation_run_id="ticket-16-fixed-batch",
        corpus_digest=_test_digest("allocation-decision-corpus"),
        split_digest=_test_digest("allocation-decision-split"),
        allocator_config_digest=allocator_config_digest,
    )

    assert decision.review_queue == ("EQ-F01-DEV-01",)
    assert decision.receipt["first_excluded_case_id"] == "EQ-F01-DEV-02"
    assert decision.receipt["assessments"] == [
        {
            "case_id": "EQ-F01-DEV-01",
            "assessment_digest": digest_contract("case_assessment", assessments[0]),
        },
        {
            "case_id": "EQ-F01-DEV-02",
            "assessment_digest": digest_contract("case_assessment", assessments[1]),
        },
    ]
    assert decision.explanations[0].selected_ordering_fields == (
        "risk_finding",
        82,
        72,
        "EQ-F01-DEV-01",
    )
    assert decision.explanations[0].excluded_ordering_fields == (
        "risk_finding",
        51,
        42,
        "EQ-F01-DEV-02",
    )
    assert decision.explanations[0].first_differing_field == "risk_score"


def test_recomputes_the_fixed_batch_allocation_receipt_from_tracked_input() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures/ticket-16/fixed-batch-input.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    ranker_cases = fixture["ranker_cases"]
    allocator_config_digest = content_digest(fixture["allocator_configuration"])
    assessments = []
    for definition in fixture["assessment_definitions"]:
        case_id = definition["case_id"]
        ranker_case = next(case for case in ranker_cases if case["case_id"] == case_id)
        assessments.append(
            {
                "schema_version": "1.0",
                **definition,
                "evidence_references": [
                    {**reference, "case_id": case_id}
                    for reference in definition["evidence_references"]
                ],
                "allocator_config_digest": allocator_config_digest,
                "input_digest": digest_contract("ranker_case", ranker_case),
                "output_digest": content_digest(
                    {"assessment_definition": definition}
                ),
                "attempts": [
                    {
                        "schema_version": "1.0",
                        "attempt": 1,
                        "outcome": "accepted",
                    }
                ],
            }
        )
    receipt_path = (
        Path(__file__).parents[1]
        / "docs/evidence/ticket-16/fixed-batch-allocation-receipt.json"
    )
    expected_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    corpus_digest = content_digest({"ranker_cases": ranker_cases})
    split_digest = content_digest(
        {
            "split": "DEV",
            "case_digests": [case["content_digest"] for case in ranker_cases],
        }
    )
    receipt = allocate_review_queue(
        assessments=assessments,
        ranker_cases=ranker_cases,
        review_budget=fixture["receipt_metadata"]["review_budget"],
        receipt_id=fixture["receipt_metadata"]["receipt_id"],
        evaluation_run_id=fixture["receipt_metadata"]["evaluation_run_id"],
        corpus_digest=corpus_digest,
        split_digest=split_digest,
        allocator_config_digest=allocator_config_digest,
    ).receipt

    assert validate_allocation_receipt(receipt, assessments, ranker_cases) == receipt
    assert receipt == expected_receipt
