"""Generate narrow public claims from one valid EvaluationRun."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from edgequeue.contracts import content_digest, digest_contract, validate_claims_manifest, validate_contract
from edgequeue.evaluation_run import recompute_allocation_metrics


SCOPED_CLAIM_TEXT = (
    "On this frozen synthetic Allocation Holdout, EdgeQueue recovered "
    "{recall:.2f} Recall at 8. This small synthetic-corpus result does not "
    "establish production performance or Calibration Promotion."
)


def generate_claims_manifest(
    *,
    evaluation_run: Mapping[str, Any],
    ranker_cases: list[Mapping[str, Any]],
    scorer_cases: list[Mapping[str, Any]],
    supporting_artifact: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Recompute and publish the sole accepted scoped allocation claim."""
    validate_contract("evaluation_run", evaluation_run)
    if evaluation_run["disposition"] != "valid":
        raise ValueError("Claims require a valid EvaluationRun")
    ranker_ids = {str(case["case_id"]) for case in ranker_cases}
    scorer_ids = {str(case["case_id"]) for case in scorer_cases}
    if ranker_ids != scorer_ids or ranker_ids != set(evaluation_run["case_ids"]):
        raise ValueError("Claims require scorer inputs bound to the EvaluationRun case identifiers")
    metrics = recompute_allocation_metrics(
        review_queue=evaluation_run["review_queue"],
        ranker_cases=ranker_cases,
        scorer_cases=scorer_cases,
        review_budget=evaluation_run["review_budget"],
    )
    recall = metrics["recall_at_k"]
    evaluation_run_digest = digest_contract("evaluation_run", evaluation_run)
    claim = {
        "schema_version": "1.0",
        "claim_id": "allocation-holdout-recall-at-8",
        "evaluation_run_digest": evaluation_run_digest,
        "supporting_artifact": supporting_artifact,
        "metric": "allocation_holdout_recall_at_8",
        "value": float(recall),
        "text": SCOPED_CLAIM_TEXT.format(recall=float(recall)),
    }
    validate_contract("claim", claim)
    claims = [claim]
    manifest = {
        "schema_version": "1.0",
        "evaluation_run_digest": evaluation_run_digest,
        "claims": [digest_contract("claim", claim)],
        "content_digest": "0" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    return dict(validate_claims_manifest(manifest, claims)), claims
