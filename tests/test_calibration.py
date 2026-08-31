import json
from dataclasses import replace
from pathlib import Path

import pytest

from edgequeue.calibration import (
    CalibrationCandidate,
    CalibrationHistory,
    CalibrationGateResult,
    BehavioralRegression,
    FrozenControls,
    PostCalibrationHoldoutInput,
    SplitComparisonInput,
    compare_calibration_candidate,
    create_calibration_candidate,
    evaluate_calibration_gate,
    record_human_decision,
    run_promoted_holdout_once,
)
from edgequeue.scoring import AllocationMetrics


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ticket-19" / "calibration-input.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _candidate(candidate_id: str) -> CalibrationCandidate:
    fixture = _fixture()
    return create_calibration_candidate(
        candidate_id=candidate_id,
        authorized_adjudication=fixture["authorized_adjudication"],
        reviewer_manifest=fixture["reviewer_manifest"],
        predecessor_pack=fixture["predecessor_pack"],
        guideline_amendments=("Prefer verified evidence over evaluator confidence.",),
        configuration_digests=fixture["configuration_digests"],
    )


def _comparison_inputs() -> tuple[SplitComparisonInput, ...]:
    controls = FrozenControls(
        model_digest="a" * 64,
        corpus_digest="b" * 64,
        scorer_digest="c" * 64,
        review_budget=4,
        metrics_digest="d" * 64,
        post_calibration_holdout_digest="e" * 64,
    )
    current_verdicts = {case_id: "PASS" for case_id in ("a", "b", "c", "d", "e")}
    reference_verdicts = {**current_verdicts, "a": "FAIL", "b": "FAIL"}
    return tuple(
        SplitComparisonInput(
            split=split,
            prior_review_queue=("a", "c", "d", "e"),
            candidate_review_queue=("a", "b", "c", "d"),
            current_verdicts=current_verdicts,
            reference_verdicts=reference_verdicts,
            prior_controls=controls,
            candidate_controls=controls,
        )
        for split in ("DEV", "AH")
    )


def _regressions(*, passed: bool) -> tuple[BehavioralRegression, ...]:
    return (BehavioralRegression("adversarial-signal-gaming", passed=passed, adversarial=True),)


def test_creates_an_immutable_candidate_from_an_authorized_adjudication() -> None:
    fixture = _fixture()
    candidate = _candidate("candidate-ticket-19-accepted")

    record = candidate.as_dict()
    assert record["status"] == "candidate"
    assert record["predecessor_digest"] == fixture["predecessor_pack"]["content_digest"]
    assert record["rollback_target"] == fixture["predecessor_pack"]["content_digest"]
    assert record["source_adjudication_digests"] == [candidate.source_adjudication_digest]
    assert record["calibration_case_digests"] == [candidate.calibration_case_digest]
    record["candidate_id"] = "mutated-caller-copy"
    assert candidate.as_dict()["candidate_id"] == "candidate-ticket-19-accepted"


def test_preserves_append_only_candidate_history_and_version_bindings() -> None:
    fixture = _fixture()
    first = create_calibration_candidate(
        candidate_id="candidate-ticket-19-first",
        authorized_adjudication=fixture["authorized_adjudication"],
        reviewer_manifest=fixture["reviewer_manifest"],
        predecessor_pack=fixture["predecessor_pack"],
        guideline_amendments=("Prefer verified evidence over evaluator confidence.",),
        configuration_digests=fixture["configuration_digests"],
    )
    second = create_calibration_candidate(
        candidate_id="candidate-ticket-19-second",
        authorized_adjudication=fixture["authorized_adjudication"],
        reviewer_manifest=fixture["reviewer_manifest"],
        predecessor_pack=fixture["predecessor_pack"],
        guideline_amendments=("Use the calibration case as a risk anchor.",),
        configuration_digests=fixture["configuration_digests"],
    )

    history = CalibrationHistory().append_candidate(first)
    expanded_history = history.append_candidate(second)

    assert [candidate.as_dict()["candidate_id"] for candidate in expanded_history.candidates] == [
        "candidate-ticket-19-first",
        "candidate-ticket-19-second",
    ]
    with pytest.raises(ValueError, match="already exists"):
        expanded_history.append_candidate(first)
    with pytest.raises(AttributeError, match="append-only"):
        expanded_history.candidates = ()


def test_compares_prior_and_candidate_packs_on_development_and_allocation_holdout() -> None:
    candidate = _candidate("candidate-ticket-19-comparison")

    report = compare_calibration_candidate(candidate, _comparison_inputs())

    assert [comparison.split for comparison in report.comparisons] == ["DEV", "AH"]
    assert all(comparison.prior_metrics.recall_at_k == 0.5 for comparison in report.comparisons)
    assert all(comparison.candidate_metrics.recall_at_k == 1.0 for comparison in report.comparisons)
    assert all(comparison.candidate_metrics.precision_at_k == 0.5 for comparison in report.comparisons)


def test_rejects_insufficient_recall_precision_decrease_and_named_regressions() -> None:
    report = compare_calibration_candidate(
        _candidate("candidate-ticket-19-gates"), _comparison_inputs(), regressions=_regressions(passed=True)
    )
    accepted = evaluate_calibration_gate(
        report,
        _regressions(passed=True),
    )
    recall_failure = evaluate_calibration_gate(
        replace(
            report,
            comparisons=tuple(
                replace(
                    comparison,
                    candidate_metrics=AllocationMetrics(0.6, 0.5, (), 0),
                )
                for comparison in report.comparisons
            ),
        ),
        _regressions(passed=True),
    )
    precision_failure = evaluate_calibration_gate(
        replace(
            report,
            comparisons=tuple(
                replace(
                    comparison,
                    candidate_metrics=AllocationMetrics(1.0, 0.2, (), 0),
                )
                for comparison in report.comparisons
            ),
        ),
        _regressions(passed=True),
    )
    regression_failure = evaluate_calibration_gate(
        report,
        _regressions(passed=False),
    )
    integrity_failure = evaluate_calibration_gate(
        replace(report, integrity_passed=False),
        _regressions(passed=True),
    )

    assert accepted.accepted
    assert "insufficient_recall_improvement:DEV" in recall_failure.failure_reasons
    assert "precision_decrease:DEV" in precision_failure.failure_reasons
    assert regression_failure.failure_reasons == ("named_behavioral_regression:adversarial-signal-gaming",)
    assert integrity_failure.failure_reasons == ("integrity_check_failed",)


