"""Build canonical, manifest-bound Proof Bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from edgequeue.contracts import (
    PROOF_BUNDLE_REQUIRED_PATHS,
    canonical_json,
    content_digest,
    digest_contract,
)


MANIFEST_PATH: Final[str] = "manifest.json"
_RAW_PATHS: Final[tuple[str, ...]] = (
    "evaluation-configuration.json",
    "ranker-cases.jsonl",
    "scorer-cases.jsonl",
    "baseline-rankings.json",
    "edgequeue-ranking.json",
    "allocation-receipt.json",
    "adjudications.jsonl",
)
_GENERATED_PATHS: Final[tuple[str, ...]] = (
    "evaluation-run.json",
    "reviewer-manifest.json",
    "claims.json",
)


class ProofBundleError(ValueError):
    """A Proof Bundle cannot be built from the supplied artifacts."""


def canonical_file_bytes(path: str, value: Any) -> bytes:
    """Return canonical UTF-8 bytes for one supported Proof Bundle artifact."""
    if path.endswith(".jsonl"):
        if not isinstance(value, list):
            raise ProofBundleError(f"{path} must contain a JSONL record list")
        if not value:
            return b""
        return ("\n".join(canonical_json(record) for record in value) + "\n").encode("utf-8")
    return canonical_json(value).encode("utf-8")


def file_digest(path: str, value: Any) -> str:
    """Return the SHA-256 digest for canonical artifact bytes."""
    return hashlib.sha256(canonical_file_bytes(path, value)).hexdigest()


def evaluation_run_digest(artifacts: Mapping[str, Any]) -> str:
    """Bind the authoritative EvaluationRun inputs without derived outputs."""
    return digest_contract("evaluation_run", artifacts["evaluation-run.json"])


def _generated_records(artifacts: dict[str, Any]) -> None:
    """Add the frozen records that bind derived claims to raw inputs."""
    digest = "0" * 64
    receipt = dict(artifacts["allocation-receipt.json"])
    receipt.update(
        {
            "schema_version": "1.0",
            "receipt_id": "receipt-1",
            "evaluation_run_id": "run-1",
            "allocator_config_digest": digest,
            "assessments": [],
            "first_excluded_case_id": None,
            "selection_boundary": None,
        }
    )
    artifacts["allocation-receipt.json"] = receipt
    reviewer_manifest = {
        "schema_version": "1.0",
        "manifest_id": "reviewers-v1",
        "version": "1.0",
        "reviewers": [{"reviewer_id": "human-1", "roles": ["reviewer"], "can_adjudicate": True, "can_resolve_conflicts": False, "can_promote_calibration": False}],
        "content_digest": digest,
    }
    reviewer_manifest["content_digest"] = content_digest(reviewer_manifest, excluded_keys={"content_digest"})
    artifacts["reviewer-manifest.json"] = reviewer_manifest
    core_names = (
        "corpus_manifest", "split_manifest", "ranker_case_bundle", "rubric_snapshot",
        "initial_evaluation_snapshot", "evidence_validation_manifest", "allocator_prompt",
        "allocator_model_config", "feature_version", "ranking_policy", "evaluation_config",
        "scorer_reference_manifest", "canonical_scorer", "runtime_dependency_manifest",
        "risk_findings", "review_queue", "allocation_receipt", "raw_run_outputs",
    )
    config = artifacts["evaluation-configuration.json"]
    run = {
        "schema_version": "1.0", "evaluation_run_id": "run-1",
        "corpus_digest": config["corpus_digest"], "split_digest": config["split_digest"],
        "evaluation_config_digest": content_digest(config), "allocator_config_digest": digest,
        "scorer_version": "1.0", "command_digest": digest, "code_commit": "fixture",
        "git_tree": "fixture", "dirty_state": False, "tested_working_tree_digest": digest,
        "evaluation_core": {name: {"name": name, "digest": digest} for name in core_names} | {"optional_absences": []},
        "exit_code": 0, "review_budget": config["review_budget"],
        "case_ids": [case["case_id"] for case in artifacts["ranker-cases.jsonl"]],
        "review_queue": artifacts["edgequeue-ranking.json"]["review_queue"],
        "allocation_receipt_digest": digest_contract("allocation_receipt", receipt),
        "disposition": "valid", "raw_artifact_refs": list(_RAW_PATHS),
    }
    artifacts["evaluation-run.json"] = run
    run_digest = digest_contract("evaluation_run", run)
    input_claims = artifacts["claims-manifest.json"].get("claims", [])
    claims = [
        {"schema_version": "1.0", "claim_id": f"claim-{index}", "evaluation_run_digest": run_digest,
         "supporting_artifact": claim["supporting_artifact"], "metric": claim["metric"],
         "value": claim["value"], "text": f"{claim['metric']}={claim['value']}"}
        for index, claim in enumerate(input_claims, start=1)
    ]
    artifacts["claims.json"] = claims
    claims_manifest = {"schema_version": "1.0", "evaluation_run_digest": run_digest,
                       "claims": [digest_contract("claim", claim) for claim in claims], "content_digest": digest}
    claims_manifest["content_digest"] = content_digest(claims_manifest, excluded_keys={"content_digest"})
    artifacts["claims-manifest.json"] = claims_manifest


def build_proof_bundle(bundle_dir: Path, artifacts: Mapping[str, Any]) -> Path:
    """Write one complete Proof Bundle and return its manifest path.

    The builder owns bundle creation. Verification never calls this function.
    """
    artifacts = dict(artifacts)
    expected_paths = set(PROOF_BUNDLE_REQUIRED_PATHS) - {MANIFEST_PATH}
    actual_paths = set(artifacts)
    permitted_paths = expected_paths | set(_GENERATED_PATHS)
    if not expected_paths.issubset(actual_paths) or actual_paths - permitted_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - permitted_paths)
        raise ProofBundleError(f"Proof Bundle paths differ. Missing: {missing}; extra: {extra}")
    supplied_generated_paths = actual_paths & set(_GENERATED_PATHS)
    if supplied_generated_paths and supplied_generated_paths != set(_GENERATED_PATHS):
        raise ProofBundleError("Proof Bundle must supply every authority artifact together")
    if not supplied_generated_paths:
        _generated_records(artifacts)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for path, value in artifacts.items():
        (bundle_dir / path).write_bytes(canonical_file_bytes(path, value))

    files = [
        {"path": path, "digest": file_digest(path, artifacts[path])}
        for path in (*PROOF_BUNDLE_REQUIRED_PATHS, *_GENERATED_PATHS)
        if path != MANIFEST_PATH
    ]
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "bundle_id": "edgequeue-proof-bundle",
        "evaluation_run_digest": evaluation_run_digest(artifacts),
        "schema_versions": {"contracts": "1.0", "corpus": "1.0"},
        "files": files,
    }
    manifest["files"].append(
        {
            "path": MANIFEST_PATH,
            "digest": content_digest(manifest),
        }
    )
    manifest_path = bundle_dir / MANIFEST_PATH
    manifest_path.write_bytes(canonical_file_bytes(MANIFEST_PATH, manifest))
    return manifest_path


def load_bundle_file(path: Path) -> Any:
    """Read one canonical JSON or JSONL bundle file without changing it."""
    text = path.read_text(encoding="utf-8")
    if path.name.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line]
    return json.loads(text)
