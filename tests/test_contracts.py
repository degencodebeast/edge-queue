import json
import hashlib
from dataclasses import asdict
from pathlib import Path

import pytest

from edgequeue.contracts import (
    CONTRACTS,
    ContractValidationError,
    PROOF_BUNDLE_REQUIRED_PATHS,
    canonical_json,
    content_digest,
    digest_contract,
    validate_proof_bundle,
    validate_adjudication_authority,
    validate_allocation_receipt,
    validate_calibration_authority,
    validate_contract,
    validate_corpus_manifest_authority,
)
from edgequeue.corpus import build_development_cases


def _ranker_case() -> dict[str, object]:
    ranker = asdict(build_development_cases()[0].ranker_case)
    ranker["case_id"] = "EQ-F01-DEV-01"
    for event in ranker["trajectory_events"]:
        event["case_id"] = "EQ-F01-DEV-01"
    ranker.pop("content_digest")
    ranker["content_digest"] = content_digest(ranker)
    return ranker


def _assessment() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "EQ-F01-DEV-01",
        "status": "risk_finding",
        "risk_score": 82,
        "reason_codes": ["missing_check"],
        "rubric_clause_ids": ["R1"],
        "evidence_references": [
            {
                "case_id": "EQ-F01-DEV-01",
                "event_id": "E1",
                "relation": "contradicts_current",
                "claim": "The required check did not run.",
                "status": "verified",
            }
        ],
        "explanation": "The current Verdict may be wrong.",
        "abstention_reason": None,
        "allocator_config_digest": "a" * 64,
        "input_digest": digest_contract("ranker_case", _ranker_case()),
        "output_digest": "c" * 64,
        "attempts": [{"schema_version": "1.0", "attempt": 1, "outcome": "accepted"}],
    }


def test_validates_versioned_case_assessment() -> None:
    assert validate_contract("case_assessment", _assessment()) == _assessment()


def test_validates_standalone_trajectory_event_with_case_binding() -> None:
    payload = {
        "schema_version": "1.0",
        "case_id": "EQ-F01-DEV-01",
        "event_id": "E1",
        "event_type": "tool_result",
        "content": "The command returned zero.",
    }

    assert validate_contract("trajectory_event", payload) == payload


@pytest.mark.parametrize(
    "event_type",
    (
        "task_instruction",
        "reasoning_summary",
        "tool_call",
        "tool_result",
        "checkpoint",
        "approval",
        "final_result",
    ),
)
def test_trajectory_event_accepts_every_normalized_event_kind(event_type: str) -> None:
    payload = {
        "schema_version": "1.0",
        "case_id": "EQ-F01-DEV-01",
        "event_id": "E1",
        "event_type": event_type,
        "content": "Normalized trajectory evidence.",
    }

    assert validate_contract("trajectory_event", payload) == payload


def test_evaluator_manifest_requires_complete_frozen_configurations() -> None:
    payload = {
        "schema_version": "1.0",
        "manifest_id": "evaluators-v1",
        "primary_evaluator_id": "primary-v1",
        "shadow_evaluator_ids": ["shadow-a-v1", "shadow-b-v1"],
        "evaluators": [
            {
                "config_id": "primary-v1",
                "role": "primary",
                "provider": "offline",
                "model": "frozen-primary",
                "prompt_version": "1.0",
                "prompt_digest": "a" * 64,
                "model_parameters": [{"name": "temperature", "value": 0}],
                "tool_permissions": ["read_repository"],
            },
            {
                "config_id": "shadow-a-v1",
                "role": "shadow",
                "provider": "offline",
                "model": "frozen-shadow-a",
                "prompt_version": "1.0",
                "prompt_digest": "b" * 64,
                "model_parameters": [{"name": "temperature", "value": 0}],
                "tool_permissions": ["read_repository"],
            },
            {
                "config_id": "shadow-b-v1",
                "role": "shadow",
                "provider": "offline",
                "model": "frozen-shadow-b",
                "prompt_version": "1.0",
                "prompt_digest": "c" * 64,
                "model_parameters": [{"name": "temperature", "value": 0}],
                "tool_permissions": ["read_repository"],
            },
        ],
        "rubric_version": "1.0",
        "rubric_digest": "d" * 64,
        "output_schema_version": "1.0",
        "output_schema_digest": "e" * 64,
        "retry_policy": {"max_attempts": 2, "retryable_outcomes": ["timeout", "malformed", "schema_failure"]},
        "smoke_result_digest": "f" * 64,
        "created_at": "2026-08-31T00:00:00Z",
    }
    payload["content_digest"] = content_digest(payload)

    assert validate_contract("evaluator_manifest", payload) == payload

    payload["primary_evaluator_id"] = "missing-primary-v1"
    with pytest.raises(ContractValidationError, match="primary evaluator"):
        validate_contract("evaluator_manifest", payload)
    payload["primary_evaluator_id"] = "primary-v1"

    payload["evaluators"] = []
    with pytest.raises(ContractValidationError, match="too few"):
        validate_contract("evaluator_manifest", payload)