def test_requires_a_separate_authorized_human_promotion_or_rejection_record() -> None:
    fixture = _fixture()
    candidate = _candidate("candidate-ticket-19-human-decision")
    report = compare_calibration_candidate(candidate, _comparison_inputs(), regressions=_regressions(passed=True))
    accepted_gate = evaluate_calibration_gate(
        report,
        _regressions(passed=True),
    )
    promotion = {
        "schema_version": "1.0",
        "promotion_id": "promotion-ticket-19-accepted",
        "candidate_digest": candidate.digest,
        "predecessor_digest": candidate.as_dict()["predecessor_digest"],
        "rollback_target": candidate.as_dict()["rollback_target"],
        "reviewer_id": "human-promoter",
        "reviewer_role": "calibration_promoter",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": fixture["reviewer_manifest"]["content_digest"],
        "decision": "promote",
        "rationale": "The candidate passed the frozen Calibration CI gates.",
    }

    history = CalibrationHistory().append_candidate(candidate)
    promoted_history = record_human_decision(
        history, candidate, report, accepted_gate, promotion, fixture["reviewer_manifest"]
    )

    decision = promoted_history.decisions[0]
    assert decision.status == "promoted"
    assert decision.pack["status"] == "promoted"

    rejected_candidate = _candidate("candidate-ticket-19-rejected")
    rejected_report = compare_calibration_candidate(rejected_candidate, _comparison_inputs(), regressions=_regressions(passed=False))
    rejected_gate = evaluate_calibration_gate(
        rejected_report,
        _regressions(passed=False),
    )
    rejection = {**promotion, "promotion_id": "promotion-ticket-19-rejected", "candidate_digest": rejected_candidate.digest, "decision": "reject", "rationale": "Removed after the named behavioral regression."}

    rejected_history = record_human_decision(
        promoted_history.append_candidate(rejected_candidate),
        rejected_candidate,
        rejected_report,
        rejected_gate,
        rejection,
        fixture["reviewer_manifest"],
    )

    assert rejected_history.decisions[-1].status == "rejected"
    assert rejected_history.decisions[-1].removal_reason == "Removed after the named behavioral regression."
    fabricated_candidate = _candidate("candidate-ticket-19-fabricated-gate")
    fabricated_report = compare_calibration_candidate(
        fabricated_candidate, _comparison_inputs(), regressions=_regressions(passed=True)
    )
    with pytest.raises(ValueError, match="must be issued"):
        record_human_decision(
            CalibrationHistory().append_candidate(fabricated_candidate),
            fabricated_candidate,
            fabricated_report,
            CalibrationGateResult(True, ()),
            {
                **promotion,
                "promotion_id": "promotion-ticket-19-fabricated-gate",
                "candidate_digest": fabricated_candidate.digest,
            },
            fixture["reviewer_manifest"],
        )
    with pytest.raises(ValueError, match="already has"):
        record_human_decision(
            history,
            candidate,
            report,
            accepted_gate,
            {**promotion, "reviewer_id": "human-reviewer"},
            fixture["reviewer_manifest"],
        )


def test_runs_a_promoted_candidate_once_on_the_untouched_post_calibration_holdout() -> None:
    fixture = _fixture()
    candidate = _candidate("candidate-ticket-19-post-calibration")
    report = compare_calibration_candidate(candidate, _comparison_inputs(), regressions=_regressions(passed=True))
    promotion = {
        "schema_version": "1.0",
        "promotion_id": "promotion-ticket-19-post-calibration",
        "candidate_digest": candidate.digest,
        "predecessor_digest": candidate.as_dict()["predecessor_digest"],
        "rollback_target": candidate.as_dict()["rollback_target"],
        "reviewer_id": "human-promoter",
        "reviewer_role": "calibration_promoter",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": fixture["reviewer_manifest"]["content_digest"],
        "decision": "promote",
        "rationale": "The candidate passed the frozen Calibration CI gates.",
    }
    promoted_history = record_human_decision(
        CalibrationHistory().append_candidate(candidate),
        candidate,
        report,
        evaluate_calibration_gate(
            report,
            _regressions(passed=True),
        ),
        promotion,
        fixture["reviewer_manifest"],
    )
    controls = report.controls
    holdout = PostCalibrationHoldoutInput(
        candidate_review_queue=("a", "b", "c", "d"),
        current_verdicts={case_id: "PASS" for case_id in ("a", "b", "c", "d", "e")},
        reference_verdicts={"a": "FAIL", "b": "FAIL", "c": "PASS", "d": "PASS", "e": "PASS"},
        controls=controls,
    )

    completed_history = run_promoted_holdout_once(
        promoted_history, candidate, report, holdout
    )

    assert completed_history.post_calibration_runs[0].metrics.recall_at_k == 1.0
    with pytest.raises(ValueError, match="already ran"):
        run_promoted_holdout_once(promoted_history, candidate, report, holdout)
    with pytest.raises(ValueError, match="already ran"):
        run_promoted_holdout_once(completed_history, candidate, report, holdout)
