"""Versioned, fail-closed contracts shared by EdgeQueue slices.

The module owns three cross-cutting rules:

* authoritative records include an explicit schema version;
* unknown fields fail before a record is serialized or hashed;
* canonical JSON uses UTF-8, sorted keys, compact separators, and normalized
  line endings.

The validator intentionally implements the small JSON Schema subset used by
the local contract files. It has no network or third-party dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
NON_AUTHORITATIVE_TIMESTAMP_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "created_at",
        "updated_at",
        "occurred_at",
        "started_at",
        "completed_at",
        "recorded_at",
    }
)


class ContractValidationError(ValueError):
    """A record does not satisfy its named authoritative contract."""

    def __init__(self, message: str, *, code: str = "contract_invalid") -> None:
        super().__init__(message)
        self.code = code


class UnknownContractError(ContractValidationError):
    """The caller requested a contract that is not frozen."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown contract: {name}", code="unknown_contract")


@dataclass(frozen=True)
class ContractSpec:
    """The runtime shape and required fields for one contract."""

    fields: Mapping[str, Any]
    required: frozenset[str]


@dataclass(frozen=True)
class NullableContractSpec:
    """A closed object that can also be explicitly null."""

    spec: ContractSpec


def _object(fields: Mapping[str, Any], *required: str) -> ContractSpec:
    return ContractSpec(fields=fields, required=frozenset(required))


def _nullable(spec: ContractSpec) -> NullableContractSpec:
    return NullableContractSpec(spec)


_DIGEST: dict[str, Any] = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_STRING: dict[str, Any] = {"type": "string"}
_VERSION: dict[str, Any] = {"type": "string", "enum": [SCHEMA_VERSION]}
_CORPUS_CASE_ID: dict[str, Any] = {
    "type": "string",
    "pattern": r"^EQ-F(?:0[1-9]|10)-(?:DEV|AH|PCH)-[0-9]{2}$",
}
_CORPUS_SPLIT: dict[str, Any] = {"type": "string", "enum": ["DEV", "AH", "PCH"]}
_EVENT_TYPE: dict[str, Any] = {
    "type": "string",
    "enum": [
        "task_instruction",
        "reasoning_summary",
        "tool_call",
        "tool_result",
        "checkpoint",
        "approval",
        "final_result",
        "task",
        "artifact",
        "evaluator_note",
    ],
}
_VERDICT: dict[str, Any] = {
    "type": "string",
    "enum": ["PASS", "FAIL", "UNDETERMINED"],
}
VERIFICATION_FAILURE_CODES: Final[tuple[str, ...]] = (
    "manifest_missing_file",
    "manifest_unlisted_file",
    "file_digest_mismatch",
    "corpus_digest_mismatch",
    "budget_violation",
    "case_not_in_split",
    "scorer_leakage",
    "invalid_evidence",
    "unauthorized_adjudication",
    "adjudication_conflict",
    "calibration_version_mismatch",
    "metric_recomputation_mismatch",
    "public_claim_mismatch",
)
PROOF_BUNDLE_REQUIRED_PATHS: Final[tuple[str, ...]] = (
    "evaluation-configuration.json",
    "ranker-cases.jsonl",
    "scorer-cases.jsonl",
    "baseline-rankings.json",
    "edgequeue-ranking.json",
    "allocation-receipt.json",
    "adjudications.jsonl",
    "metrics.json",
    "claims-manifest.json",
    "manifest.json",
)
_CORPUS_SCHEMA_FILES: Final[dict[str, str]] = {
    "case_specification": "case-specification.schema.json",
    "trajectory_event": "trajectory-event.schema.json",
    "frozen_initial_evaluation": "frozen-initial-evaluation.schema.json",
    "shadow_evaluation": "shadow-evaluation.schema.json",
    "ranker_case": "ranker-case.schema.json",
    "scorer_case": "scorer-case.schema.json",
    "evaluator_manifest": "evaluator-manifest.schema.json",
    "authoring_ledger": "authoring-ledger.schema.json",
    "split_manifest": "split-manifest.schema.json",
    "corpus_manifest": "corpus-manifest.schema.json",
}
_VERIFICATION_FAILURE_CODE = {
    "type": "string",
    "enum": list(VERIFICATION_FAILURE_CODES),
}
_VERIFICATION_FAILURE_RECORD = _object(
    {
        "schema_version": _VERSION,
        "code": _VERIFICATION_FAILURE_CODE,
        "artifact": _STRING,
        "expected": {"type": ["string", "number", "boolean", "null"]},
        "observed": {"type": ["string", "number", "boolean", "null"]},
        "message": _STRING,
    },
    "schema_version", "code", "artifact", "expected", "observed", "message",
)
_EVIDENCE_REFERENCE = _object(
    {
        "case_id": _STRING,
        "event_id": _STRING,
        "relation": {
            "type": "string",
            "enum": ["supports_current", "contradicts_current", "insufficient"],
        },
    "claim": _STRING,
        "status": {
            "type": "string",
            "enum": [
                "verified",
                "unavailable",
                "malformed",
                "digest_mismatch",
                "forbidden",
                "wrong_case",
            ],
        },
    },
    "case_id",
    "event_id",
    "relation",
    "claim",
    "status",
)
_ATTEMPT = _object(
    {
        "schema_version": _VERSION,
        "attempt": {"type": "integer", "minimum": 1},
        "outcome": {
            "type": "string",
            "enum": ["accepted", "timeout", "malformed", "schema_failure", "execution_failure"],
        },
        "error": _STRING,
        "runtime_seconds": {"type": "number", "minimum": 0},
    },
    "schema_version",
    "attempt",
    "outcome",
)
_SELECTION_BOUNDARY = _object(
    {
        "excluded_case_id": _STRING,
        "excluded_status": {"type": "string", "enum": ["risk_finding", "abstention"]},
        "excluded_risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "excluded_deterministic_score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "excluded_case_id",
    "excluded_status",
    "excluded_risk_score",
    "excluded_deterministic_score",
)
_RUBRIC_CLAUSE = _object(
    {"schema_version": _VERSION, "clause_id": _STRING, "text": _STRING},
    "schema_version",
    "clause_id",
    "text",
)
_TRAJECTORY_EVENT = _object(
    {
        "schema_version": _VERSION,
        "case_id": _CORPUS_CASE_ID,
        "event_id": _STRING,
        "event_type": _EVENT_TYPE,
        "content": _STRING,
        "occurred_at": _STRING,
    },
    "schema_version",
    "case_id",
    "event_id",
    "event_type",
    "content",
)
_REVIEWER = _object(
    {
        "reviewer_id": _STRING,
        "roles": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["reviewer", "conflict_resolver", "calibration_promoter"],
            },
        },
        "can_adjudicate": {"type": "boolean"},
        "can_resolve_conflicts": {"type": "boolean"},
        "can_promote_calibration": {"type": "boolean"},
    },
    "reviewer_id",
    "roles",
    "can_adjudicate",
    "can_resolve_conflicts",
    "can_promote_calibration",
)
_REVIEWER_ROLE = {
    "type": "string",
    "enum": ["reviewer", "conflict_resolver", "calibration_promoter"],
}
_NOMINATOR_ROLE = {"type": "string", "enum": ["reviewer"]}
_PROMOTION_ROLE = {"type": "string", "enum": ["calibration_promoter"]}
_ASSESSMENT_REFERENCE = _object(
    {"case_id": _STRING, "assessment_digest": _DIGEST},
    "case_id",
    "assessment_digest",
)
_CONTENT_REFERENCE = _object(
    {"name": _STRING, "digest": _DIGEST},
    "name",
    "digest",
)
_EVALUATION_CORE = _object(
    {
        "corpus_manifest": _CONTENT_REFERENCE,
        "split_manifest": _CONTENT_REFERENCE,
        "ranker_case_bundle": _CONTENT_REFERENCE,
        "rubric_snapshot": _CONTENT_REFERENCE,
        "initial_evaluation_snapshot": _CONTENT_REFERENCE,
        "evidence_validation_manifest": _CONTENT_REFERENCE,
        "allocator_prompt": _CONTENT_REFERENCE,
        "allocator_model_config": _CONTENT_REFERENCE,
        "feature_version": _CONTENT_REFERENCE,
        "ranking_policy": _CONTENT_REFERENCE,
        "evaluation_config": _CONTENT_REFERENCE,
        "scorer_reference_manifest": _CONTENT_REFERENCE,
        "canonical_scorer": _CONTENT_REFERENCE,
        "runtime_dependency_manifest": _CONTENT_REFERENCE,
        "risk_findings": _CONTENT_REFERENCE,
        "review_queue": _CONTENT_REFERENCE,
        "allocation_receipt": _CONTENT_REFERENCE,
        "raw_run_outputs": _CONTENT_REFERENCE,
        "optional_absences": {"type": "array", "items": _STRING},
    },
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
    "optional_absences",
)
_OPTIONAL_DIGEST = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
_RESOLUTION_ADJUDICATION = _object(
    {
        "schema_version": _VERSION,
        "adjudication_id": _STRING,
        "case_id": _STRING,
        "conflict_adjudication_digests": {
            "type": "array",
            "items": _DIGEST,
            "minItems": 2,
        },
        "action": {"type": "string", "enum": ["preserve", "correct", "abstain"]},
        "resulting_verdict": _VERDICT,
        "rationale": _STRING,
        "reviewer_id": _STRING,
        "reviewer_role": _REVIEWER_ROLE,
        "reviewer_manifest_version": _STRING,
        "reviewer_manifest_digest": _DIGEST,
        "prior_record_digest": _DIGEST,
    },
    "schema_version",
    "adjudication_id",
    "case_id",
    "conflict_adjudication_digests",
    "action",
    "resulting_verdict",
    "rationale",
    "reviewer_id",
    "reviewer_role",
    "reviewer_manifest_version",
    "reviewer_manifest_digest",
    "prior_record_digest",
)