def test_authoring_ledger_requires_closed_candidate_attempt_records() -> None:
    payload = {
        "schema_version": "1.0",
        "ledger_id": "ledger-v1",
        "entries": [
            {
                "allocation_row_id": "EQ-F01-DEV-01",
                "candidate_id": "candidate-1",
                "candidate_number": 1,
                "case_blueprint_version": "F01-v1",
                "trajectory_digest": "b" * 64,
                "evaluator_manifest_digest": "c" * 64,
                "status": "accepted",
                "evaluator_attempts": [
                    {
                        "attempt": 1,
                        "evaluator_id": "primary-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                    {
                        "attempt": 2,
                        "evaluator_id": "shadow-a-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                    {
                        "attempt": 3,
                        "evaluator_id": "shadow-b-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                ],
                "reason": "Matches the frozen current Verdict.",
                "reviewer_id": "human-1",
                "recorded_at": "2026-08-31T00:00:00Z",
                "referenced_digests": ["a" * 64],
            }
        ],
    }
    payload["content_digest"] = content_digest(payload)

    assert validate_contract("authoring_ledger", payload) == payload

    entry = payload["entries"][0]
    payload["entries"] = [
        {**entry, "candidate_id": f"candidate-{number}"}
        for number in range(1, 5)
    ]
    with pytest.raises(ContractValidationError, match="at most three"):
        validate_contract("authoring_ledger", payload)
    payload["entries"] = [entry]

    payload["entries"][0]["evaluator_attempts"][-1]["outcome"] = "execution_failure"
    with pytest.raises(ContractValidationError, match="accepted candidate"):
        validate_contract("authoring_ledger", payload)

    payload["entries"] = []
    with pytest.raises(ContractValidationError, match="too few"):
        validate_contract("authoring_ledger", payload)


def test_rejects_unknown_fields_in_nested_authoritative_records() -> None:
    payload = _assessment()
    payload["attempts"] = [{"attempt": 1, "outcome": "accepted", "debug": True}]

    with pytest.raises(ContractValidationError, match="unknown field.*debug"):
        validate_contract("case_assessment", payload)


def test_rejects_missing_schema_version() -> None:
    payload = _assessment()
    del payload["schema_version"]

    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_contract("case_assessment", payload)


def test_canonical_json_is_utf8_sorted_and_line_ending_normalized() -> None:
    payload = {"z": "line1\r\nline2", "a": "café"}

    serialized = canonical_json(payload)

    assert serialized == '{"a":"café","z":"line1\\nline2"}'
    assert serialized.encode("utf-8") == b'{"a":"caf\xc3\xa9","z":"line1\\nline2"}'


def test_declared_timestamps_do_not_change_content_digest() -> None:
    first = {"case_id": "case-a", "text": "line1\r\nline2", "created_at": "one"}
    second = {"created_at": "two", "text": "line1\nline2", "case_id": "case-a"}

    assert content_digest(first, excluded_keys={"created_at"}) == content_digest(
        second, excluded_keys={"created_at"}
    )


def test_independent_digest_vector_matches_sha256_of_canonical_bytes() -> None:
    payload = {"b": 2, "a": "é"}
    expected_bytes = b'{"a":"\xc3\xa9","b":2}'
    expected = "06c264c46ad5ada9493abd3aa2383fb205ae99d7d0bad40b03a43bfec8a1b8de"

    assert canonical_json(payload).encode("utf-8") == expected_bytes
    assert expected == "06c264c46ad5ada9493abd3aa2383fb205ae99d7d0bad40b03a43bfec8a1b8de"
    assert content_digest(payload) == expected


def test_verification_failures_use_frozen_named_codes() -> None:
    payload = {
        "schema_version": "1.0",
        "code": "metric_recomputation_mismatch",
        "artifact": "metrics.json",
        "expected": 0.8,
        "observed": 0.6,
        "message": "Derived metric does not match recomputation.",
    }

    assert validate_contract("verification_failure", payload) == payload

    payload["code"] = "generic_failure"
    with pytest.raises(ContractValidationError, match="unsupported value"):
        validate_contract("verification_failure", payload)


def test_risk_finding_requires_verified_evidence() -> None:
    payload = _assessment()
    payload["evidence_references"] = []

    with pytest.raises(ContractValidationError, match="verified evidence|too few"):
        validate_contract("case_assessment", payload)

    payload["evidence_references"] = [
        {
            "case_id": "case-a",
            "event_id": "E1",
            "relation": "contradicts_current",
            "claim": "unavailable",
            "status": "unavailable",
        }
    ]
    with pytest.raises(ContractValidationError, match="verified evidence"):
        validate_contract("case_assessment", payload)


def test_verification_result_is_always_offline_and_read_only() -> None:
    payload = {
        "schema_version": "1.0",
        "valid": True,
        "bundle_digest": "a" * 64,
        "failures": [],
        "checked_files": [],
        "offline": False,
        "read_only": True,
    }

    with pytest.raises(ContractValidationError, match="must equal True"):
        validate_contract("verification_result", payload)


def test_nested_records_use_the_frozen_schema_version() -> None:
    payload = _assessment()
    payload["evidence_references"] = [
        {
            "case_id": "case-a",
            "event_id": "E1",
            "relation": "contradicts_current",
            "claim": "claim",
            "status": "verified",
        }
    ]
    payload["attempts"] = [{"attempt": 1, "outcome": "accepted", "schema_version": "9.9"}]

    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_contract("case_assessment", payload)


def test_reviewer_manifest_binds_identities_to_roles() -> None:
    payload = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [
            {
                "reviewer_id": "human-1",
                "roles": ["reviewer", "conflict_resolver"],
                "can_adjudicate": True,
                "can_resolve_conflicts": True,
                "can_promote_calibration": False,
            }
        ],
        "content_digest": "a" * 64,
    }
    payload["content_digest"] = content_digest(payload, excluded_keys={"content_digest"})

    assert validate_contract("reviewer_manifest", payload) == payload


def test_canonical_json_rejects_normalized_key_collisions() -> None:
    with pytest.raises(ContractValidationError, match="key collision"):
        canonical_json({"a\r": 1, "a\n": 2})


def test_calibration_records_reject_invalid_optional_digests() -> None:
    candidate = {
        "schema_version": "1.0",
        "candidate_id": "candidate-1",
        "predecessor_digest": "a" * 64,
        "rollback_target": "b" * 64,
        "source_adjudication_digests": ["c" * 64],
        "calibration_case_digests": ["d" * 64],
        "guideline_amendments": [],
        "configuration_digests": ["e" * 64],
        "status": "candidate",
        "decision_digest": "not-a-digest",
        "nominator_id": "human-1",
        "nominator_role": "reviewer",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": "f" * 64,
    }
    with pytest.raises(ContractValidationError, match="invalid format"):
        validate_contract("calibration_candidate", candidate)

    pack = {
        "schema_version": "1.0",
        "pack_id": "pack-1",
        "predecessor_digest": "not-a-digest",
        "rollback_target": None,
        "calibration_case_digests": [],
        "guideline_amendments": [],
        "status": "candidate",
        "content_digest": "f" * 64,
    }
    with pytest.raises(ContractValidationError, match="invalid format"):
        validate_contract("calibration_pack", pack)


def test_resolution_adjudication_references_every_conflict_branch() -> None:
    payload = {
        "schema_version": "1.0",
        "adjudication_id": "resolution-1",
        "case_id": "case-a",
        "conflict_adjudication_digests": ["a" * 64, "b" * 64],
        "action": "correct",
        "resulting_verdict": "FAIL",
        "rationale": "The conflict is resolved by the authorized resolver.",
        "reviewer_id": "human-1",
        "reviewer_role": "conflict_resolver",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": "c" * 64,
        "prior_record_digest": "d" * 64,
    }

    assert validate_contract("resolution_adjudication", payload) == payload


def test_calibration_candidate_records_nominator_authority() -> None:
    payload = {
        "schema_version": "1.0",
        "candidate_id": "candidate-1",
        "predecessor_digest": "a" * 64,
        "rollback_target": "b" * 64,
        "source_adjudication_digests": ["c" * 64],
        "calibration_case_digests": ["d" * 64],
        "guideline_amendments": [],
        "configuration_digests": ["e" * 64],
        "status": "candidate",
        "nominator_id": "human-1",
        "nominator_role": "reviewer",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": "f" * 64,
    }

    assert validate_contract("calibration_candidate", payload) == payload


def test_adjudication_authority_requires_a_manifest_permission() -> None:
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [
            {
                "reviewer_id": "human-1",
                "roles": ["reviewer"],
                "can_adjudicate": True,
                "can_resolve_conflicts": False,
                "can_promote_calibration": False,
            }
        ],
        "content_digest": "b" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    adjudication = {
        "schema_version": "1.0",
        "adjudication_id": "adj-1",
        "case_id": "case-a",
        "action": "preserve",
        "prior_record_digest": "a" * 64,
        "prior_verdict": "PASS",
        "resulting_verdict": "PASS",
        "rationale": "Evidence supports the current Verdict.",
        "reviewer_id": "human-1",
        "reviewer_role": "reviewer",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": manifest["content_digest"],
        "trajectory_schema_version": "1.0",
        "trajectory_digest": "1" * 64,
        "allocation_receipt_schema_version": "1.0",
        "allocation_receipt_digest": "2" * 64,
        "evidence_references": [{"case_id": "case-a", "event_id": "E1", "relation": "supports_current", "claim": "Evidence supports the decision.", "status": "verified"}],
        "corpus_digest": "c" * 64,
        "split_digest": "d" * 64,
        "rubric_version": "1.0",
        "prompt_version": "1.0",
        "feature_version": "1.0",
        "model_config_digest": "e" * 64,
        "evaluation_config_digest": "f" * 64,
        "predecessor_digest": "a" * 64,
    }

    assert validate_adjudication_authority(adjudication, manifest) == adjudication
    adjudication["reviewer_id"] = "unknown"
    with pytest.raises(ContractValidationError, match="not authorized"):
        validate_adjudication_authority(adjudication, manifest)


def test_case_assessment_states_are_exclusive() -> None:
    payload = _assessment()
    payload["status"] = "abstention"
    payload["abstention_reason"] = None

    with pytest.raises(ContractValidationError, match="abstention reason"):
        validate_contract("case_assessment", payload)

    payload = _assessment()
    payload["abstention_reason"] = "not an abstention"
    with pytest.raises(ContractValidationError, match="abstention reason"):
        validate_contract("case_assessment", payload)


def test_allocation_receipt_binds_each_assessment_digest() -> None:
    assessment = _assessment()
    receipt = {
        "schema_version": "1.0",
        "receipt_id": "receipt-1",
        "evaluation_run_id": "run-1",
        "corpus_digest": "a" * 64,
        "split_digest": "b" * 64,
        "allocator_config_digest": "a" * 64,
        "review_budget": 1,
        "assessments": [
            {"case_id": "EQ-F01-DEV-01", "assessment_digest": digest_contract("case_assessment", assessment)}
        ],
        "review_queue": ["EQ-F01-DEV-01"],
        "first_excluded_case_id": None,
        "selection_boundary": None,
    }

    assert validate_allocation_receipt(receipt, [assessment], [_ranker_case()]) == receipt
    receipt["assessments"][0]["assessment_digest"] = "e" * 64
    with pytest.raises(ContractValidationError, match="assessment digest"):
        validate_allocation_receipt(receipt, [assessment], [_ranker_case()])


def test_calibration_authority_requires_calibration_permission() -> None:
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [
            {
                "reviewer_id": "human-1",
                "roles": ["reviewer"],
                "can_adjudicate": True,
                "can_resolve_conflicts": False,
                "can_promote_calibration": False,
            }
        ],
        "content_digest": "a" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    promotion = {
        "schema_version": "1.0",
        "promotion_id": "promotion-1",
        "candidate_digest": "b" * 64,
        "predecessor_digest": "c" * 64,
        "rollback_target": "d" * 64,
        "reviewer_id": "human-1",
        "reviewer_role": "calibration_promoter",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": manifest["content_digest"],
        "decision": "promote",
        "rationale": "The candidate passes all gates.",
    }

    with pytest.raises(ContractValidationError, match="not authorized"):
        validate_calibration_authority(promotion, manifest)


def test_calibration_nominations_require_reviewer_authority() -> None:
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [
            {
                "reviewer_id": "human-1",
                "roles": ["reviewer", "conflict_resolver"],
                "can_adjudicate": True,
                "can_resolve_conflicts": True,
                "can_promote_calibration": False,
            }
        ],
        "content_digest": "a" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    candidate = {
        "schema_version": "1.0",
        "candidate_id": "candidate-1",
        "predecessor_digest": "b" * 64,
        "rollback_target": "c" * 64,
        "source_adjudication_digests": ["d" * 64],
        "calibration_case_digests": ["e" * 64],
        "guideline_amendments": [],
        "configuration_digests": [],
        "status": "candidate",
        "nominator_id": "human-1",
        "nominator_role": "conflict_resolver",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": manifest["content_digest"],
    }

    with pytest.raises(ContractValidationError, match="unsupported|Reviewer"):
        validate_calibration_authority(candidate, manifest)


def test_case_assessment_does_not_convert_execution_failure_to_abstention() -> None:
    payload = _assessment()
    payload["status"] = "abstention"
    payload["abstention_reason"] = "The allocator failed to execute."
    payload["attempts"] = [
        {"schema_version": "1.0", "attempt": 1, "outcome": "execution_failure"}
    ]

    with pytest.raises(ContractValidationError, match="execution failure"):
        validate_contract("case_assessment", payload)


def test_case_assessment_does_not_retry_after_execution_failure() -> None:
    payload = _assessment()
    payload["attempts"] = [
        {"schema_version": "1.0", "attempt": 1, "outcome": "execution_failure"},
        {"schema_version": "1.0", "attempt": 2, "outcome": "accepted"},
    ]

    with pytest.raises(ContractValidationError, match="retryable first failure|execution failure"):
        validate_contract("case_assessment", payload)


def test_allocation_receipt_requires_unique_bounded_queue_and_boundary() -> None:
    assessment = _assessment()
    receipt = {
        "schema_version": "1.0",
        "receipt_id": "receipt-1",
        "evaluation_run_id": "run-1",
        "corpus_digest": "a" * 64,
        "split_digest": "b" * 64,
        "allocator_config_digest": "a" * 64,
        "review_budget": 1,
        "assessments": [
            {"case_id": "EQ-F01-DEV-01", "assessment_digest": digest_contract("case_assessment", assessment)}
        ],
        "review_queue": ["EQ-F01-DEV-01", "EQ-F01-DEV-01"],
        "first_excluded_case_id": None,
        "selection_boundary": None,
    }

    with pytest.raises(ContractValidationError, match="budget|unique"):
        validate_allocation_receipt(receipt, [assessment], [_ranker_case()])


def test_adjudication_preserve_cannot_change_the_verdict() -> None:
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [
            {
                "reviewer_id": "human-1",
                "roles": ["reviewer"],
                "can_adjudicate": True,
                "can_resolve_conflicts": False,
                "can_promote_calibration": False,
            }
        ],
        "content_digest": "a" * 64,
    }
    manifest["content_digest"] = content_digest(manifest, excluded_keys={"content_digest"})
    adjudication = {
        "schema_version": "1.0",
        "adjudication_id": "adj-1",
        "case_id": "case-a",
        "action": "preserve",
        "prior_record_digest": "b" * 64,
        "prior_verdict": "PASS",
        "resulting_verdict": "FAIL",
        "rationale": "Invalid preservation.",
        "reviewer_id": "human-1",
        "reviewer_role": "reviewer",
        "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": manifest["content_digest"],
        "trajectory_schema_version": "1.0",
        "trajectory_digest": "3" * 64,
        "allocation_receipt_schema_version": "1.0",
        "allocation_receipt_digest": "4" * 64,
        "evidence_references": [{"case_id": "case-a", "event_id": "E1", "relation": "supports_current", "claim": "Evidence supports the decision.", "status": "verified"}],
        "corpus_digest": "c" * 64,
        "split_digest": "d" * 64,
        "rubric_version": "1.0",
        "prompt_version": "1.0",
        "feature_version": "1.0",
        "model_config_digest": "e" * 64,
        "evaluation_config_digest": "f" * 64,
        "predecessor_digest": "b" * 64,
    }

    with pytest.raises(ContractValidationError, match="resulting verdict"):
        validate_adjudication_authority(adjudication, manifest)


