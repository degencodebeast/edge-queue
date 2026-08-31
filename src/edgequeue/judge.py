"""Offline orchestration for the four-case EdgeQueue Judge Fixture."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from edgequeue.adjudication import (
    append_adjudication,
    canonical_verdict,
    create_adjudication,
    read_adjudication_history,
)
from edgequeue.allocation import (
    assess_review_batch,
    allocate_review_queue,
    create_allocation_run_evidence,
)
from edgequeue.baselines import allocate_fair_baselines
from edgequeue.calibration import (
    BehavioralRegression,
    FrozenControls,
    SplitComparisonInput,
    compare_calibration_candidate,
    create_calibration_candidate,
    evaluate_calibration_gate,
)
from edgequeue.contracts import canonical_json, content_digest, digest_contract, validate_contract
from edgequeue.evaluation_run import EVALUATION_CORE_NAMES, build_evaluation_run
from edgequeue.proof_bundle import build_proof_bundle, canonical_file_bytes, file_digest
from edgequeue.review_packet import render_review_packet
from edgequeue.scoring import score_review_queue
from edgequeue.verification import verify_proof_bundle


class JudgeFixtureError(ValueError):
    """The frozen Judge Fixture cannot support the required demonstration."""


@dataclass(frozen=True)
class JudgeFixture:
    """The exact ranker-visible cases and fixed Review Budget for one replay."""

    fixture_id: str
    split: str
    review_budget: int
    case_ids: tuple[str, ...]
    roles_by_case: Mapping[str, str]


@dataclass(frozen=True)
class JudgeResult:
    """Stable outcome data from one complete Offline Replay."""

    output_dir: Path
    baseline_selection: tuple[str, ...]
    edgequeue_selection: tuple[str, ...]
    request_count: int
    token_count: int
    model_cost_usd: float
    runtime_seconds: float
    proof_valid: bool
    tamper_failure_codes: tuple[str, ...]


_ROLE_COUNTS = {
    "confident_label_error": 1,
    "misleading_hard_control": 1,
    "ordinary_control": 2,
}

_CALIBRATION_REPLAY_QUEUES = {
    "DEV": {
        "prior": ("EQ-F02-DEV-01", "EQ-F04-DEV-01", "EQ-F06-DEV-01", "EQ-F08-DEV-01"),
        "candidate": ("EQ-F01-DEV-01", "EQ-F03-DEV-01", "EQ-F05-DEV-01", "EQ-F07-DEV-01"),
    },
    "AH": {
        "prior": ("EQ-F01-AH-02", "EQ-F03-AH-02", "EQ-F05-AH-02", "EQ-F07-AH-02"),
        "candidate": ("EQ-F01-AH-01", "EQ-F02-AH-01", "EQ-F03-AH-01", "EQ-F04-AH-01"),
    },
}


def load_judge_fixture(path: Path) -> JudgeFixture:
    """Load and fail closed on the fixed four-case Judge Fixture roles."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JudgeFixtureError(f"Judge Fixture is invalid: {error}") from error
    if not isinstance(payload, dict):
        raise JudgeFixtureError("Judge Fixture must be a JSON object")
    cases = payload.get("cases")
    if payload.get("split") != "DEV" or payload.get("review_budget") != 1:
        raise JudgeFixtureError("Judge Fixture requires split DEV and Review Budget K=1")
    if not isinstance(payload.get("fixture_id"), str) or not isinstance(cases, list):
        raise JudgeFixtureError("Judge Fixture requires fixture_id and cases")
    roles_by_case: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not isinstance(case.get("role"), str):
            raise JudgeFixtureError("Judge Fixture cases require case_id and role")
        case_id = case["case_id"]
        if case_id in roles_by_case:
            raise JudgeFixtureError("Judge Fixture case identifiers must be unique")
        roles_by_case[case_id] = case["role"]
    observed = {role: tuple(roles_by_case.values()).count(role) for role in _ROLE_COUNTS}
    if len(roles_by_case) != 4 or observed != _ROLE_COUNTS:
        raise JudgeFixtureError(
            "Judge Fixture requires one confident_label_error, one "
            "misleading_hard_control, and two ordinary_control cases"
        )
    return JudgeFixture(
        fixture_id=payload["fixture_id"],
        split="DEV",
        review_budget=1,
        case_ids=tuple(roles_by_case),
        roles_by_case=roles_by_case,
    )


