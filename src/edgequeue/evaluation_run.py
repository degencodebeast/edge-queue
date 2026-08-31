"""Create immutable EvaluationRun records from frozen allocation inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from edgequeue.contracts import content_digest, validate_contract
from edgequeue.scoring import score_review_queue


EVALUATION_CORE_NAMES: Final[tuple[str, ...]] = (
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


class EvaluationRunError(ValueError):
    """The supplied allocation result cannot form one EvaluationRun."""


def build_evaluation_run(
    *,
    evaluation_run_id: str,
    corpus_digest: str,
    split_digest: str,
    evaluation_config: Mapping[str, Any],
    allocator_config: Mapping[str, Any],
    command: Sequence[str],
    code_commit: str,
    git_tree: str,
    tested_working_tree: Mapping[str, Any],
    evaluation_core: Mapping[str, Any],
    allocation_receipt: Mapping[str, Any],
    case_ids: Sequence[str],
    review_queue: Sequence[str],
    raw_artifact_refs: Sequence[str],
    runtime_seconds: float,
    request_count: int,
    token_count: int,
    available_cost: float | None,
    scorer_version: str = "1.0",
    exit_code: int = 0,
    dirty_state: bool = False,
    optional_absences: Sequence[str] = (),
) -> dict[str, Any]:
    """Bind one complete offline allocation result into an EvaluationRun."""
    missing = set(EVALUATION_CORE_NAMES) - set(evaluation_core)
    extra = set(evaluation_core) - set(EVALUATION_CORE_NAMES)
    if missing or extra:
        raise EvaluationRunError(
            f"Evaluation Core names differ. Missing: {sorted(missing)}; extra: {sorted(extra)}"
        )
    if list(review_queue) != list(allocation_receipt["review_queue"]):
        raise EvaluationRunError("Review Queue must match the Allocation Receipt")
    if allocation_receipt["evaluation_run_id"] != evaluation_run_id:
        raise EvaluationRunError("Allocation Receipt must bind the EvaluationRun identifier")
    if allocation_receipt["corpus_digest"] != corpus_digest or allocation_receipt["split_digest"] != split_digest:
        raise EvaluationRunError("Allocation Receipt must bind the EvaluationRun corpus and split")
    if allocation_receipt["allocator_config_digest"] != content_digest(allocator_config):
        raise EvaluationRunError("Allocation Receipt must bind the allocator configuration")
    if content_digest(evaluation_core["allocation_receipt"]) != content_digest(allocation_receipt):
        raise EvaluationRunError("Evaluation Core must bind the supplied Allocation Receipt")
    if int(allocation_receipt["review_budget"]) != int(evaluation_config["review_budget"]):
        raise EvaluationRunError("Review Budget must match the evaluation configuration")

    core = {
        name: {"name": name, "digest": content_digest(evaluation_core[name])}
        for name in EVALUATION_CORE_NAMES
    }
    run: dict[str, Any] = {
        "schema_version": "1.0",
        "evaluation_run_id": evaluation_run_id,
        "corpus_digest": corpus_digest,
        "split_digest": split_digest,
        "evaluation_config_digest": content_digest(evaluation_config),
        "allocator_config_digest": content_digest(allocator_config),
        "scorer_version": scorer_version,
        "command_digest": content_digest(list(command)),
        "code_commit": code_commit,
        "git_tree": git_tree,
        "dirty_state": dirty_state,
        "tested_working_tree_digest": content_digest(tested_working_tree),
        "evaluation_core": {**core, "optional_absences": list(optional_absences)},
        "exit_code": exit_code,
        "review_budget": int(evaluation_config["review_budget"]),
        "case_ids": list(case_ids),
        "review_queue": list(review_queue),
        "allocation_receipt_digest": content_digest(allocation_receipt),
        "disposition": "valid" if exit_code == 0 else "invalid",
        "raw_artifact_refs": list(raw_artifact_refs),
        "runtime_seconds": runtime_seconds,
        "request_count": request_count,
        "token_count": token_count,
        "available_cost": available_cost,
    }
    return dict(validate_contract("evaluation_run", run))


def recompute_allocation_metrics(
    *,
    review_queue: Sequence[str],
    ranker_cases: Sequence[Mapping[str, Any]],
    scorer_cases: Sequence[Mapping[str, Any]],
    review_budget: int,
) -> dict[str, Any]:
    """Recompute aggregate and Defect Family metrics from scorer authority."""
    ranker_by_id = {str(case["case_id"]): case for case in ranker_cases}
    scorer_by_id = {str(case["case_id"]): case for case in scorer_cases}
    current_verdicts = {
        case_id: str(case["current_verdict"])
        for case_id, case in ranker_by_id.items()
    }
    reference_verdicts = {
        case_id: str(case["reference_verdict"])
        for case_id, case in scorer_by_id.items()
    }
    score = score_review_queue(
        review_queue=review_queue,
        current_verdicts=current_verdicts,
        reference_verdicts=reference_verdicts,
        review_budget=review_budget,
    )
    family_results: dict[str, dict[str, int | float | None]] = {}
    for family in sorted({str(case["defect_family"]) for case in ranker_cases}):
        family_ids = {
            case_id
            for case_id, case in ranker_by_id.items()
            if str(case["defect_family"]) == family
        }
        label_error_ids = {
            case_id
            for case_id in family_ids
            if current_verdicts[case_id] != reference_verdicts[case_id]
        }
        selected = label_error_ids.intersection(review_queue)
        family_results[family] = {
            "label_error_count": len(label_error_ids),
            "selected_label_error_count": len(selected),
            "recall_at_k": len(selected) / len(label_error_ids) if label_error_ids else None,
        }
    return {
        "recall_at_k": score.recall_at_k,
        "precision_at_k": score.precision_at_k,
        "false_negative_ids": list(score.false_negative_ids),
        "oracle_regret": score.oracle_regret,
        "defect_families": family_results,
    }


def preserve_evaluation_results(
    *,
    development: Mapping[str, Any],
    allocation_holdout_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Preserve the accepted Development and repeated Allocation Holdout results."""
    if development.get("split") != "DEV":
        raise EvaluationRunError("Development result must bind the DEV split")
    if len(allocation_holdout_runs) != 3:
        raise EvaluationRunError("Evaluation evidence requires exactly three Allocation Holdout runs")
    for result in allocation_holdout_runs:
        if result.get("split") != "AH":
            raise EvaluationRunError("Allocation Holdout result must bind the AH split")
        if result.get("edgequeue", {}).get("recall_at_k") != 0.8:
            raise EvaluationRunError("Each valid EdgeQueue Allocation Holdout run must preserve Recall at 8 of 0.80")
        if result.get("simple_baseline", {}).get("recall_at_k") != 0.0:
            raise EvaluationRunError("The strongest defined simple baseline must preserve Recall at 8 of 0.00")
        if result.get("seeded_random", {}).get("p95_recall_at_k") != 0.4:
            raise EvaluationRunError("Seeded random must preserve p95 Recall at 8 of 0.40")
    return {
        "development": dict(development),
        "allocation_holdout_runs": [dict(result) for result in allocation_holdout_runs],
    }


def recompute_saved_evaluation_result(
    *,
    saved_result: Mapping[str, Any],
    ranker_cases: Sequence[Mapping[str, Any]],
    scorer_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Recompute and verify every fixed allocator result from frozen inputs."""
    fixed = saved_result.get("fixed")
    if not isinstance(fixed, Mapping):
        raise EvaluationRunError("Saved evaluation result must contain fixed allocator outputs")
    review_budget = int(saved_result["review_budget"])
    recomputed: dict[str, Any] = {}
    for name, result in fixed.items():
        if not isinstance(result, Mapping):
            raise EvaluationRunError(f"Allocator result {name} is malformed")
        metrics = recompute_allocation_metrics(
            review_queue=result["review_queue"],
            ranker_cases=ranker_cases,
            scorer_cases=scorer_cases,
            review_budget=review_budget,
        )
        declared = result.get("metrics")
        if not isinstance(declared, Mapping) or any(declared.get(key) != metrics[key] for key in ("recall_at_k", "precision_at_k", "false_negative_ids", "oracle_regret")):
            raise EvaluationRunError(f"Allocator result {name} does not match scorer recomputation")
        recomputed[str(name)] = metrics
    return recomputed