def test_ranker_schema_closes_case_bound_trajectory_events() -> None:
    schema = json.loads(Path("schemas/corpus/v1/ranker-case.schema.json").read_text())
    event_schema = schema["$defs"]["trajectory_event"]

    assert "case_id" in event_schema["required"]
    assert "case_id" in event_schema["properties"]


def test_corpus_schemas_freeze_case_ids_splits_and_event_types() -> None:
    trajectory = json.loads(Path("schemas/corpus/v1/trajectory-event.schema.json").read_text())
    ranker = json.loads(Path("schemas/corpus/v1/ranker-case.schema.json").read_text())
    split = json.loads(Path("schemas/corpus/v1/split-manifest.schema.json").read_text())

    case_id_pattern = "^EQ-F(?:0[1-9]|10)-(?:DEV|AH|PCH)-[0-9]{2}$"
    assert trajectory["properties"]["case_id"]["pattern"] == case_id_pattern
    assert trajectory["properties"]["event_type"]["enum"] == [
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
    ]
    assert ranker["properties"]["split"]["enum"] == ["DEV", "AH", "PCH"]
    assert ranker["properties"]["case_id"]["pattern"] == case_id_pattern
    assert split["properties"]["split"]["enum"] == ["DEV", "AH", "PCH"]


def test_runtime_corpus_contracts_reject_unfrozen_values() -> None:
    payload = _ranker_case()
    payload["case_id"] = "not-a-case"
    payload["split"] = "OTHER"
    payload["trajectory_events"][0]["event_type"] = "unfrozen_event"

    with pytest.raises(ContractValidationError, match="invalid format|unsupported value"):
        validate_contract("ranker_case", payload)