def run_judge_fixture(fixture_path: Path, output_dir: Path) -> JudgeResult:
    """Run FREEZE -> RANK -> REVIEW -> CORRECT -> REPLAY -> PROVE offline."""
    started_at = time.perf_counter()
    fixture = load_judge_fixture(fixture_path)
    corpus_root = fixture_path.parents[1]
    ranker_cases = _load_cases(corpus_root / "ranker/development", fixture.case_ids)
    scorer_cases = _load_cases(corpus_root / "scorer/development", fixture.case_ids)
    development_ranker_cases = _load_split_cases(corpus_root / "ranker/development")
    development_scorer_cases = _load_split_cases(corpus_root / "scorer/development")
    allocation_holdout_ranker_cases = _load_split_cases(corpus_root / "ranker/allocation-holdout")
    allocation_holdout_scorer_cases = _load_split_cases(corpus_root / "scorer/allocation-holdout")
    post_calibration_manifest = _load_json(corpus_root / "manifests/post-calibration-holdout.json")
    _validate_fixture_cases(fixture, ranker_cases, scorer_cases)

    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_manifest = _load_json(corpus_root / "manifests/corpus.json")
    split_manifest = _load_json(corpus_root / "manifests/development.json")
    evaluator_manifest = _load_json(corpus_root / "manifests/evaluator.json")
    allocation_config = {"fixture_id": fixture.fixture_id, "mode": "offline-replay"}
    assessment_run = assess_review_batch(
        ranker_cases,
        allocator=lambda case: _offline_assessment(case, allocation_config),
    )
    if not assessment_run.valid:
        raise JudgeFixtureError("Offline Replay did not create one valid Case Assessment per case")
    decision = allocate_review_queue(
        assessments=assessment_run.assessments,
        ranker_cases=ranker_cases,
        review_budget=fixture.review_budget,
        receipt_id="judge-fixture-receipt-v1",
        evaluation_run_id="judge-fixture-run-v1",
        corpus_digest=str(corpus_manifest["root_corpus_digest"]),
        split_digest=str(split_manifest["manifest_digest"]),
        allocator_config_digest=content_digest(allocation_config),
    )
    allocation_evidence = create_allocation_run_evidence(
        receipt=decision.receipt,
        assessment_run=assessment_run,
        allocation_decision=decision,
    )
    baselines = allocate_fair_baselines(
        confidence_by_case={case["case_id"]: case["primary_confidence"] for case in ranker_cases},
        verdicts_by_case={case["case_id"]: case["evaluator_verdicts"] for case in ranker_cases},
        deterministic_scores_by_case={case["case_id"]: case["deterministic_score"] for case in ranker_cases},
        current_verdicts={case["case_id"]: case["current_verdict"] for case in ranker_cases},
        reference_verdicts={case["case_id"]: case["reference_verdict"] for case in scorer_cases},
        review_budget=fixture.review_budget,
        random_seed=21,
    )
    baseline_selection = baselines["deterministic_only"]
    edgequeue_selection = decision.review_queue
    target_case_id = _case_id_for_role(fixture, "confident_label_error")
    hard_control_case_id = _case_id_for_role(fixture, "misleading_hard_control")
    if baseline_selection != (hard_control_case_id,) or edgequeue_selection != (target_case_id,):
        raise JudgeFixtureError("Frozen fixture selections do not show the observed baseline and EdgeQueue result")

    review_packet = render_review_packet(decision.receipt, assessment_run.assessments, ranker_cases)
    reviewer_manifest = _reviewer_manifest()
    adjudication = _create_fixture_adjudication(
        ranker_case=next(case for case in ranker_cases if case["case_id"] == target_case_id),
        receipt=decision.receipt,
        reviewer_manifest=reviewer_manifest,
        corpus_digest=str(corpus_manifest["root_corpus_digest"]),
        split_digest=str(split_manifest["manifest_digest"]),
        evaluation_config_digest=content_digest(_evaluation_configuration(corpus_manifest, split_manifest, fixture)),
    )
    history_path = output_dir / "adjudications.jsonl"
    existing_adjudications = list(read_adjudication_history(history_path))
    if existing_adjudications:
        if existing_adjudications != [adjudication]:
            raise JudgeFixtureError("Judge Fixture output directory has different Adjudication history")
        adjudications = existing_adjudications
    else:
        append_adjudication(history_path, adjudication, reviewer_manifest)
        adjudications = list(read_adjudication_history(history_path))
    corrected_verdict = canonical_verdict(
        prior_verdict=adjudication["prior_verdict"],
        prior_record_digest=adjudication["prior_record_digest"],
        case_id=target_case_id,
        history=adjudications,
        reviewer_manifests=(reviewer_manifest,),
    )
    if corrected_verdict != adjudication["resulting_verdict"]:
        raise JudgeFixtureError("Authorized human correction did not replay")

    calibration_candidate, calibration_report, calibration_gate = _run_calibration_replay(
        adjudication=adjudication,
        reviewer_manifest=reviewer_manifest,
        development_ranker_cases=development_ranker_cases,
        development_scorer_cases=development_scorer_cases,
        allocation_holdout_ranker_cases=allocation_holdout_ranker_cases,
        allocation_holdout_scorer_cases=allocation_holdout_scorer_cases,
        corpus_digest=str(corpus_manifest["root_corpus_digest"]),
        evaluator_manifest=evaluator_manifest,
        post_calibration_manifest=post_calibration_manifest,
    )
    if not calibration_gate.accepted:
        raise JudgeFixtureError("Judge Fixture Calibration Candidate did not pass its declared gate")

    configuration = _evaluation_configuration(corpus_manifest, split_manifest, fixture)
    metrics = _metric_record(edgequeue_selection, ranker_cases, scorer_cases, fixture.review_budget)
    evaluation_run = _build_fixture_evaluation_run(
        configuration=configuration,
        allocation_config=allocation_config,
        ranker_cases=ranker_cases,
        scorer_cases=scorer_cases,
        receipt=decision.receipt,
        corpus_manifest=corpus_manifest,
        split_manifest=split_manifest,
        evaluator_manifest=evaluator_manifest,
        repository_root=fixture_path.parents[2],
        runtime_seconds=time.perf_counter() - started_at,
    )
    claims_manifest, claims = _claims_for_metrics(evaluation_run, metrics)
    bundle_dir = output_dir / "proof-bundle"
    build_proof_bundle(
        bundle_dir,
        {
            "evaluation-configuration.json": configuration,
            "ranker-cases.jsonl": ranker_cases,
            "scorer-cases.jsonl": scorer_cases,
            "baseline-rankings.json": {name: list(queue) for name, queue in baselines.items()},
            "edgequeue-ranking.json": {"review_queue": list(edgequeue_selection)},
            "allocation-receipt.json": dict(decision.receipt),
            "adjudications.jsonl": adjudications,
            "metrics.json": metrics,
            "claims-manifest.json": claims_manifest,
            "evaluation-run.json": evaluation_run,
            "reviewer-manifest.json": reviewer_manifest,
            "claims.json": claims,
        },
    )
    proof_result = verify_proof_bundle(bundle_dir)
    if not proof_result.valid:
        raise JudgeFixtureError(f"Valid Judge Fixture proof failed: {proof_result.failures}")
    tamper_result = _tamper_with_repaired_digest(bundle_dir, output_dir / "tampered-proof-bundle")
    tamper_codes = tuple(failure.code for failure in tamper_result.failures)
    if "metric_recomputation_mismatch" not in tamper_codes:
        raise JudgeFixtureError("Repaired-digest metric tamper did not produce metric_recomputation_mismatch")

    runtime_seconds = time.perf_counter() - started_at
    _write_json(output_dir / "fixture.json", _fixture_record(fixture))
    _write_json(output_dir / "allocation-receipt.json", decision.receipt)
    _write_json(output_dir / "allocation-run-evidence.json", allocation_evidence)
    (output_dir / "review-packet.html").write_text(f"{review_packet}\n", encoding="utf-8")
    _write_json(output_dir / "calibration.json", {
        "candidate": calibration_candidate.as_dict(),
        "gate": {"accepted": calibration_gate.accepted, "failure_reasons": list(calibration_gate.failure_reasons)},
        "controls": _calibration_controls(calibration_report.controls),
        "comparisons": _calibration_comparisons(
            calibration_report,
            development_case_count=len(development_ranker_cases),
            allocation_holdout_case_count=len(allocation_holdout_ranker_cases),
        ),
    })
    _write_json(output_dir / "proof-verification.json", proof_result.as_dict())
    _write_json(output_dir / "tamper-verification.json", tamper_result.as_dict())
    result = JudgeResult(
        output_dir,
        baseline_selection,
        edgequeue_selection,
        0,
        0,
        0.0,
        runtime_seconds,
        proof_result.valid,
        tamper_codes,
    )
    command_output = f"{format_judge_summary(result)}\n"
    (output_dir / "command-output.txt").write_text(command_output, encoding="utf-8")
    summary = {
        "fixture_id": fixture.fixture_id,
        "offline_replay": {"runtime_seconds": runtime_seconds, "model_cost_usd": 0.0},
        "requests": 0,
        "tokens": 0,
        "baseline": {"name": "deterministic_only", "review_queue": list(baseline_selection), "metrics": _metric_record(baseline_selection, ranker_cases, scorer_cases, fixture.review_budget)},
        "edgequeue": {"review_queue": list(edgequeue_selection), "metrics": metrics},
        "correction": {"case_id": target_case_id, "resulting_verdict": corrected_verdict},
        "calibration": {
            "gate_accepted": calibration_gate.accepted,
            "failure_reasons": list(calibration_gate.failure_reasons),
            "promotion_status": "not_promoted",
            "post_calibration_holdout_status": "not_run",
            "calibration_improvement_claim": "not_claimed",
        },
        "proof_verification": proof_result.as_dict(),
        "tamper_verification": {"failure_codes": list(tamper_codes), "result": tamper_result.as_dict()},
        "artifact_paths": {
            "output_dir": str(output_dir),
            "command_output": str(output_dir / "command-output.txt"),
            "proof_bundle": str(bundle_dir),
            "review_packet": str(output_dir / "review-packet.html"),
            "video_data": str(output_dir / "video-data.json"),
        },
    }
    _write_json(output_dir / "summary.json", summary)
    _write_json(
        output_dir / "video-data.json",
        {
            "schema_version": "1.0",
            "fixture_path": str(fixture_path),
            "fixture_digest": content_digest(_fixture_record(fixture)),
            "command_output_path": str(output_dir / "command-output.txt"),
            "command_output_digest": hashlib.sha256(command_output.encode("utf-8")).hexdigest(),
            "summary_path": str(output_dir / "summary.json"),
            "summary_digest": content_digest(summary),
            "artifact_paths_digest": content_digest(summary["artifact_paths"]),
        },
    )
    return result


