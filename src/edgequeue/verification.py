"""Offline, read-only Proof Bundle verification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgequeue.contracts import PROOF_BUNDLE_REQUIRED_PATHS, canonical_json, content_digest
from edgequeue.contracts import (
    ContractValidationError,
    digest_contract,
    validate_adjudication_authority,
    validate_claims_manifest,
    validate_contract,
)
from edgequeue.integrity import ScorerLeakageDetected, reject_scorer_leakage
from edgequeue.proof_bundle import (
    _GENERATED_PATHS,
    MANIFEST_PATH,
    canonical_file_bytes,
    evaluation_run_digest,
    file_digest,
    load_bundle_file,
)
from edgequeue.scoring import InvalidReviewQueue, InvalidScorerInput, score_review_queue


@dataclass(frozen=True)
class VerificationFailure:
    """One named fail-closed verification result."""

    code: str
    artifact: str
    expected: str | int | float | bool | None
    observed: str | int | float | bool | None
    message: str

    def as_dict(self) -> dict[str, str | int | float | bool | None]:
        """Return the frozen Verification Failure record shape."""
        return {
            "schema_version": "1.0",
            "code": self.code,
            "artifact": self.artifact,
            "expected": self.expected,
            "observed": self.observed,
            "message": self.message,
        }


@dataclass(frozen=True)
class VerificationResult:
    """The complete result of an offline, read-only bundle check."""

    bundle_digest: str
    failures: tuple[VerificationFailure, ...]
    checked_files: tuple[str, ...]
    offline: bool = True
    read_only: bool = True

    @property
    def valid(self) -> bool:
        """Return true only when no fail-closed check failed."""
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        """Return the frozen Verification Result record shape."""
        return {
            "schema_version": "1.0",
            "valid": self.valid,
            "bundle_digest": self.bundle_digest,
            "failures": [failure.as_dict() for failure in self.failures],
            "checked_files": list(self.checked_files),
            "offline": self.offline,
            "read_only": self.read_only,
        }


def _failure(
    failures: list[VerificationFailure],
    code: str,
    artifact: str,
    expected: str | int | float | bool | None,
    observed: str | int | float | bool | None,
    message: str,
) -> None:
    failures.append(VerificationFailure(code, artifact, expected, observed, message))


def _read_manifest(bundle_dir: Path, failures: list[VerificationFailure]) -> dict[str, Any] | None:
    path = bundle_dir / MANIFEST_PATH
    if not path.is_file():
        _failure(failures, "manifest_missing_file", MANIFEST_PATH, "file", None, "Proof Bundle manifest is missing")
        return None
    try:
        payload = load_bundle_file(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _failure(failures, "file_digest_mismatch", MANIFEST_PATH, "canonical JSON", None, f"Manifest cannot be read: {error}")
        return None
    if not isinstance(payload, dict):
        _failure(failures, "file_digest_mismatch", MANIFEST_PATH, "JSON object", type(payload).__name__, "Manifest must be a JSON object")
        return None
    if path.read_bytes() != canonical_file_bytes(MANIFEST_PATH, payload):
        _failure(failures, "file_digest_mismatch", MANIFEST_PATH, "canonical JSON", None, "Manifest bytes are not canonical")
    return payload


def _listed_files(bundle_dir: Path) -> set[str]:
    return {
        file.relative_to(bundle_dir).as_posix()
        for file in bundle_dir.rglob("*")
        if file.is_file()
    }


def _verify_manifest(bundle_dir: Path, manifest: dict[str, Any], failures: list[VerificationFailure]) -> dict[str, Any]:
    entries = manifest.get("files")
    if not isinstance(entries, list):
        _failure(failures, "manifest_missing_file", MANIFEST_PATH, "file list", None, "Manifest must list bundle files")
        return {}
    declared: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            _failure(failures, "file_digest_mismatch", MANIFEST_PATH, "path and digest", None, "Manifest contains an invalid file entry")
            continue
        path = entry["path"]
        if path in declared:
            _failure(failures, "manifest_unlisted_file", path, "one manifest entry", "duplicate", "Manifest has a duplicate file path")
        declared[path] = entry.get("digest")
    required = set(PROOF_BUNDLE_REQUIRED_PATHS) | set(_GENERATED_PATHS)
    for path in sorted(required - set(declared)):
        _failure(failures, "manifest_missing_file", path, "listed", None, "Required bundle file is not listed")
    for path in sorted(set(declared) - required):
        _failure(failures, "manifest_unlisted_file", path, "permitted path", path, "Manifest lists a non-permitted file")
    actual = _listed_files(bundle_dir)
    for path in sorted(set(declared) - actual):
        _failure(failures, "manifest_missing_file", path, "file", None, "Manifest lists a missing file")
    for path in sorted(actual - set(declared)):
        _failure(failures, "manifest_unlisted_file", path, "listed", path, "Bundle contains an unlisted file")
    projection = {**manifest, "files": [entry for entry in entries if entry.get("path") != MANIFEST_PATH]}
    expected_manifest_digest = __import__("hashlib").sha256(canonical_json(projection).encode("utf-8")).hexdigest()
    if declared.get(MANIFEST_PATH) != expected_manifest_digest:
        _failure(failures, "file_digest_mismatch", MANIFEST_PATH, expected_manifest_digest, declared.get(MANIFEST_PATH), "Manifest digest does not bind its projection")
    return declared


def _load_artifacts(bundle_dir: Path, declared: dict[str, Any], failures: list[VerificationFailure]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for path, digest in declared.items():
        if path == MANIFEST_PATH or not (bundle_dir / path).is_file():
            continue
        try:
            value = load_bundle_file(bundle_dir / path)
            artifacts[path] = value
            if (bundle_dir / path).read_bytes() != canonical_file_bytes(path, value):
                _failure(failures, "file_digest_mismatch", path, "canonical JSON or JSONL", None, "File bytes are not canonical")
                continue
            expected = file_digest(path, value)
            if digest != expected:
                _failure(failures, "file_digest_mismatch", path, expected, digest if isinstance(digest, str) else None, "File digest does not match canonical contents")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            _failure(failures, "file_digest_mismatch", path, "canonical JSON", None, f"File cannot be read: {error}")
    return artifacts


def _verify_authority_and_evidence(artifacts: dict[str, Any], failures: list[VerificationFailure]) -> None:
    adjudications = artifacts.get("adjudications.jsonl", [])
    reviewer_manifest = artifacts.get("reviewer-manifest.json")
    if not isinstance(reviewer_manifest, dict):
        _failure(failures, "unauthorized_adjudication", "reviewer-manifest.json", "Reviewer Manifest", None, "Reviewer Manifest is missing")
        return
    try:
        validate_contract("reviewer_manifest", reviewer_manifest)
    except ContractValidationError as error:
        _failure(failures, "unauthorized_adjudication", "reviewer-manifest.json", "valid frozen Reviewer Manifest", None, str(error))
        return
    seen: dict[tuple[str, str], str] = {}
    for record in adjudications if isinstance(adjudications, list) else []:
        if not isinstance(record, dict):
            _failure(failures, "unauthorized_adjudication", "adjudications.jsonl", "Adjudication record", None, "Adjudication record is invalid")
            continue
        case_id = record.get("case_id")
        evidence_references = record.get("evidence_references")
        if not isinstance(evidence_references, list) or not evidence_references or any(
            not isinstance(reference, dict)
            or reference.get("case_id") != case_id
            or reference.get("status") != "verified"
            for reference in evidence_references
        ):
            _failure(failures, "invalid_evidence", "adjudications.jsonl", "verified same-case evidence", None, "Adjudication evidence is invalid")
        try:
            validate_adjudication_authority(record, reviewer_manifest)
        except ContractValidationError as error:
            code = "invalid_evidence" if error.code == "invalid_evidence" else "unauthorized_adjudication"
            _failure(failures, code, "adjudications.jsonl", "authorized, evidence-linked Adjudication", None, str(error))
        key = (str(case_id), str(record.get("prior_record_digest")))
        prior_result = seen.get(key)
        result = str(record.get("resulting_verdict"))
        if prior_result is not None and prior_result != result:
            _failure(failures, "adjudication_conflict", "adjudications.jsonl", prior_result, result, "Adjudications conflict on one prior record")
        seen[key] = result


def _verify_semantics(manifest: dict[str, Any], artifacts: dict[str, Any], failures: list[VerificationFailure]) -> None:
    config = artifacts.get("evaluation-configuration.json")
    ranker_cases = artifacts.get("ranker-cases.jsonl")
    scorer_cases = artifacts.get("scorer-cases.jsonl")
    ranking = artifacts.get("edgequeue-ranking.json")
    receipt = artifacts.get("allocation-receipt.json")
    if not all(isinstance(value, (dict, list)) for value in (config, ranker_cases, scorer_cases, ranking, receipt)):
        _failure(failures, "file_digest_mismatch", "authoritative inputs", "JSON configuration and case artifacts", None, "An authoritative input has an invalid JSON shape")
        return
    assert isinstance(config, dict) and isinstance(ranker_cases, list) and isinstance(scorer_cases, list)
    assert isinstance(ranking, dict) and isinstance(receipt, dict)
    for name, record in (("manifest.json", manifest), ("evaluation-run.json", artifacts.get("evaluation-run.json")), ("allocation-receipt.json", receipt)):
        if not isinstance(record, dict):
            _failure(failures, "file_digest_mismatch", name, "frozen contract record", None, "Required contract record is missing")
            return
        try:
            validate_contract("proof_bundle" if name == "manifest.json" else "evaluation_run" if name == "evaluation-run.json" else "allocation_receipt", record)
        except ContractValidationError as error:
            _failure(failures, "file_digest_mismatch", name, "valid frozen contract", None, str(error))
            return
    corpus_digest = config.get("corpus_digest")
    for name, record in (("allocation-receipt.json", receipt),):
        if record.get("corpus_digest") != corpus_digest:
            _failure(failures, "corpus_digest_mismatch", name, corpus_digest, record.get("corpus_digest"), "Artifact corpus digest does not match configuration")
        if record.get("split_digest") != config.get("split_digest"):
            _failure(failures, "corpus_digest_mismatch", name, config.get("split_digest"), record.get("split_digest"), "Artifact split digest does not match configuration")
    run = artifacts["evaluation-run.json"]
    assert isinstance(run, dict)
    run_bindings = {
        "corpus_digest": config.get("corpus_digest"),
        "split_digest": config.get("split_digest"),
        "evaluation_config_digest": content_digest(config),
        "review_budget": config.get("review_budget"),
        "review_queue": ranking.get("review_queue"),
        "allocation_receipt_digest": digest_contract("allocation_receipt", receipt),
    }
    for field, expected in run_bindings.items():
        if run.get(field) != expected:
            code = "budget_violation" if field in {"review_budget", "review_queue"} else "corpus_digest_mismatch"
            _failure(failures, code, "evaluation-run.json", expected, run.get(field), f"EvaluationRun {field} does not bind the authoritative input")
    case_id_pattern = re.compile(r"^EQ-F(?:0[1-9]|10)-(?:DEV|AH|PCH)-[0-9]{2}$")
    if any(
        not isinstance(case, dict)
        or not isinstance(case.get("case_id"), str)
        or case_id_pattern.fullmatch(case["case_id"]) is None
        or case.get("split") not in {"DEV", "AH", "PCH"}
        or case.get("current_verdict") not in {"PASS", "FAIL", "UNDETERMINED"}
        for case in ranker_cases
    ) or any(
        not isinstance(case, dict)
        or not isinstance(case.get("case_id"), str)
        or case_id_pattern.fullmatch(case["case_id"]) is None
        or case.get("reference_verdict") not in {"PASS", "FAIL", "UNDETERMINED"}
        or not isinstance(case.get("scorer_sentinel"), str)
        for case in scorer_cases
    ):
        _failure(failures, "case_not_in_split", "case artifacts", "frozen RankerCase and ScorerCase records", None, "Case artifacts do not satisfy the frozen split fields")
        return
    ranker_by_id = {case["case_id"]: case for case in ranker_cases}
    scorer_by_id = {case["case_id"]: case for case in scorer_cases}
    if set(ranker_by_id) != set(scorer_by_id):
        _failure(failures, "case_not_in_split", "scorer-cases.jsonl", sorted(ranker_by_id), sorted(scorer_by_id), "RankerCases and ScorerCases must name the same split")
        return
    if set(ranker_by_id) != set(run.get("case_ids", [])):
        _failure(failures, "case_not_in_split", "evaluation-run.json", sorted(ranker_by_id), run.get("case_ids"), "EvaluationRun case identifiers do not bind the declared split")
    split = config.get("split")
    if any(case.get("split") != split for case in ranker_by_id.values()):
        _failure(failures, "case_not_in_split", "ranker-cases.jsonl", split, None, "RankerCase is outside the declared split")
    queue = ranking.get("review_queue")
    budget = config.get("review_budget")
    if (
        not isinstance(queue, list)
        or not isinstance(budget, int)
        or any(not isinstance(case_id, str) for case_id in queue)
        or len(queue) != budget
        or len(set(queue)) != len(queue)
    ):
        _failure(failures, "budget_violation", "edgequeue-ranking.json", budget if isinstance(budget, int) else None, len(queue) if isinstance(queue, list) else None, "Review Queue must contain exactly the Review Budget")
        return
    if receipt.get("review_queue") != queue or receipt.get("review_budget") != budget:
        _failure(failures, "budget_violation", "allocation-receipt.json", queue, receipt.get("review_queue"), "Allocation Receipt must bind the Review Queue and Review Budget")
    if any(case_id not in ranker_by_id for case_id in queue):
        _failure(failures, "case_not_in_split", "edgequeue-ranking.json", sorted(ranker_by_id), queue, "Review Queue contains a case outside the declared split")
        return
    allocator_artifacts = {name: artifacts[name] for name in ("evaluation-configuration.json", "ranker-cases.jsonl", "baseline-rankings.json", "edgequeue-ranking.json", "allocation-receipt.json") if name in artifacts}
    try:
        reject_scorer_leakage(allocator_artifacts, forbidden_field_names={"reference_verdict", "scorer_sentinel", "decisive_event_ids"}, scorer_sentinels={str(case.get("scorer_sentinel")) for case in scorer_by_id.values()})
    except ScorerLeakageDetected as error:
        _failure(failures, "scorer_leakage", "allocator-visible artifacts", "no scorer-only content", str(error), "Allocator-visible data contains scorer-only content")
    _verify_authority_and_evidence(artifacts, failures)
    expected_calibration = config.get("calibration_pack_version")
    used_calibration = config.get("calibration_version_used", expected_calibration)
    if used_calibration != expected_calibration:
        _failure(failures, "calibration_version_mismatch", "evaluation-configuration.json", expected_calibration, used_calibration, "Calibration version does not match the frozen configuration")
    expected_run_digest = digest_contract("evaluation_run", artifacts["evaluation-run.json"])
    if manifest.get("evaluation_run_digest") != expected_run_digest:
        _failure(failures, "corpus_digest_mismatch", MANIFEST_PATH, expected_run_digest, manifest.get("evaluation_run_digest"), "Manifest EvaluationRun digest does not bind authoritative inputs")
    try:
        recomputed = score_review_queue(
            review_queue=queue,
            current_verdicts={case_id: str(case["current_verdict"]) for case_id, case in ranker_by_id.items()},
            reference_verdicts={case_id: str(case["reference_verdict"]) for case_id, case in scorer_by_id.items()},
            review_budget=budget,
        )
    except (InvalidReviewQueue, InvalidScorerInput, KeyError, ZeroDivisionError) as error:
        _failure(failures, "metric_recomputation_mismatch", "metrics.json", "recomputable metrics", None, f"Metrics cannot be recomputed: {error}")
        return
    expected_metrics = {
        "recall_at_k": recomputed.recall_at_k,
        "precision_at_k": recomputed.precision_at_k,
        "false_negative_ids": list(recomputed.false_negative_ids),
        "oracle_regret": recomputed.oracle_regret,
    }
    metrics = artifacts.get("metrics.json")
    if not isinstance(metrics, dict):
        _failure(failures, "metric_recomputation_mismatch", "metrics.json", "derived metric object", None, "Metrics artifact has an invalid JSON shape")
        return
    if set(metrics) != set(expected_metrics):
        _failure(failures, "metric_recomputation_mismatch", "metrics.json", sorted(expected_metrics), sorted(metrics), "Metrics artifact must contain exactly the recomputed metrics")
    for metric, expected in expected_metrics.items():
        if metrics.get(metric) != expected:
            _failure(failures, "metric_recomputation_mismatch", "metrics.json", expected, metrics.get(metric), f"{metric} does not match recomputation")
    claims_manifest = artifacts.get("claims-manifest.json")
    claims = artifacts.get("claims.json")
    if not isinstance(claims_manifest, dict) or not isinstance(claims, list):
        _failure(failures, "public_claim_mismatch", "claims-manifest.json", "Claims Manifest and Claim records", None, "Claim artifacts are missing")
        return
    try:
        validate_claims_manifest(claims_manifest, claims)
    except ContractValidationError as error:
        _failure(failures, "public_claim_mismatch", "claims-manifest.json", "bound Claims Manifest", None, str(error))
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("supporting_artifact") != "metrics.json" or claim.get("metric") not in expected_metrics or claim.get("value") != expected_metrics[claim.get("metric")]:
            _failure(failures, "public_claim_mismatch", "claims.json", "recomputed metric claim", None, "Public claim does not match the recomputed metric")


def verify_proof_bundle(bundle_dir: Path) -> VerificationResult:
    """Verify one Proof Bundle without network, model access, or bundle writes."""
    failures: list[VerificationFailure] = []
    manifest = _read_manifest(bundle_dir, failures)
    if manifest is None:
        return VerificationResult("", tuple(failures), (), True, True)
    declared = _verify_manifest(bundle_dir, manifest, failures)
    artifacts = _load_artifacts(bundle_dir, declared, failures)
    if not failures:
        _verify_semantics(manifest, artifacts, failures)
    return VerificationResult(str(declared.get(MANIFEST_PATH, "")), tuple(failures), tuple(sorted(artifacts)), True, True)