def test_runtime_corpus_contracts_bind_case_ids_to_the_declared_split() -> None:
    payload = _ranker_case()
    payload["split"] = "AH"

    with pytest.raises(ContractValidationError, match="split"):
        validate_contract("ranker_case", payload)


def test_proof_bundle_manifest_uses_a_non_circular_digest() -> None:
    contents = {path: {"path": path} for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]}
    bundle = {
        "schema_version": "1.0",
        "bundle_id": "bundle-1",
        "evaluation_run_digest": "a" * 64,
        "schema_versions": {"contracts": "1.0"},
        "files": [
            {
                "path": path,
                "digest": (
                    hashlib.sha256(contents[path].encode("utf-8")).hexdigest()
                    if isinstance(contents[path], str)
                    else content_digest(contents[path])
                ),
            }
            for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]
        ],
    }
    bundle["files"].append({"path": "manifest.json", "digest": "0" * 64})
    manifest_projection = {
        **bundle,
        "files": bundle["files"][:-1],
    }
    bundle["files"][-1]["digest"] = content_digest(manifest_projection)
    contents["manifest.json"] = bundle

    assert validate_proof_bundle(bundle, contents) == bundle


def test_proof_bundle_reports_a_declared_missing_file_by_name() -> None:
    contents = {path: {"path": path} for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]}
    bundle = {
        "schema_version": "1.0",
        "bundle_id": "bundle-1",
        "evaluation_run_digest": "a" * 64,
        "schema_versions": {"contracts": "1.0"},
        "files": [
            {"path": path, "digest": content_digest(contents[path])}
            for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]
        ],
    }

    with pytest.raises(ContractValidationError) as error:
        validate_proof_bundle(bundle, contents)
    assert error.value.code == "manifest_missing_file"