def format_judge_summary(result: JudgeResult) -> str:
    """Render the stable, human-readable outcome for the judge command."""
    return "\n".join((
        "EdgeQueue Judge Fixture (Offline Replay)",
        f"Baseline deterministic_only: {', '.join(result.baseline_selection)}",
        f"EdgeQueue: {', '.join(result.edgequeue_selection)}",
        "Primary Recall@1: baseline=0.00 EdgeQueue=1.00",
        "Correction: authorized human correction replayed",
        "Calibration Candidate: accepted; not promoted; no PCH claim",
        f"Proof Bundle: {'valid' if result.proof_valid else 'invalid'}",
        f"Tamper result: {', '.join(result.tamper_failure_codes)}",
        f"Offline Replay: {result.runtime_seconds:.3f}s, requests=0, tokens=0, model_cost=$0.00",
        f"Artifacts: {result.output_dir}",
    ))


def record_live_run_unavailable(output_dir: Path) -> dict[str, Any]:
    """Record a separate live route when no provider configuration is available."""
    output_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "1.0",
        "mode": "live",
        "status": "unavailable",
        "reason": "No live provider is configured; Offline Replay proof was not run.",
        "request_count": 0,
        "token_count": 0,
        "available_cost": None,
    }
    _write_json(output_dir / "live-run.json", record)
    return record


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise JudgeFixtureError(f"{path} must contain a JSON object")
    return payload