CONTRACTS: Final[dict[str, ContractSpec]] = {
    "rubric_clause": _object(
        {"schema_version": _STRING, "clause_id": _STRING, "text": _STRING},
        "schema_version",
        "clause_id",
        "text",
    ),
    "trajectory_event": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "event_id": _STRING,
            "event_type": _EVENT_TYPE,
            "content": _STRING,
            "occurred_at": _STRING,
        },
        "schema_version",
        "case_id",
        "event_id",
        "event_type",
        "content",
    ),
    "case_specification": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "task": _STRING,
            "defect_family": _STRING,
            "current_verdict": _VERDICT,
            "reference_verdict": _VERDICT,
            "decisive_event_ids": {"type": "array", "items": _STRING},
            "decisive_evidence": _STRING,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "task",
        "defect_family",
        "current_verdict",
        "reference_verdict",
        "decisive_event_ids",
        "decisive_evidence",
    ),
    "frozen_initial_evaluation": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "verdict": _VERDICT,
            "rationale": _STRING,
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "evaluator_manifest_digest": _DIGEST,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "verdict",
        "rationale",
        "confidence",
        "evaluator_manifest_digest",
    ),
    "shadow_evaluation": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "evaluator_id": _STRING,
            "verdict": _VERDICT,
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "output_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "evaluator_id",
        "verdict",
        "confidence",
        "output_digest",
    ),
    "evaluator_manifest": _object(
        {
            "schema_version": _STRING,
            "manifest_id": _STRING,
            "rubric_version": _STRING,
            "evaluators": {"type": "array", "items": _STRING},
            "retry_policy": _STRING,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "manifest_id",
        "rubric_version",
        "evaluators",
        "retry_policy",
    ),
    "authoring_ledger": _object(
        {
            "schema_version": _STRING,
            "ledger_id": _STRING,
            "entries": {"type": "array", "items": _STRING},
            "content_digest": _DIGEST,
        },
        "schema_version",
        "ledger_id",
        "entries",
    ),
    "ranker_case": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "split": _CORPUS_SPLIT,
            "defect_family": _STRING,
            "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            "signal_profile": {
                "type": "string",
                "enum": ["baseline_visible", "signal_conflicted", "signal_gaming"],
            },
            "current_verdict": _VERDICT,
            "current_rationale": _STRING,
            "primary_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "evaluator_verdicts": {
                "type": "array",
                "items": _VERDICT,
                "minItems": 3,
                "maxItems": 3,
            },
            "deterministic_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "rubric_clauses": {"type": "array", "items": _RUBRIC_CLAUSE},
            "trajectory_events": {"type": "array", "items": _TRAJECTORY_EVENT},
            "provenance_digest": _DIGEST,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "split",
        "defect_family",
        "difficulty",
        "signal_profile",
        "current_verdict",
        "current_rationale",
        "primary_confidence",
        "evaluator_verdicts",
        "deterministic_score",
        "rubric_clauses",
        "trajectory_events",
        "content_digest",
    ),
    "scorer_case": _object(
        {
            "schema_version": _STRING,
            "case_id": _CORPUS_CASE_ID,
            "reference_verdict": _VERDICT,
            "kind": _STRING,
            "decisive_event_ids": {"type": "array", "items": _STRING},
            "scorer_sentinel": _STRING,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "reference_verdict",
        "kind",
        "decisive_event_ids",
        "scorer_sentinel",
        "content_digest",
    ),
    "case_assessment": _object(
        {
            "schema_version": _STRING,
            "case_id": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": ["risk_finding", "abstention"]},
            "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "reason_codes": {"type": "array", "items": _STRING},
            "rubric_clause_ids": {"type": "array", "items": _STRING},
            "evidence_references": {"type": "array", "items": _EVIDENCE_REFERENCE, "minItems": 1},
            "explanation": _STRING,
            "abstention_reason": {"type": ["string", "null"]},
            "allocator_config_digest": _DIGEST,
            "input_digest": _DIGEST,
            "output_digest": _DIGEST,
            "attempts": {"type": "array", "items": _ATTEMPT, "minItems": 1, "maxItems": 2},
        },
        "schema_version",
        "case_id",
        "status",
        "risk_score",
        "reason_codes",
        "rubric_clause_ids",
        "evidence_references",
        "explanation",
        "abstention_reason",
        "allocator_config_digest",
        "input_digest",
        "output_digest",
        "attempts",
    ),
    "split_manifest": _object(
        {
            "schema_version": _STRING,
            "split": _CORPUS_SPLIT,
            "case_digests": {
                "type": "array",
                "items": _object(
                    {"case_id": _CORPUS_CASE_ID, "ranker_digest": _DIGEST, "scorer_digest": _DIGEST},
                    "case_id",
                    "ranker_digest",
                    "scorer_digest",
                ),
            },
            "manifest_digest": _DIGEST,
        },
        "schema_version",
        "split",
        "case_digests",
        "manifest_digest",
    ),
    "corpus_manifest": _object(
        {
            "schema_version": _STRING,
            "corpus_id": _STRING,
            "split_manifests": {"type": "array", "items": _DIGEST},
            "schema_versions": {"type": "object", "additionalProperties": _STRING},
            "case_blueprint_versions": {"type": "array", "items": _STRING},
            "evaluator_manifest_digest": _DIGEST,
            "authoring_ledger_digest": _DIGEST,
            "root_corpus_digest": _DIGEST,
        },
        "schema_version",
        "corpus_id",
        "split_manifests",
        "schema_versions",
        "case_blueprint_versions",
        "evaluator_manifest_digest",
        "authoring_ledger_digest",
        "root_corpus_digest",
    ),
    "evaluation_run": _object(
        {
            "schema_version": _STRING,
            "evaluation_run_id": _STRING,
            "corpus_digest": _DIGEST,
            "split_digest": _DIGEST,
            "evaluation_config_digest": _DIGEST,
            "allocator_config_digest": _DIGEST,
            "scorer_version": _STRING,
            "command_digest": _DIGEST,
            "code_commit": _STRING,
            "git_tree": _STRING,
            "dirty_state": {"type": "boolean"},
            "tested_working_tree_digest": _DIGEST,
            "evaluation_core": _EVALUATION_CORE,
            "exit_code": {"type": "integer"},
            "review_budget": {"type": "integer", "minimum": 1},
            "case_ids": {"type": "array", "items": _STRING},
            "review_queue": {"type": "array", "items": _STRING},
            "allocation_receipt_digest": _DIGEST,
            "disposition": {"type": "string", "enum": ["valid", "invalid"]},
            "raw_artifact_refs": {"type": "array", "items": _STRING},
            "runtime_seconds": {"type": "number", "minimum": 0},
            "request_count": {"type": "integer", "minimum": 0},
            "token_count": {"type": "integer", "minimum": 0},
            "available_cost": {"type": ["number", "null"], "minimum": 0},
            "created_at": _STRING,
        },
        "schema_version",
        "evaluation_run_id",
        "corpus_digest",
        "split_digest",
        "evaluation_config_digest",
        "allocator_config_digest",
        "scorer_version",
        "command_digest",
        "code_commit",
        "git_tree",
        "dirty_state",
        "tested_working_tree_digest",
        "evaluation_core",
        "exit_code",
        "review_budget",
        "case_ids",
        "review_queue",
        "allocation_receipt_digest",
        "disposition",
        "raw_artifact_refs",
    ),
    "allocation_receipt": _object(
        {
            "schema_version": _STRING,
            "receipt_id": _STRING,
            "evaluation_run_id": _STRING,
            "corpus_digest": _DIGEST,
            "split_digest": _DIGEST,
            "allocator_config_digest": _DIGEST,
            "review_budget": {"type": "integer", "minimum": 1},
            "assessments": {"type": "array", "items": _ASSESSMENT_REFERENCE},
            "review_queue": {"type": "array", "items": _STRING},
            "first_excluded_case_id": {"type": ["string", "null"]},
            "selection_boundary": _nullable(_SELECTION_BOUNDARY),
            "created_at": _STRING,
        },
        "schema_version",
        "receipt_id",
        "evaluation_run_id",
        "corpus_digest",
        "split_digest",
        "allocator_config_digest",
        "review_budget",
        "assessments",
        "review_queue",
        "first_excluded_case_id",
        "selection_boundary",
    ),
    "reviewer_manifest": _object(
        {
            "schema_version": _STRING,
            "manifest_id": _STRING,
            "version": _STRING,
            "reviewers": {"type": "array", "items": _REVIEWER},
            "content_digest": _DIGEST,
        },
        "schema_version",
        "manifest_id",
        "version",
        "reviewers",
        "content_digest",
    ),
    "adjudication": _object(
        {
            "schema_version": _STRING,
            "adjudication_id": _STRING,
            "case_id": _STRING,
            "action": {"type": "string", "enum": ["preserve", "correct", "abstain"]},
            "prior_record_digest": _DIGEST,
            "prior_verdict": _VERDICT,
            "resulting_verdict": _VERDICT,
            "rationale": _STRING,
            "reviewer_id": _STRING,
            "reviewer_role": _REVIEWER_ROLE,
            "reviewer_manifest_version": _STRING,
            "reviewer_manifest_digest": _DIGEST,
            "trajectory_schema_version": _VERSION,
            "trajectory_digest": _DIGEST,
            "allocation_receipt_schema_version": _VERSION,
            "allocation_receipt_digest": _DIGEST,
            "evidence_references": {"type": "array", "items": _EVIDENCE_REFERENCE, "minItems": 1},
            "corpus_digest": _DIGEST,
            "split_digest": _DIGEST,
            "rubric_version": _STRING,
            "prompt_version": _STRING,
            "feature_version": _STRING,
            "model_config_digest": _DIGEST,
            "evaluation_config_digest": _DIGEST,
            "predecessor_digest": _DIGEST,
            "created_at": _STRING,
        },
        "schema_version",
        "adjudication_id",
        "case_id",
        "action",
        "prior_record_digest",
        "prior_verdict",
        "resulting_verdict",
        "rationale",
        "reviewer_id",
        "reviewer_role",
        "reviewer_manifest_version",
        "reviewer_manifest_digest",
        "trajectory_schema_version",
        "trajectory_digest",
        "allocation_receipt_schema_version",
        "allocation_receipt_digest",
        "evidence_references",
        "corpus_digest",
        "split_digest",
        "rubric_version",
        "prompt_version",
        "feature_version",
        "model_config_digest",
        "evaluation_config_digest",
        "predecessor_digest",
    ),
    "resolution_adjudication": _RESOLUTION_ADJUDICATION,
    "calibration_case": _object(
        {
            "schema_version": _STRING,
            "case_id": _STRING,
            "source_adjudication_digest": _DIGEST,
            "prior_verdict": _VERDICT,
            "resulting_verdict": _VERDICT,
            "rationale": _STRING,
            "evidence_references": {"type": "array", "items": _EVIDENCE_REFERENCE},
            "rubric_version": _STRING,
            "content_digest": _DIGEST,
        },
        "schema_version",
        "case_id",
        "source_adjudication_digest",
        "prior_verdict",
        "resulting_verdict",
        "rationale",
        "evidence_references",
        "rubric_version",
        "content_digest",
    ),
    "calibration_candidate": _object(
        {
            "schema_version": _STRING,
            "candidate_id": _STRING,
            "predecessor_digest": _DIGEST,
            "rollback_target": _DIGEST,
            "source_adjudication_digests": {"type": "array", "items": _DIGEST},
            "calibration_case_digests": {"type": "array", "items": _DIGEST},
            "guideline_amendments": {"type": "array", "items": _STRING},
            "configuration_digests": {"type": "array", "items": _DIGEST},
            "status": {"type": "string", "enum": ["candidate", "promoted", "rejected"]},
            "decision_digest": _OPTIONAL_DIGEST,
            "nominator_id": _STRING,
            "nominator_role": _NOMINATOR_ROLE,
            "reviewer_manifest_version": _STRING,
            "reviewer_manifest_digest": _DIGEST,
            "created_at": _STRING,
        },
        "schema_version",
        "candidate_id",
        "predecessor_digest",
        "rollback_target",
        "source_adjudication_digests",
        "calibration_case_digests",
        "guideline_amendments",
        "configuration_digests",
        "status",
        "nominator_id",
        "nominator_role",
        "reviewer_manifest_version",
        "reviewer_manifest_digest",
    ),
    "calibration_pack": _object(
        {
            "schema_version": _STRING,
            "pack_id": _STRING,
            "predecessor_digest": _OPTIONAL_DIGEST,
            "rollback_target": _OPTIONAL_DIGEST,
            "calibration_case_digests": {"type": "array", "items": _DIGEST},
            "guideline_amendments": {"type": "array", "items": _STRING},
            "status": {"type": "string", "enum": ["candidate", "promoted", "rejected"]},
            "content_digest": _DIGEST,
        },
        "schema_version",
        "pack_id",
        "predecessor_digest",
        "rollback_target",
        "calibration_case_digests",
        "guideline_amendments",
        "status",
        "content_digest",
    ),
    "calibration_promotion": _object(
        {
            "schema_version": _STRING,
            "promotion_id": _STRING,
            "candidate_digest": _DIGEST,
            "predecessor_digest": _DIGEST,
            "rollback_target": _DIGEST,
            "reviewer_id": _STRING,
            "reviewer_role": _PROMOTION_ROLE,
            "reviewer_manifest_version": _STRING,
            "reviewer_manifest_digest": _DIGEST,
            "decision": {"type": "string", "enum": ["promote", "reject"]},
            "rationale": _STRING,
            "created_at": _STRING,
        },
        "schema_version",
        "promotion_id",
        "candidate_digest",
        "predecessor_digest",
        "rollback_target",
        "reviewer_id",
        "reviewer_role",
        "reviewer_manifest_version",
        "reviewer_manifest_digest",
        "decision",
        "rationale",
    ),
    "proof_bundle": _object(
        {
            "schema_version": _STRING,
            "bundle_id": _STRING,
            "evaluation_run_digest": _DIGEST,
            "schema_versions": {"type": "object", "additionalProperties": _STRING},
            "files": {
                "type": "array",
                "items": _object({"path": _STRING, "digest": _DIGEST}, "path", "digest"),
                "minItems": 1,
            },
            "created_at": _STRING,
        },
        "schema_version",
        "bundle_id",
        "evaluation_run_digest",
        "schema_versions",
        "files",
    ),
    "claim": _object(
        {
            "schema_version": _STRING,
            "claim_id": _STRING,
            "evaluation_run_digest": _DIGEST,
            "supporting_artifact": _STRING,
            "metric": _STRING,
            "value": {"type": ["number", "string", "boolean"]},
            "text": _STRING,
        },
        "schema_version",
        "claim_id",
        "evaluation_run_digest",
        "supporting_artifact",
        "metric",
        "value",
        "text",
    ),
    "claims_manifest": _object(
        {
            "schema_version": _STRING,
            "evaluation_run_digest": _DIGEST,
            "claims": {"type": "array", "items": _DIGEST, "minItems": 1},
            "content_digest": _DIGEST,
        },
        "schema_version",
        "evaluation_run_digest",
        "claims",
        "content_digest",
    ),
    "verification_failure": _object(
        {
            "schema_version": _STRING,
            "code": _VERIFICATION_FAILURE_CODE,
            "artifact": _STRING,
            "expected": {"type": ["string", "number", "boolean", "null"]},
            "observed": {"type": ["string", "number", "boolean", "null"]},
            "message": _STRING,
        },
        "schema_version",
        "code",
        "artifact",
        "expected",
        "observed",
        "message",
    ),
    "verification_result": _object(
        {
            "schema_version": _STRING,
            "valid": {"type": "boolean"},
            "bundle_digest": _DIGEST,
            "failures": {"type": "array", "items": _VERIFICATION_FAILURE_RECORD},
            "checked_files": {"type": "array", "items": _STRING},
            "offline": {"type": "boolean", "const": True},
            "read_only": {"type": "boolean", "const": True},
        },
        "schema_version",
        "valid",
        "bundle_digest",
        "failures",
        "checked_files",
        "offline",
        "read_only",
    ),
}