def test_proof_bundle_hashes_jsonl_as_normalized_file_bytes() -> None:
    contents = {path: {"path": path} for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]}
    contents["ranker-cases.jsonl"] = '{"case_id":"EQ-F01-DEV-01"}\r\n'
    bundle = {
        "schema_version": "1.0",
        "bundle_id": "bundle-1",
        "evaluation_run_digest": "a" * 64,
        "schema_versions": {"contracts": "1.0"},
        "files": [
            {
                "path": path,
                "digest": hashlib.sha256(
                    (
                        contents[path].replace("\r\n", "\n").replace("\r", "\n")
                        if isinstance(contents[path], str)
                        else canonical_json(contents[path])
                    ).encode("utf-8")
                ).hexdigest()
                if isinstance(contents[path], str)
                else content_digest(contents[path]),
            }
            for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]
        ],
    }
    bundle["files"].append({"path": "manifest.json", "digest": "0" * 64})
    bundle["files"][-1]["digest"] = content_digest(
        {**bundle, "files": bundle["files"][:-1]}
    )
    contents["manifest.json"] = bundle

    assert validate_proof_bundle(bundle, contents) == bundle


def test_proof_bundle_rejects_noncanonical_jsonl_text() -> None:
    contents = {path: {"path": path} for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]}
    contents["ranker-cases.jsonl"] = '{ "case_id": "EQ-F01-DEV-01" }\n'
    bundle = {
        "schema_version": "1.0",
        "bundle_id": "bundle-1",
        "evaluation_run_digest": "a" * 64,
        "schema_versions": {"contracts": "1.0"},
        "files": [
            {
                "path": path,
                "digest": (
                    hashlib.sha256(contents[path].encode("utf-8")).hexdigest()
                    if isinstance(contents[path], str)
                    else content_digest(contents[path])
                ),
            }
            for path in PROOF_BUNDLE_REQUIRED_PATHS[:-1]
        ],
    }
    bundle["files"].append({"path": "manifest.json", "digest": "0" * 64})
    bundle["files"][-1]["digest"] = content_digest(
        {**bundle, "files": bundle["files"][:-1]}
    )
    contents["manifest.json"] = bundle

    with pytest.raises(ContractValidationError, match="canonical"):
        validate_proof_bundle(bundle, contents)