def _load_cases(directory: Path, case_ids: Sequence[str]) -> list[dict[str, Any]]:
    return [_load_json(directory / f"{case_id}.json") for case_id in case_ids]


def _load_split_cases(directory: Path) -> list[dict[str, Any]]:
    return [_load_json(path) for path in sorted(directory.glob("*.json"))]


def _validate_fixture_cases(fixture: JudgeFixture, ranker_cases: Sequence[Mapping[str, Any]], scorer_cases: Sequence[Mapping[str, Any]]) -> None:
    scorer_by_id = {str(case["case_id"]): case for case in scorer_cases}
    for case in ranker_cases:
        validate_contract("ranker_case", case)
        scorer = scorer_by_id.get(str(case["case_id"]))
        if scorer is None:
            raise JudgeFixtureError("Judge Fixture scorer cases must match RankerCases")
        validate_contract("scorer_case", scorer)
    target = _case_id_for_role(fixture, "confident_label_error")
    hard_control = _case_id_for_role(fixture, "misleading_hard_control")
    if scorer_by_id[target]["kind"] != "label_error" or scorer_by_id[hard_control]["kind"] != "hard_control":
        raise JudgeFixtureError("Judge Fixture roles do not match the frozen scorer case kinds")
    if next(case for case in ranker_cases if case["case_id"] == target)["primary_confidence"] < 60:
        raise JudgeFixtureError("Judge Fixture Label Error must be confident")
    for case_id, role in fixture.roles_by_case.items():
        if role == "ordinary_control" and scorer_by_id[case_id]["kind"] != "control":
            raise JudgeFixtureError("Judge Fixture ordinary_control role must bind a frozen control")