_CONTRACT_ALIASES: Final[dict[str, str]] = {
    "case-assessment": "case_assessment",
    "ranker-case": "ranker_case",
    "scorer-case": "scorer_case",
    "trajectory-event": "trajectory_event",
    "rubric-clause": "rubric_clause",
    "case-specification": "case_specification",
    "frozen-initial-evaluation": "frozen_initial_evaluation",
    "shadow-evaluation": "shadow_evaluation",
    "evaluator-manifest": "evaluator_manifest",
    "authoring-ledger": "authoring_ledger",
    "split-manifest": "split_manifest",
    "corpus-manifest": "corpus_manifest",
    "evaluation-run": "evaluation_run",
    "allocation-receipt": "allocation_receipt",
    "calibration-case": "calibration_case",
    "calibration-candidate": "calibration_candidate",
    "calibration-pack": "calibration_pack",
    "calibration-promotion": "calibration_promotion",
    "proof-bundle": "proof_bundle",
    "proof-bundle-manifest": "proof_bundle",
    "proof_bundle_manifest": "proof_bundle",
    "claims-manifest": "claims_manifest",
    "verification-failure": "verification_failure",
    "verification-result": "verification_result",
    "resolution-adjudication": "resolution_adjudication",
}
_SELF_DIGEST_FIELDS: Final[dict[str, str]] = {
    "ranker_case": "content_digest",
    "scorer_case": "content_digest",
    "case_specification": "content_digest",
    "frozen_initial_evaluation": "content_digest",
    "evaluator_manifest": "content_digest",
    "authoring_ledger": "content_digest",
    "split_manifest": "manifest_digest",
    "corpus_manifest": "root_corpus_digest",
    "reviewer_manifest": "content_digest",
    "calibration_case": "content_digest",
    "calibration_pack": "content_digest",
    "claims_manifest": "content_digest",
}