def test_corpus_manifest_requires_both_provenance_bindings() -> None:
    payload = {
        "schema_version": "1.0",
        "corpus_id": "corpus-v1",
        "split_manifests": ["a" * 64],
        "schema_versions": {"corpus": "1.0"},
        "case_blueprint_versions": ["F01-v1"],
        "root_corpus_digest": "b" * 64,
    }

    with pytest.raises(ContractValidationError, match="evaluator_manifest_digest|authoring_ledger_digest"):
        validate_contract("corpus_manifest", payload)


def test_split_manifest_rejects_duplicate_or_unordered_case_membership() -> None:
    payload = {
        "schema_version": "1.0",
        "split": "DEV",
        "case_digests": [
            {"case_id": "EQ-F01-DEV-02", "ranker_digest": "a" * 64, "scorer_digest": "b" * 64},
            {"case_id": "EQ-F01-DEV-01", "ranker_digest": "c" * 64, "scorer_digest": "d" * 64},
        ],
    }
    payload["manifest_digest"] = content_digest(payload)

    with pytest.raises(ContractValidationError, match="stable case identifier order"):
        validate_contract("split_manifest", payload)


def test_corpus_manifest_binds_all_splits_and_the_supplied_ledger_digest() -> None:
    split_manifests = []
    for split, case_id in (("DEV", "EQ-F01-DEV-01"), ("AH", "EQ-F01-AH-01"), ("PCH", "EQ-F01-PCH-01")):
        split_manifest = {
            "schema_version": "1.0",
            "split": split,
            "case_digests": [
                {"case_id": case_id, "ranker_digest": "a" * 64, "scorer_digest": "b" * 64}
            ],
        }
        split_manifest["manifest_digest"] = content_digest(split_manifest)
        split_manifests.append(split_manifest)
    corpus_manifest = {
        "schema_version": "1.0",
        "corpus_id": "corpus-v1",
        "split_manifests": [manifest["manifest_digest"] for manifest in split_manifests],
        "schema_versions": {"corpus": "1.0"},
        "case_blueprint_versions": ["F01-v1"],
        "evaluator_manifest_digest": "c" * 64,
        "authoring_ledger_digest": "d" * 64,
    }
    corpus_manifest["root_corpus_digest"] = content_digest(corpus_manifest)

    with pytest.raises(ContractValidationError, match="Authoring Ledger digest"):
        validate_corpus_manifest_authority(corpus_manifest, split_manifests, "e" * 64)