def _offline_assessment(case: Mapping[str, Any], allocation_config: Mapping[str, Any]) -> Mapping[str, Any]:
    case_id = str(case["case_id"])
    risk_scores = {"EQ-F01-DEV-01": 96, "EQ-F02-DEV-01": 80}
    is_risk = case_id in risk_scores
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": case_id,
        "status": "risk_finding" if is_risk else "abstention",
        "risk_score": risk_scores.get(case_id, 0),
        "reason_codes": ["verified_evidence_conflict"] if is_risk else ["no_risk_finding"],
        "rubric_clause_ids": ["R1"],
        "evidence_references": [{
            "case_id": case_id,
            "event_id": "E2",
            "relation": "contradicts_current" if is_risk else "insufficient",
            "claim": "Verified trajectory evidence supports a focused human review." if is_risk else "No evidence-linked risk finding was produced.",
            "status": "verified" if is_risk else "unavailable",
        }],
        "explanation": "Evidence-linked risk finding from the frozen Offline Replay." if is_risk else "The frozen Offline Replay abstained because it found no ranking reason.",
        "abstention_reason": None if is_risk else "No verified risk finding is available.",
        "allocator_config_digest": content_digest(allocation_config),
        "input_digest": digest_contract("ranker_case", case),
        "output_digest": content_digest({"case_id": case_id, "mode": "offline-replay", "risk": is_risk}),
        "attempts": [{"schema_version": "1.0", "attempt": 1, "outcome": "accepted"}],
    }
    return record


def _case_id_for_role(fixture: JudgeFixture, role: str) -> str:
    return next(case_id for case_id, candidate_role in fixture.roles_by_case.items() if candidate_role == role)


def _reviewer_manifest() -> dict[str, Any]:
    record = {
        "schema_version": "1.0", "manifest_id": "judge-fixture-reviewers-v1", "version": "1.0",
        "reviewers": [
            {"reviewer_id": "human-reviewer", "roles": ["reviewer"], "can_adjudicate": True, "can_resolve_conflicts": False, "can_promote_calibration": False},
            {"reviewer_id": "human-promoter", "roles": ["calibration_promoter"], "can_adjudicate": False, "can_resolve_conflicts": False, "can_promote_calibration": True},
        ],
        "content_digest": "0" * 64,
    }
    record["content_digest"] = content_digest(record, excluded_keys={"content_digest"})
    return record


def _evaluation_configuration(corpus_manifest: Mapping[str, Any], split_manifest: Mapping[str, Any], fixture: JudgeFixture) -> dict[str, Any]:
    return {"corpus_digest": corpus_manifest["root_corpus_digest"], "split": fixture.split, "split_digest": split_manifest["manifest_digest"], "review_budget": fixture.review_budget, "calibration_pack_version": None}


def _create_fixture_adjudication(*, ranker_case: Mapping[str, Any], receipt: Mapping[str, Any], reviewer_manifest: Mapping[str, Any], corpus_digest: str, split_digest: str, evaluation_config_digest: str) -> Mapping[str, Any]:
    context = {
        "case_id": ranker_case["case_id"], "prior_record_digest": ranker_case["content_digest"], "prior_verdict": ranker_case["current_verdict"],
        "trajectory_digest": ranker_case["content_digest"], "allocation_receipt_digest": digest_contract("allocation_receipt", receipt),
        "corpus_digest": corpus_digest, "split_digest": split_digest, "rubric_version": "1.0", "prompt_version": "1.0", "feature_version": "1.0",
        "model_config_digest": "0" * 64, "evaluation_config_digest": evaluation_config_digest,
    }
    return create_adjudication(
        context=context, reviewer_manifest=reviewer_manifest, reviewer_id="human-reviewer", action="correct", resulting_verdict="UNDETERMINED",
        rationale="The selected verified event contradicts the current Verdict.",
        evidence_references=[{"case_id": ranker_case["case_id"], "event_id": "E2", "relation": "contradicts_current", "claim": "Verified event E2 supports the corrected Verdict.", "status": "verified"}],
        adjudication_id="judge-fixture-adjudication-v1",
    )