def _canonicalize(value: Any, *, excluded_keys: Set[str]) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            if key in excluded_keys:
                continue
            if not isinstance(key, str):
                raise ContractValidationError(
                    "Canonical JSON object keys must be strings",
                    code="canonical_json_invalid",
                )
            normalized_key = (
                key.replace("\r\n", "\n").replace("\r", "\n")
            )
            if normalized_key in normalized:
                raise ContractValidationError(
                    f"Canonical JSON key collision after line-ending normalization: {key!r}",
                    code="canonical_json_invalid",
                )
            normalized[normalized_key] = _canonicalize(
                item, excluded_keys=excluded_keys
            )
        return normalized
    if isinstance(value, list):
        return [_canonicalize(item, excluded_keys=excluded_keys) for item in value]
    if isinstance(value, tuple):
        return [_canonicalize(item, excluded_keys=excluded_keys) for item in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    return value


def canonical_json(payload: Any, *, excluded_keys: Set[str] = frozenset()) -> str:
    """Return the canonical compact JSON representation of ``payload``."""
    normalized = _canonicalize(payload, excluded_keys=excluded_keys)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ContractValidationError(
            f"Value cannot be represented as canonical JSON: {error}",
            code="canonical_json_invalid",
        ) from error


def canonical_json_bytes(payload: Any, *, excluded_keys: Set[str] = frozenset()) -> bytes:
    """Return canonical JSON encoded as UTF-8 bytes."""
    return canonical_json(payload, excluded_keys=excluded_keys).encode("utf-8")


def content_digest(
    payload: Any,
    *,
    excluded_keys: Set[str] = NON_AUTHORITATIVE_TIMESTAMP_FIELDS,
) -> str:
    """Return the SHA-256 digest of canonical UTF-8 JSON content."""
    return hashlib.sha256(
        canonical_json_bytes(payload, excluded_keys=excluded_keys)
    ).hexdigest()


def _canonical_file_bytes(path: str, contents: Any) -> bytes:
    """Return canonical bytes for parsed JSON or canonical JSON/JSONL text."""
    if isinstance(contents, bytes):
        try:
            contents = contents.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContractValidationError(
                f"Proof Bundle file is not valid UTF-8: {path}",
                code="file_digest_mismatch",
            ) from error
    if isinstance(contents, str):
        normalized = contents.replace("\r\n", "\n").replace("\r", "\n")
        try:
            if path.endswith(".jsonl"):
                has_final_newline = normalized.endswith("\n")
                lines = normalized.split("\n")
                if has_final_newline:
                    lines.pop()
                if not lines or any(not line for line in lines):
                    raise ValueError("JSONL contains an empty record")
                canonical = "\n".join(
                    canonical_json(json.loads(line)) for line in lines
                )
                if has_final_newline:
                    canonical += "\n"
            elif path.endswith(".json"):
                canonical = canonical_json(json.loads(normalized))
            else:
                canonical = normalized
        except (json.JSONDecodeError, ContractValidationError, ValueError) as error:
            raise ContractValidationError(
                f"Proof Bundle file is not canonical JSON text: {path}",
                code="canonical_json_invalid",
            ) from error
        if canonical != normalized:
            raise ContractValidationError(
                f"Proof Bundle file is not canonical JSON text: {path}",
                code="canonical_json_invalid",
            )
        return canonical.encode("utf-8")
    return canonical_json_bytes(contents)


def _file_digest(path: str, contents: Any) -> str:
    """Hash canonical JSON or JSONL file bytes."""
    return hashlib.sha256(_canonical_file_bytes(path, contents)).hexdigest()


@lru_cache(maxsize=None)
def _load_corpus_schema(name: str) -> Mapping[str, Any]:
    filename = _CORPUS_SCHEMA_FILES[name]
    try:
        schema_resource = files("edgequeue").joinpath(
            "schemas", "corpus", "v1", filename
        )
        return json.loads(schema_resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "corpus"
            / "v1"
            / filename
        )
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fallback_error:
            raise ContractValidationError(
                f"Corpus schema cannot be loaded: {filename}",
                code="schema_unavailable",
            ) from fallback_error


# Keep the public contract registry aligned with the checked-in corpus schema.
# Runtime corpus validation uses the complete loaded schema below.
for _corpus_name in _CORPUS_SCHEMA_FILES:
    _corpus_schema = _load_corpus_schema(_corpus_name)
    CONTRACTS[_corpus_name] = ContractSpec(
        fields=_corpus_schema["properties"],
        required=frozenset(_corpus_schema["required"]),
    )


def _resolve_schema_ref(root: Mapping[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ContractValidationError(
            f"Unsupported schema reference: {reference}",
            code="schema_invalid",
        )
    value: Any = root
    for component in reference[2:].split("/"):
        value = value[component.replace("~1", "/").replace("~0", "~")]
    return value


def _validate_json_schema(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
    root: Mapping[str, Any],
) -> None:
    if "$ref" in schema:
        _validate_json_schema(value, _resolve_schema_ref(root, schema["$ref"]), path, root)
        return
    if "type" in schema:
        types = schema["type"]
        allowed_types = types if isinstance(types, list) else [types]
        if not any(_is_type(value, type_name) for type_name in allowed_types):
            raise ContractValidationError(f"{path} has an invalid type", code="schema_invalid")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"{path} has an unsupported value: {value!r}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"{path} must equal {schema['const']!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ContractValidationError(f"{path} is shorter than its minimum length")
        if "pattern" in schema:
            import re

            if re.fullmatch(schema["pattern"], value) is None:
                raise ContractValidationError(f"{path} has an invalid format")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractValidationError(f"{path} is below its minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"{path} is above its maximum")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ContractValidationError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractValidationError(f"{path} has too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_json_schema(item, schema["items"], f"{path}[{index}]", root)
    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        missing = sorted(required - set(value))
        if missing:
            raise ContractValidationError(
                f"{path} is missing required field(s): {', '.join(missing)}",
                code="missing_field",
            )
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ContractValidationError(
                    f"{path} contains unknown field(s): {', '.join(unknown)}",
                    code="unknown_field",
                )
        additional = schema.get("additionalProperties")
        for key, item in value.items():
            if key in properties:
                _validate_json_schema(item, properties[key], f"{path}.{key}", root)
            elif isinstance(additional, Mapping):
                _validate_json_schema(item, additional, f"{path}.{key}", root)


def _validate(value: Any, schema: Any, path: str) -> None:
    if isinstance(schema, NullableContractSpec):
        if value is not None:
            _validate(value, schema.spec, path)
        return
    if isinstance(schema, ContractSpec):
        if not isinstance(value, Mapping):
            raise ContractValidationError(f"{path} must be an object")
        unknown = sorted(set(value) - set(schema.fields))
        if unknown:
            raise ContractValidationError(
                f"{path} contains unknown field(s): {', '.join(unknown)}",
                code="unknown_field",
            )
        missing = sorted(schema.required - set(value))
        if missing:
            raise ContractValidationError(
                f"{path} is missing required field(s): {', '.join(missing)}",
                code="missing_field",
            )
        for key, child_schema in schema.fields.items():
            if key in value:
                _validate(value[key], child_schema, f"{path}.{key}")
        return

    if isinstance(schema, Mapping) and "type" in schema:
        types = schema["type"]
        allowed_types = types if isinstance(types, list) else [types]
        if value is None and "null" in allowed_types:
            return
        if not any(_is_type(value, type_name) for type_name in allowed_types):
            names = ", ".join(allowed_types)
            raise ContractValidationError(f"{path} must be {names}")
        if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
            raise ContractValidationError(f"{path} is shorter than its minimum length")
        if isinstance(value, str) and "pattern" in schema:
            import re

            if re.fullmatch(schema["pattern"], value) is None:
                raise ContractValidationError(f"{path} has an invalid format")
        if "enum" in schema and value not in schema["enum"]:
            raise ContractValidationError(f"{path} has an unsupported value: {value!r}")
        if "const" in schema and value != schema["const"]:
            raise ContractValidationError(f"{path} must equal {schema['const']!r}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                raise ContractValidationError(f"{path} is below its minimum")
            if "maximum" in schema and value > schema["maximum"]:
                raise ContractValidationError(f"{path} is above its maximum")
        if isinstance(value, (list, tuple)):
            if "minItems" in schema and len(value) < schema["minItems"]:
                raise ContractValidationError(f"{path} has too few items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                raise ContractValidationError(f"{path} has too many items")
            for index, item in enumerate(value):
                _validate(item, schema["items"], f"{path}[{index}]")
        if isinstance(value, Mapping) and "additionalProperties" in schema:
            additional = schema["additionalProperties"]
            if additional is False:
                raise ContractValidationError(f"{path} must not contain unknown fields")
            for key, item in value.items():
                _validate(item, additional, f"{path}.{key}")
        return

    raise ContractValidationError(f"No validator exists for {path}")


def _is_type(value: Any, type_name: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, (list, tuple)),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(type_name, False)


def contract_name(name: str) -> str:
    """Return the canonical contract name for a hyphenated or underscored name."""
    normalized = name.strip().lower().replace("/", "_")
    return _CONTRACT_ALIASES.get(normalized, normalized)


def validate_contract(
    name: str,
    payload: Mapping[str, Any],
    *,
    verify_digest: bool = True,
) -> Mapping[str, Any]:
    """Validate and return one authoritative record without mutating it."""
    canonical_name = contract_name(name)
    spec = CONTRACTS.get(canonical_name)
    if spec is None:
        raise UnknownContractError(name)
    if canonical_name in _CORPUS_SCHEMA_FILES:
        schema = _load_corpus_schema(canonical_name)
        _validate_json_schema(payload, schema, canonical_name, schema)
    else:
        _validate(payload, spec, canonical_name)
    if canonical_name == "case_assessment" and payload["status"] == "risk_finding":
        if payload["abstention_reason"] is not None:
            raise ContractValidationError(
                "risk_finding abstention reason must be null",
                code="invalid_assessment_state",
            )
        evidence_references = payload["evidence_references"]
        if not evidence_references or any(
            reference["status"] != "verified"
            or reference["case_id"] != payload["case_id"]
            for reference in evidence_references
        ):
            raise ContractValidationError(
                "case_assessment risk_finding requires verified evidence",
                code="invalid_evidence",
            )
    if canonical_name == "ranker_case" and any(
        event["case_id"] != payload["case_id"] for event in payload["trajectory_events"]
    ):
        raise ContractValidationError(
            "RankerCase trajectory events must use the parent case identifier",
            code="invalid_evidence",
        )
    if canonical_name == "ranker_case" and payload["case_id"].split("-")[2] != payload["split"]:
        raise ContractValidationError(
            "RankerCase case identifier does not match its declared split",
            code="invalid_split",
        )
    if canonical_name == "split_manifest" and any(
        entry["case_id"].split("-")[2] != payload["split"]
        for entry in payload["case_digests"]
    ):
        raise ContractValidationError(
            "Split Manifest case identifier does not match its declared split",
            code="invalid_split",
        )
    if canonical_name == "split_manifest":
        case_ids = [entry["case_id"] for entry in payload["case_digests"]]
        if case_ids != sorted(case_ids) or len(set(case_ids)) != len(case_ids):
            raise ContractValidationError(
                "Split Manifest case membership must use stable case identifier order without duplicates",
                code="invalid_split",
            )
    if canonical_name == "case_assessment" and payload["status"] == "abstention":
        abstention_reason = payload["abstention_reason"]
        if not isinstance(abstention_reason, str) or not abstention_reason.strip():
            raise ContractValidationError(
                "abstention requires a non-empty abstention reason",
                code="invalid_assessment_state",
            )
        if any(
            reference["status"] in {"malformed", "digest_mismatch", "forbidden", "wrong_case"}
            for reference in payload["evidence_references"]
        ):
            raise ContractValidationError(
                "invalid evidence cannot enter an Agent Abstention",
                code="invalid_evidence",
            )
    if canonical_name == "case_assessment":
        attempts = payload["attempts"]
        if any(attempt["outcome"] == "execution_failure" for attempt in attempts) and payload["status"] == "abstention":
            raise ContractValidationError(
                "execution failure cannot become an assessment or abstention",
                code="invalid_attempt",
            )
        if attempts[-1]["outcome"] != "accepted":
            raise ContractValidationError(
                "a Case Assessment requires a final accepted attempt",
                code="invalid_attempt",
            )
        expected_attempts = list(range(1, len(attempts) + 1))
        if [attempt["attempt"] for attempt in attempts] != expected_attempts:
            raise ContractValidationError(
                "attempt records must be numbered consecutively",
                code="invalid_attempt",
            )
        if len(attempts) == 2 and attempts[0]["outcome"] not in {
            "timeout",
            "malformed",
            "schema_failure",
        }:
            raise ContractValidationError(
                "a retry requires a retryable first failure",
                code="invalid_attempt",
            )
    if canonical_name == "evaluator_manifest":
        evaluator_roles = {
            evaluator["config_id"]: evaluator["role"]
            for evaluator in payload["evaluators"]
        }
        if len(evaluator_roles) != len(payload["evaluators"]):
            raise ContractValidationError(
                "Evaluator Manifest configuration identifiers must be unique",
                code="invalid_evaluator_manifest",
            )
        if evaluator_roles.get(payload["primary_evaluator_id"]) != "primary":
            raise ContractValidationError(
                "Evaluator Manifest primary evaluator must bind a primary configuration",
                code="invalid_evaluator_manifest",
            )
        shadow_evaluator_ids = payload["shadow_evaluator_ids"]
        if (
            len(set(shadow_evaluator_ids)) != 2
            or set(shadow_evaluator_ids)
            != {
                config_id
                for config_id, role in evaluator_roles.items()
                if role == "shadow"
            }
        ):
            raise ContractValidationError(
                "Evaluator Manifest shadow evaluators must bind both shadow configurations",
                code="invalid_evaluator_manifest",
            )
    if canonical_name == "authoring_ledger":
        candidates_by_row: dict[str, list[Mapping[str, Any]]] = {}
        for candidate in payload["entries"]:
            row_candidates = candidates_by_row.setdefault(candidate["allocation_row_id"], [])
            row_candidate_ids = {entry["candidate_id"] for entry in row_candidates}
            if candidate["candidate_id"] in row_candidate_ids:
                raise ContractValidationError(
                    "Authoring Ledger candidate identifiers must be unique within an allocation row",
                    code="invalid_attempt",
                )
            row_candidates.append(candidate)
            if len(row_candidates) > 3:
                raise ContractValidationError(
                    "An Authoring Ledger allocation row permits at most three candidates",
                    code="invalid_attempt",
                )
            attempts = candidate["evaluator_attempts"]
            roles_by_evaluator: dict[str, str] = {}
            attempts_by_evaluator: dict[str, list[Mapping[str, Any]]] = {}
            for attempt in attempts:
                evaluator_id = attempt["evaluator_id"]
                prior_role = roles_by_evaluator.setdefault(
                    evaluator_id, attempt["evaluator_role"]
                )
                if prior_role != attempt["evaluator_role"]:
                    raise ContractValidationError(
                        "Authoring Ledger evaluator roles must not change between attempts",
                        code="invalid_attempt",
                    )
                attempts_by_evaluator.setdefault(evaluator_id, []).append(attempt)
            if set(roles_by_evaluator.values()) != {"primary", "shadow"} or list(
                roles_by_evaluator.values()
            ).count("primary") != 1 or list(roles_by_evaluator.values()).count("shadow") != 2:
                raise ContractValidationError(
                    "Authoring Ledger candidates require all three frozen evaluator attempts",
                    code="invalid_attempt",
                )
            if [attempt["attempt"] for attempt in attempts] != list(
                range(1, len(attempts) + 1)
            ):
                raise ContractValidationError(
                    "Authoring Ledger attempt records must be numbered consecutively",
                    code="invalid_attempt",
                )
            for evaluator_attempts in attempts_by_evaluator.values():
                if len(evaluator_attempts) > 2:
                    raise ContractValidationError(
                        "An evaluator permits at most two attempts for one candidate",
                        code="invalid_attempt",
                    )
                if len(evaluator_attempts) == 2 and evaluator_attempts[0]["outcome"] not in {
                    "timeout",
                    "malformed",
                    "schema_failure",
                }:
                    raise ContractValidationError(
                        "A retry requires an identical retryable evaluator failure",
                        code="invalid_attempt",
                    )
            primary_attempts = next(
                evaluator_attempts
                for evaluator_id, evaluator_attempts in attempts_by_evaluator.items()
                if roles_by_evaluator[evaluator_id] == "primary"
            )
            primary_verdict = primary_attempts[-1]["verdict"]
            primary_matches_target = (
                primary_attempts[-1]["outcome"] == "accepted"
                and primary_verdict == candidate["target_verdict"]
            )
            if candidate["status"] == "accepted" and any(
                evaluator_attempts[-1]["outcome"] != "accepted"
                for evaluator_attempts in attempts_by_evaluator.values()
            ):
                raise ContractValidationError(
                    "An accepted candidate requires final accepted evaluator attempts",
                    code="invalid_attempt",
                )
            if candidate["status"] == "accepted" and not primary_matches_target:
                raise ContractValidationError(
                    "An accepted candidate requires a primary Verdict that matches its target Verdict",
                    code="invalid_attempt",
                )
            if candidate["status"] == "rejected" and primary_matches_target:
                raise ContractValidationError(
                    "A matching primary Verdict must accept its first candidate",
                    code="invalid_attempt",
                )
        for row_candidates in candidates_by_row.values():
            candidate_numbers = [candidate["candidate_number"] for candidate in row_candidates]
            if candidate_numbers != list(range(1, len(row_candidates) + 1)):
                raise ContractValidationError(
                    "Authoring Ledger candidate records must be numbered consecutively",
                    code="invalid_attempt",
                )
            accepted_candidates = [
                candidate for candidate in row_candidates if candidate["status"] == "accepted"
            ]
            if not accepted_candidates:
                if len(row_candidates) == 3:
                    raise ContractValidationError(
                        "Corpus Freeze is blocked because all three candidates failed",
                        code="invalid_attempt",
                    )
                raise ContractValidationError(
                    "An Authoring Ledger allocation row requires one accepted candidate",
                    code="invalid_attempt",
                )
            if len(accepted_candidates) != 1:
                raise ContractValidationError(
                    "An Authoring Ledger allocation row permits one accepted candidate",
                    code="invalid_attempt",
                )
            first_matching = next(
                candidate
                for candidate in row_candidates
                if candidate["status"] == "accepted"
            )
            if first_matching["candidate_number"] != min(
                candidate["candidate_number"]
                for candidate in row_candidates
                if candidate["status"] == "accepted"
            ):
                raise ContractValidationError(
                    "The first matching candidate must be accepted",
                    code="invalid_attempt",
                )
    self_digest_field = _SELF_DIGEST_FIELDS.get(canonical_name)
    if verify_digest and self_digest_field is not None and self_digest_field in payload:
        expected_digest = content_digest(
            payload,
            excluded_keys=set(NON_AUTHORITATIVE_TIMESTAMP_FIELDS) | {self_digest_field},
        )
        if payload[self_digest_field] != expected_digest:
            raise ContractValidationError(
                f"{canonical_name}.{self_digest_field} does not match canonical content",
                code="digest_mismatch",
            )
    if canonical_name == "adjudication":
        action = payload["action"]
        prior_verdict = payload["prior_verdict"]
        resulting_verdict = payload["resulting_verdict"]
        if action in {"preserve", "abstain"} and resulting_verdict != prior_verdict:
            raise ContractValidationError(
                "resulting verdict must equal prior verdict for preserve or abstain",
                code="invalid_adjudication",
            )
        if action == "correct" and resulting_verdict == prior_verdict:
            raise ContractValidationError(
                "correct must change the resulting verdict",
                code="invalid_adjudication",
            )
    if canonical_name == "verification_result" and payload["valid"] != (not payload["failures"]):
        raise ContractValidationError(
            "Verification Result valid flag must match its failure records",
            code="metric_recomputation_mismatch",
        )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ContractValidationError(
            f"{canonical_name}.schema_version must be {SCHEMA_VERSION!r}",
            code="schema_version_mismatch",
        )
    return payload


def validate_record(name: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Compatibility alias for :func:`validate_contract`."""
    return validate_contract(name, payload)


def validate_corpus_manifest_authority(
    corpus_manifest: Mapping[str, Any],
    split_manifests: Sequence[Mapping[str, Any]],
    authoring_ledger_digest: str,
) -> Mapping[str, Any]:
    """Validate root bindings to the three supplied split manifests and Ledger."""
    validate_contract("corpus_manifest", corpus_manifest)
    if len(split_manifests) != 3:
        raise ContractValidationError(
            "Corpus Manifest requires exactly one DEV, AH, and PCH Split Manifest",
            code="invalid_split",
        )
    expected_splits = ("DEV", "AH", "PCH")
    expected_digests: list[str] = []
    for expected_split, split_manifest in zip(expected_splits, split_manifests, strict=True):
        validate_contract("split_manifest", split_manifest)
        if split_manifest["split"] != expected_split:
            raise ContractValidationError(
                "Corpus Manifest Split Manifests must bind DEV, AH, and PCH in order",
                code="invalid_split",
            )
        expected_digests.append(split_manifest["manifest_digest"])
    if corpus_manifest["split_manifests"] != expected_digests:
        raise ContractValidationError(
            "Corpus Manifest split digests do not match the supplied Split Manifests",
            code="digest_mismatch",
        )
    if corpus_manifest["authoring_ledger_digest"] != authoring_ledger_digest:
        raise ContractValidationError(
            "Corpus Manifest Authoring Ledger digest does not match the supplied Ledger",
            code="digest_mismatch",
        )
    return corpus_manifest


def validate_case_assessment(
    assessment: Mapping[str, Any],
    ranker_case: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate an assessment against the exact RankerCase that supplied its context."""
    validate_contract("case_assessment", assessment)
    validate_contract("ranker_case", ranker_case)
    if any(event["case_id"] != ranker_case["case_id"] for event in ranker_case["trajectory_events"]):
        raise ContractValidationError(
            "RankerCase contains a trajectory event from another case",
            code="invalid_evidence",
        )
    if assessment["input_digest"] != digest_contract("ranker_case", ranker_case):
        raise ContractValidationError(
            "Case Assessment input digest does not match its RankerCase",
            code="digest_mismatch",
        )
    event_ids = {event["event_id"] for event in ranker_case["trajectory_events"]}
    rubric_ids = {clause["clause_id"] for clause in ranker_case["rubric_clauses"]}
    for reference in assessment["evidence_references"]:
        if reference["event_id"] not in event_ids:
            raise ContractValidationError(
                "Case Assessment evidence references an unknown trajectory event",
                code="invalid_evidence",
            )
        event = next(event for event in ranker_case["trajectory_events"] if event["event_id"] == reference["event_id"])
        if event["case_id"] != assessment["case_id"]:
            raise ContractValidationError(
                "Case Assessment evidence references another case",
                code="invalid_evidence",
            )
    if not set(assessment["rubric_clause_ids"]).issubset(rubric_ids):
        raise ContractValidationError(
            "Case Assessment references an unknown rubric clause",
            code="invalid_evidence",
        )
    return assessment


def validate_adjudication_authority(
    adjudication: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate that the frozen manifest grants the requested human action."""
    adjudication_name = (
        "resolution_adjudication"
        if "conflict_adjudication_digests" in adjudication
        else "adjudication"
    )
    validate_contract(adjudication_name, adjudication)
    validate_contract("reviewer_manifest", reviewer_manifest)
    if adjudication_name == "adjudication" and adjudication["action"] == "correct":
        if any(
            reference["status"] != "verified"
            or reference["case_id"] != adjudication["case_id"]
            for reference in adjudication["evidence_references"]
        ):
            raise ContractValidationError(
                "correct Adjudication requires verified same-case evidence",
                code="invalid_evidence",
            )
    expected_manifest_digest = digest_contract("reviewer_manifest", reviewer_manifest)
    if reviewer_manifest["content_digest"] != expected_manifest_digest:
        raise ContractValidationError(
            "Reviewer Manifest content digest does not match its canonical content",
            code="unauthorized_adjudication",
        )
    if adjudication["reviewer_manifest_version"] != reviewer_manifest["version"]:
        raise ContractValidationError(
            "Adjudication Reviewer Manifest version does not match",
            code="unauthorized_adjudication",
        )
    manifest_digest = reviewer_manifest.get("content_digest")
    if adjudication["reviewer_manifest_digest"] != manifest_digest:
        raise ContractValidationError(
            "Adjudication Reviewer Manifest digest does not match",
            code="unauthorized_adjudication",
        )
    reviewer = next(
        (
            entry
            for entry in reviewer_manifest["reviewers"]
            if entry["reviewer_id"] == adjudication["reviewer_id"]
        ),
        None,
    )
    role_permission = {
        "reviewer": "can_adjudicate",
        "conflict_resolver": "can_resolve_conflicts",
        "calibration_promoter": "can_promote_calibration",
    }
    if reviewer is None or adjudication["reviewer_role"] not in reviewer["roles"]:
        raise ContractValidationError(
            f"Reviewer {adjudication['reviewer_id']} is not authorized for this role",
            code="unauthorized_adjudication",
        )
    expected_role = (
        "conflict_resolver"
        if adjudication_name == "resolution_adjudication"
        else "reviewer"
    )
    if adjudication["reviewer_role"] != expected_role:
        raise ContractValidationError(
            f"Reviewer role {adjudication['reviewer_role']} cannot perform this action",
            code="unauthorized_adjudication",
        )
    permission = role_permission[adjudication["reviewer_role"]]
    if not reviewer[permission]:
        raise ContractValidationError(
            f"Reviewer {adjudication['reviewer_id']} is not authorized for this action",
            code="unauthorized_adjudication",
        )
    return adjudication


def validate_resolution_adjudication(
    resolution: Mapping[str, Any],
    conflicting_adjudications: Sequence[Mapping[str, Any]],
    reviewer_manifest: Mapping[str, Any],
    branch_manifests: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate that a Resolution Adjudication preserves a real conflict history."""
    validate_contract("resolution_adjudication", resolution)
    validate_adjudication_authority(resolution, reviewer_manifest)
    if len(conflicting_adjudications) < 2:
        raise ContractValidationError(
            "An Adjudication Conflict requires at least two records",
            code="adjudication_conflict",
        )
    for manifest in branch_manifests:
        validate_contract("reviewer_manifest", manifest)
    manifests_by_digest = {
        manifest["content_digest"]: manifest for manifest in branch_manifests
    }
    for adjudication in conflicting_adjudications:
        validate_contract("adjudication", adjudication)
        branch_manifest = manifests_by_digest.get(adjudication["reviewer_manifest_digest"])
        if branch_manifest is None:
            raise ContractValidationError(
                "Adjudication Conflict branch has no creation-time Reviewer Manifest",
                code="unauthorized_adjudication",
            )
        validate_adjudication_authority(adjudication, branch_manifest)
    branch_digests = [digest_contract("adjudication", adjudication) for adjudication in conflicting_adjudications]
    if len(set(branch_digests)) != len(branch_digests):
        raise ContractValidationError(
            "Adjudication Conflict branches must be distinct",
            code="adjudication_conflict",
        )
    if set(resolution["conflict_adjudication_digests"]) != set(branch_digests):
        raise ContractValidationError(
            "Resolution Adjudication does not reference every conflict branch",
            code="adjudication_conflict",
        )
    case_ids = {adjudication["case_id"] for adjudication in conflicting_adjudications}
    prior_digests = {adjudication["prior_record_digest"] for adjudication in conflicting_adjudications}
    resulting_verdicts = {adjudication["resulting_verdict"] for adjudication in conflicting_adjudications}
    if len(case_ids) != 1 or len(prior_digests) != 1 or len(resulting_verdicts) < 2:
        raise ContractValidationError(
            "Adjudication Conflict branches must share a case and prior record but disagree on result",
            code="adjudication_conflict",
        )
    if resolution["case_id"] not in case_ids:
        raise ContractValidationError(
            "Resolution Adjudication case does not match the conflict",
            code="adjudication_conflict",
        )
    if resolution["prior_record_digest"] != next(iter(prior_digests)):
        raise ContractValidationError(
            "Resolution Adjudication prior record does not match the conflict",
            code="adjudication_conflict",
        )
    if resolution["action"] == "preserve" and resolution["resulting_verdict"] not in resulting_verdicts:
        raise ContractValidationError(
            "preserved Resolution Adjudication must select a conflict result",
            code="adjudication_conflict",
        )
    if resolution["action"] == "abstain" and resolution["resulting_verdict"] != "UNDETERMINED":
        raise ContractValidationError(
            "abstaining Resolution Adjudication must produce UNDETERMINED",
            code="adjudication_conflict",
        )
    return resolution


def validate_proof_bundle(
    bundle: Mapping[str, Any],
    file_contents: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate Proof Bundle coverage and content digests.

    ``manifest.json`` is bound to the digest of the manifest projection that
    omits its own file entry. This gives the manifest a stable digest without
    creating a self-referential hash.
    """
    validate_contract("proof_bundle", bundle)
    declared = {entry["path"]: entry["digest"] for entry in bundle["files"]}
    if len(declared) != len(bundle["files"]):
        raise ContractValidationError("Proof Bundle contains duplicate file paths", code="manifest_unlisted_file")
    if not set(PROOF_BUNDLE_REQUIRED_PATHS).issubset(declared):
        raise ContractValidationError("Proof Bundle omits a required file", code="manifest_missing_file")
    missing_contents = set(declared) - set(file_contents)
    if missing_contents:
        raise ContractValidationError(
            f"Proof Bundle is missing declared file(s): {', '.join(sorted(missing_contents))}",
            code="manifest_missing_file",
        )
    unlisted_contents = set(file_contents) - set(declared)
    if unlisted_contents:
        raise ContractValidationError(
            f"Proof Bundle contains unlisted file(s): {', '.join(sorted(unlisted_contents))}",
            code="manifest_unlisted_file",
        )
    manifest_contents = file_contents["manifest.json"]
    if not isinstance(manifest_contents, Mapping) or dict(manifest_contents) != dict(bundle):
        raise ContractValidationError(
            "Proof Bundle manifest.json does not match the supplied manifest",
            code="file_digest_mismatch",
        )
    manifest_projection = {
        **bundle,
        "files": [entry for entry in bundle["files"] if entry["path"] != "manifest.json"],
    }
    if declared["manifest.json"] != content_digest(manifest_projection):
        raise ContractValidationError(
            "Proof Bundle manifest digest does not match its non-circular projection",
            code="file_digest_mismatch",
        )
    for path, contents in file_contents.items():
        if path == "manifest.json":
            continue
        if declared[path] != _file_digest(path, contents):
            raise ContractValidationError(
                f"Proof Bundle digest does not match {path}",
                code="file_digest_mismatch",
            )
    return bundle


def validate_claims_manifest(
    manifest: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate that a Claims Manifest names the exact Claim records it publishes."""
    validate_contract("claims_manifest", manifest)
    claim_digests = [digest_contract("claim", claim) for claim in claims]
    if manifest["claims"] != claim_digests:
        raise ContractValidationError(
            "Claims Manifest does not reference the supplied Claim records",
            code="public_claim_mismatch",
        )
    if any(claim["evaluation_run_digest"] != manifest["evaluation_run_digest"] for claim in claims):
        raise ContractValidationError(
            "Claim does not reference the Claims Manifest EvaluationRun",
            code="public_claim_mismatch",
        )
    return manifest


def validate_allocation_receipt(
    receipt: Mapping[str, Any],
    assessments: list[Mapping[str, Any]],
    ranker_cases: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate an Allocation Receipt against the exact assessment digests it names."""
    validate_contract("allocation_receipt", receipt)
    expected = [
        {
            "case_id": assessment["case_id"],
            "assessment_digest": digest_contract("case_assessment", assessment),
        }
        for assessment in assessments
    ]
    assessment_ids = [assessment["case_id"] for assessment in assessments]
    if len(set(assessment_ids)) != len(assessment_ids):
        raise ContractValidationError(
            "Allocation Receipt assessments must have unique case identifiers",
            code="invalid_allocation",
        )
    if receipt["assessments"] != expected:
        raise ContractValidationError(
            "Allocation Receipt assessment digest does not match the supplied assessments",
            code="digest_mismatch",
        )
    queue = receipt["review_queue"]
    if len(set(queue)) != len(queue):
        raise ContractValidationError(
            "Allocation Receipt review queue must contain unique case identifiers",
            code="invalid_allocation",
        )
    if len(queue) > receipt["review_budget"]:
        raise ContractValidationError(
            "Allocation Receipt review queue exceeds the review budget",
            code="budget_violation",
        )
    if any(case_id not in assessment_ids for case_id in queue):
        raise ContractValidationError(
            "Allocation Receipt review queue contains an unknown case identifier",
            code="case_not_in_split",
        )
    ranker_by_id: dict[str, Mapping[str, Any]] = {}
    for ranker_case in ranker_cases:
        validate_contract("ranker_case", ranker_case)
    ranker_by_id = {ranker_case["case_id"]: ranker_case for ranker_case in ranker_cases}
    if len(ranker_by_id) != len(ranker_cases) or set(ranker_by_id) != set(assessment_ids):
        raise ContractValidationError(
            "Allocation Receipt ranker cases do not match its assessments",
            code="case_not_in_split",
        )
    for assessment in assessments:
        validate_case_assessment(assessment, ranker_by_id[assessment["case_id"]])
        if assessment["allocator_config_digest"] != receipt["allocator_config_digest"]:
            raise ContractValidationError(
                "Allocation Receipt allocator configuration does not match its assessments",
                code="digest_mismatch",
            )

    ordered_assessments = sorted(
        assessments,
        key=lambda assessment: (
            0 if assessment["status"] == "risk_finding" else 1,
            -assessment["risk_score"],
            -ranker_by_id[assessment["case_id"]]["deterministic_score"],
            assessment["case_id"],
        ),
    )
    ordered_ids = [assessment["case_id"] for assessment in ordered_assessments]
    expected_queue = ordered_ids[: receipt["review_budget"]]
    if len(queue) != min(receipt["review_budget"], len(ordered_ids)) or queue != expected_queue:
        raise ContractValidationError(
            "Allocation Receipt review queue is not the deterministic prefix",
            code="invalid_allocation",
        )
    excluded_case_id = receipt["first_excluded_case_id"]
    if excluded_case_id is None:
        if len(queue) < len(assessment_ids):
            raise ContractValidationError(
                "Allocation Receipt must preserve the first excluded case",
                code="invalid_allocation",
            )
        if receipt["selection_boundary"] is not None:
            raise ContractValidationError(
                "Allocation Receipt boundary must be null when no case is excluded",
                code="invalid_allocation",
            )
    else:
        first_excluded_index = len(queue)
        if first_excluded_index >= len(ordered_ids) or excluded_case_id != ordered_ids[first_excluded_index]:
            raise ContractValidationError(
                "Allocation Receipt first excluded case is not the next deterministic case",
                code="invalid_allocation",
            )
        boundary = receipt["selection_boundary"]
        if boundary is None or boundary["excluded_case_id"] != excluded_case_id:
            raise ContractValidationError(
                "Allocation Receipt selection boundary does not match the first excluded case",
                code="invalid_allocation",
            )
        excluded_assessment = next(assessment for assessment in assessments if assessment["case_id"] == excluded_case_id)
        if (
            boundary["excluded_status"] != excluded_assessment["status"]
            or boundary["excluded_risk_score"] != excluded_assessment["risk_score"]
        ):
            raise ContractValidationError(
                "Allocation Receipt selection boundary does not match the excluded assessment",
                code="invalid_allocation",
            )
        if boundary["excluded_deterministic_score"] != ranker_by_id[excluded_case_id]["deterministic_score"]:
            raise ContractValidationError(
                "Allocation Receipt selection boundary deterministic score does not match",
                code="invalid_allocation",
            )
    return receipt


def validate_calibration_authority(
    record: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate calibration nomination or promotion against a frozen reviewer manifest."""
    record_name = (
        "calibration_promotion" if "promotion_id" in record else "calibration_candidate"
    )
    validate_contract(record_name, record)
    validate_contract("reviewer_manifest", reviewer_manifest)
    expected_manifest_digest = digest_contract("reviewer_manifest", reviewer_manifest)
    if reviewer_manifest["content_digest"] != expected_manifest_digest:
        raise ContractValidationError(
            "Reviewer Manifest content digest does not match its canonical content",
            code="unauthorized_adjudication",
        )
    if record["reviewer_manifest_version"] != reviewer_manifest["version"]:
        raise ContractValidationError(
            "Calibration Reviewer Manifest version does not match",
            code="unauthorized_adjudication",
        )
    if record["reviewer_manifest_digest"] != reviewer_manifest["content_digest"]:
        raise ContractValidationError(
            "Calibration Reviewer Manifest digest does not match",
            code="unauthorized_adjudication",
        )
    reviewer_id = record.get("reviewer_id", record.get("nominator_id"))
    reviewer_role = record.get("reviewer_role", record.get("nominator_role"))
    reviewer = next(
        (entry for entry in reviewer_manifest["reviewers"] if entry["reviewer_id"] == reviewer_id),
        None,
    )
    role_permission = {
        "reviewer": "can_adjudicate",
        "conflict_resolver": "can_resolve_conflicts",
        "calibration_promoter": "can_promote_calibration",
    }
    if record_name == "calibration_candidate":
        if record["status"] != "candidate":
            raise ContractValidationError(
                "Only candidate Calibration Candidates can be nominated",
                code="unauthorized_adjudication",
            )
        authorized = (
            reviewer_role == "reviewer"
            and reviewer is not None
            and reviewer_role in reviewer["roles"]
            and reviewer["can_adjudicate"]
        )
    else:
        authorized = (
            reviewer_role == "calibration_promoter"
            and reviewer is not None
            and reviewer_role in reviewer["roles"]
            and reviewer["can_promote_calibration"]
        )
    if not authorized:
        raise ContractValidationError(
            f"Reviewer {reviewer_id} is not authorized for calibration",
            code="unauthorized_adjudication",
        )
    return record


def digest_contract(
    name: str,
    payload: Mapping[str, Any],
    *,
    excluded_keys: Set[str] = NON_AUTHORITATIVE_TIMESTAMP_FIELDS,
) -> str:
    """Validate a record and hash its declared authoritative content."""
    validate_contract(name, payload)
    self_digest_field = _SELF_DIGEST_FIELDS.get(contract_name(name))
    digest_exclusions = set(excluded_keys)
    if self_digest_field is not None:
        digest_exclusions.add(self_digest_field)
    return content_digest(payload, excluded_keys=digest_exclusions)