def test_authoring_ledger_binds_its_content_without_a_root_digest_cycle() -> None:
    payload = {
        "schema_version": "1.0",
        "ledger_id": "ledger-v1",
        "entries": [
            {
                "allocation_row_id": "EQ-F01-DEV-01",
                "candidate_id": "candidate-1",
                "candidate_number": 1,
                "case_blueprint_version": "F01-v1",
                "trajectory_digest": "b" * 64,
                "evaluator_manifest_digest": "c" * 64,
                "status": "accepted",
                "evaluator_attempts": [
                    {
                        "attempt": 1,
                        "evaluator_id": "primary-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                    {
                        "attempt": 2,
                        "evaluator_id": "shadow-a-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                    {
                        "attempt": 3,
                        "evaluator_id": "shadow-b-v1",
                        "outcome": "accepted",
                        "runtime_seconds": 0.5,
                    },
                ],
                "reason": "The candidate matches the frozen current Verdict.",
                "reviewer_id": "reviewer-1",
                "recorded_at": "2026-08-31T00:00:00Z",
                "referenced_digests": ["a" * 64],
            }
        ],
    }
    payload["content_digest"] = content_digest(payload)

    assert validate_contract("authoring_ledger", payload) == payload


def test_validation_does_not_mutate_payload() -> None:
    payload = _assessment()
    before = json.loads(json.dumps(payload))

    validate_contract("case_assessment", payload)

    assert payload == before