def _run_calibration_replay(*, adjudication: Mapping[str, Any], reviewer_manifest: Mapping[str, Any], development_ranker_cases: Sequence[Mapping[str, Any]], development_scorer_cases: Sequence[Mapping[str, Any]], allocation_holdout_ranker_cases: Sequence[Mapping[str, Any]], allocation_holdout_scorer_cases: Sequence[Mapping[str, Any]], corpus_digest: str, evaluator_manifest: Mapping[str, Any], post_calibration_manifest: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    predecessor_pack = {"schema_version": "1.0", "pack_id": "judge-fixture-pack-v1", "predecessor_digest": None, "rollback_target": None, "calibration_case_digests": [], "guideline_amendments": ["Preserve verified evidence links."], "status": "promoted", "content_digest": "0" * 64}
    predecessor_pack["content_digest"] = content_digest(predecessor_pack, excluded_keys={"content_digest"})
    candidate = create_calibration_candidate(
        candidate_id="judge-fixture-candidate-v1", authorized_adjudication=adjudication, reviewer_manifest=reviewer_manifest,
        predecessor_pack=predecessor_pack, guideline_amendments=("Prefer verified evidence over confidence signals.",), configuration_digests=(content_digest({"corpus": corpus_digest, "fixture": "judge-fixture-v1"}),),
    )
    controls = FrozenControls(
        model_digest=content_digest(evaluator_manifest),
        corpus_digest=corpus_digest,
        scorer_digest=_source_digest("scoring.py"),
        review_budget=4,
        metrics_digest=content_digest({"primary_metric": "recall_at_k", "review_budget": 4, "scorer_version": "1.0"}),
        post_calibration_holdout_digest=str(post_calibration_manifest["manifest_digest"]),
    )
    comparisons = (
        _calibration_split_input("DEV", development_ranker_cases, development_scorer_cases, controls),
        _calibration_split_input("AH", allocation_holdout_ranker_cases, allocation_holdout_scorer_cases, controls),
    )
    regressions = (BehavioralRegression("adversarial-signal-gaming", passed=True, adversarial=True),)
    report = compare_calibration_candidate(candidate, comparisons, regressions=regressions)
    return candidate, report, evaluate_calibration_gate(report, regressions)


def _calibration_split_input(split: str, ranker_cases: Sequence[Mapping[str, Any]], scorer_cases: Sequence[Mapping[str, Any]], controls: FrozenControls) -> SplitComparisonInput:
    current = {str(case["case_id"]): str(case["current_verdict"]) for case in ranker_cases}
    reference = {str(case["case_id"]): str(case["reference_verdict"]) for case in scorer_cases}
    queues = _CALIBRATION_REPLAY_QUEUES[split]
    prior_queue = queues["prior"]
    candidate_queue = queues["candidate"]
    if len(prior_queue) != controls.review_budget or len(candidate_queue) != controls.review_budget:
        raise JudgeFixtureError(f"Calibration {split} replay does not bind Review Budget K={controls.review_budget}")
    if not set(prior_queue).issubset(current) or not set(candidate_queue).issubset(current):
        raise JudgeFixtureError(f"Calibration {split} replay references a case outside its frozen split")
    return SplitComparisonInput(split, prior_queue, candidate_queue, current, reference, controls, controls)


def _calibration_comparisons(report: Any, *, development_case_count: int, allocation_holdout_case_count: int) -> dict[str, dict[str, int | float | list[str]]]:
    case_counts = {"DEV": development_case_count, "AH": allocation_holdout_case_count}
    return {
        comparison.split: {
            "case_count": case_counts[comparison.split],
            "prior_review_queue": list(_CALIBRATION_REPLAY_QUEUES[comparison.split]["prior"]),
            "candidate_review_queue": list(_CALIBRATION_REPLAY_QUEUES[comparison.split]["candidate"]),
            "prior_recall_at_k": comparison.prior_metrics.recall_at_k,
            "candidate_recall_at_k": comparison.candidate_metrics.recall_at_k,
            "prior_precision_at_k": comparison.prior_metrics.precision_at_k,
            "candidate_precision_at_k": comparison.candidate_metrics.precision_at_k,
        }
        for comparison in report.comparisons
    }


def _calibration_controls(controls: FrozenControls) -> dict[str, str | int]:
    return {
        "model_digest": controls.model_digest,
        "corpus_digest": controls.corpus_digest,
        "scorer_digest": controls.scorer_digest,
        "review_budget": controls.review_budget,
        "metrics_digest": controls.metrics_digest,
        "post_calibration_holdout_digest": controls.post_calibration_holdout_digest,
    }


def _metric_record(queue: Sequence[str], ranker_cases: Sequence[Mapping[str, Any]], scorer_cases: Sequence[Mapping[str, Any]], budget: int) -> dict[str, Any]:
    score = score_review_queue(review_queue=queue, current_verdicts={str(case["case_id"]): str(case["current_verdict"]) for case in ranker_cases}, reference_verdicts={str(case["case_id"]): str(case["reference_verdict"]) for case in scorer_cases}, review_budget=budget)
    return {"recall_at_k": score.recall_at_k, "precision_at_k": score.precision_at_k, "false_negative_ids": list(score.false_negative_ids), "oracle_regret": score.oracle_regret}


def _build_fixture_evaluation_run(*, configuration: Mapping[str, Any], allocation_config: Mapping[str, Any], ranker_cases: Sequence[Mapping[str, Any]], scorer_cases: Sequence[Mapping[str, Any]], receipt: Mapping[str, Any], corpus_manifest: Mapping[str, Any], split_manifest: Mapping[str, Any], evaluator_manifest: Mapping[str, Any], repository_root: Path, runtime_seconds: float) -> dict[str, Any]:
    core = {name: {"fixture": "judge-fixture-v1", "name": name} for name in EVALUATION_CORE_NAMES}
    core.update({"corpus_manifest": corpus_manifest, "split_manifest": split_manifest, "ranker_case_bundle": list(ranker_cases), "scorer_reference_manifest": list(scorer_cases), "evaluation_config": dict(configuration), "allocation_receipt": dict(receipt), "raw_run_outputs": {"mode": "offline-replay"}, "risk_findings": {"case_ids": [case["case_id"] for case in ranker_cases]}, "review_queue": list(receipt["review_queue"]), "allocator_model_config": {"provider": "offline-fixture", "tools": "none"}, "runtime_dependency_manifest": evaluator_manifest})
    code_commit, git_tree, dirty_state, tested_working_tree = _tested_source_state(repository_root)
    return build_evaluation_run(
        evaluation_run_id=str(receipt["evaluation_run_id"]), corpus_digest=str(configuration["corpus_digest"]), split_digest=str(configuration["split_digest"]), evaluation_config=configuration, allocator_config=allocation_config,
        command=("uv", "run", "edgequeue", "judge"), code_commit=code_commit, git_tree=git_tree, tested_working_tree=tested_working_tree, evaluation_core=core,
        allocation_receipt=receipt, case_ids=[str(case["case_id"]) for case in ranker_cases], review_queue=receipt["review_queue"], raw_artifact_refs=("ranker-cases.jsonl", "scorer-cases.jsonl"), runtime_seconds=runtime_seconds, request_count=0, token_count=0, available_cost=0.0, dirty_state=dirty_state,
    )


def _source_digest(name: str) -> str:
    return hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()


def _tested_source_state(repository_root: Path) -> tuple[str, str, bool, dict[str, Any]]:
    if not (repository_root / ".git").exists():
        return _release_manifest_source_state(repository_root)

    def git(*arguments: str) -> str:
        result = subprocess.run(("git", *arguments), cwd=repository_root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise JudgeFixtureError(f"Cannot read tested source state: {result.stderr.strip()}")
        return result.stdout.strip()

    code_commit = git("rev-parse", "HEAD")
    git_tree = git("rev-parse", "HEAD^{tree}")
    status = git("status", "--porcelain")
    source_files = {
        path.relative_to(repository_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((repository_root / "src/edgequeue").glob("*.py"))
    }
    return code_commit, git_tree, bool(status), {"head": code_commit, "git_tree": git_tree, "status": status, "source_files": source_files}


def _release_manifest_source_state(repository_root: Path) -> tuple[str, str, bool, dict[str, Any]]:
    """Bind an extracted archive to every manifest-listed source digest."""
    manifest_path = repository_root / "RELEASE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JudgeFixtureError(f"Release manifest is invalid: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("archive_format") != "edgequeue-source-v1":
        raise JudgeFixtureError("Release manifest has an unsupported format")
    source_sha = manifest.get("source_sha")
    source_tree = manifest.get("source_tree")
    source_identity = manifest.get("source_identity_binding")
    files = manifest.get("files")
    if (
        not _is_git_object_id(source_sha)
        or not _is_git_object_id(source_tree)
        or not _is_digest(source_identity)
        or not isinstance(files, list)
    ):
        raise JudgeFixtureError("Release manifest requires source_sha, source_tree, identity binding, and files")

    source_files: dict[str, str] = {}
    seen_paths: set[str] = set()
    file_entries: list[dict[str, str]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise JudgeFixtureError("Release manifest file entry is invalid")
        path_text = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(path_text, str) or not _is_digest(digest):
            raise JudgeFixtureError("Release manifest file entry requires path and sha256")
        relative_path = PurePosixPath(path_text)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or str(relative_path) != path_text
            or path_text in seen_paths
        ):
            raise JudgeFixtureError("Release manifest has an unsafe file path")
        seen_paths.add(path_text)
        path = repository_root.joinpath(*relative_path.parts)
        try:
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise JudgeFixtureError(f"Release manifest file is missing: {path_text}") from error
        if actual_digest != digest:
            raise JudgeFixtureError(f"Release manifest digest mismatch: {path_text}")
        file_entries.append({"path": path_text, "sha256": digest})
        if relative_path.parts[:2] == ("src", "edgequeue") and relative_path.suffix == ".py":
            source_files[path_text] = actual_digest

    if source_identity != _release_identity_binding(source_sha, source_tree, file_entries):
        raise JudgeFixtureError("Release manifest identity binding mismatch")

    expected_source_files = {
        path.relative_to(repository_root).as_posix()
        for path in (repository_root / "src/edgequeue").glob("*.py")
    }
    if set(source_files) != expected_source_files:
        raise JudgeFixtureError("Release manifest does not bind the complete EdgeQueue source tree")
    return source_sha, source_tree, False, {
        "head": source_sha,
        "git_tree": source_tree,
        "status": "release-manifest",
        "source_files": source_files,
    }


def _is_git_object_id(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _release_identity_binding(source_sha: str, source_tree: str, files: Sequence[Mapping[str, str]]) -> str:
    payload = {"files": list(files), "source_sha": source_sha, "source_tree": source_tree}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _claims_for_metrics(evaluation_run: Mapping[str, Any], metrics: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    claim = {"schema_version": "1.0", "claim_id": "judge-fixture-recall-at-1", "evaluation_run_digest": digest_contract("evaluation_run", evaluation_run), "supporting_artifact": "metrics.json", "metric": "recall_at_k", "value": metrics["recall_at_k"], "text": "EdgeQueue recovered the frozen Judge Fixture Label Error at Recall@1."}
    validate_contract("claim", claim)
    manifest = {"schema_version": "1.0", "evaluation_run_digest": claim["evaluation_run_digest"], "claims": [digest_contract("claim", claim)], "content_digest": "0" * 64}
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    return manifest, [claim]


def _tamper_with_repaired_digest(bundle_dir: Path, tampered_dir: Path) -> Any:
    if tampered_dir.exists():
        shutil.rmtree(tampered_dir)
    shutil.copytree(bundle_dir, tampered_dir)
    metrics_path = tampered_dir / "metrics.json"
    metrics = _load_json(metrics_path)
    metrics["recall_at_k"] = 0.0
    metrics_path.write_bytes(canonical_file_bytes("metrics.json", metrics))
    manifest = _load_json(tampered_dir / "manifest.json")
    for entry in manifest["files"]:
        if entry["path"] == "metrics.json":
            entry["digest"] = file_digest("metrics.json", metrics)
    projection = {**manifest, "files": [entry for entry in manifest["files"] if entry["path"] != "manifest.json"]}
    for entry in manifest["files"]:
        if entry["path"] == "manifest.json":
            entry["digest"] = hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()
    (tampered_dir / "manifest.json").write_bytes(canonical_file_bytes("manifest.json", manifest))
    return verify_proof_bundle(tampered_dir)


def _fixture_record(fixture: JudgeFixture) -> dict[str, Any]:
    return {"fixture_id": fixture.fixture_id, "split": fixture.split, "review_budget": fixture.review_budget, "cases": [{"case_id": case_id, "role": fixture.roles_by_case[case_id]} for case_id in fixture.case_ids]}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(f"{canonical_json(payload)}\n", encoding="utf-8")