@pytest.mark.parametrize(
    "contract_name",
    (
        "ranker_case",
        "scorer_case",
        "evaluation_run",
        "allocation_receipt",
        "adjudication",
        "resolution_adjudication",
        "calibration_case",
        "calibration_candidate",
        "calibration_pack",
        "calibration_promotion",
        "proof_bundle",
        "claim",
        "claims_manifest",
        "verification_failure",
        "verification_result",
    ),
)
def test_contract_names_are_frozen(contract_name: str) -> None:
    assert contract_name in CONTRACTS


def test_versioned_schema_files_are_closed_records() -> None:
    schema_root = Path("schemas")
    schema_files = tuple(schema_root.glob("**/v1/*.schema.json"))

    assert len(schema_files) >= 15
    for schema_file in schema_files:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        assert "schema_version" in schema["required"]


def test_runtime_contracts_match_checked_in_schema_top_level_fields() -> None:
    schema_names = {
        "case_assessment": "schemas/contracts/v1/case-assessment.schema.json",
        "evaluation_run": "schemas/contracts/v1/evaluation-run.schema.json",
        "allocation_receipt": "schemas/contracts/v1/allocation-receipt.schema.json",
        "adjudication": "schemas/contracts/v1/adjudication.schema.json",
        "calibration_candidate": "schemas/contracts/v1/calibration-candidate.schema.json",
        "calibration_pack": "schemas/contracts/v1/calibration-pack.schema.json",
        "calibration_promotion": "schemas/contracts/v1/calibration-promotion.schema.json",
        "proof_bundle": "schemas/contracts/v1/proof-bundle.schema.json",
        "claim": "schemas/contracts/v1/claim.schema.json",
        "claims_manifest": "schemas/contracts/v1/claims-manifest.schema.json",
        "verification_failure": "schemas/contracts/v1/verification-failure.schema.json",
        "verification_result": "schemas/contracts/v1/verification-result.schema.json",
        "reviewer_manifest": "schemas/contracts/v1/reviewer-manifest.schema.json",
        "resolution_adjudication": "schemas/contracts/v1/resolution-adjudication.schema.json",
    }

    for name, schema_path in schema_names.items():
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        assert set(schema["properties"]) == set(CONTRACTS[name].fields)
        assert set(schema["required"]) == set(CONTRACTS[name].required)
