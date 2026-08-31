from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from edgequeue.contracts import canonical_json, content_digest
from edgequeue.proof_bundle import build_proof_bundle, file_digest
from edgequeue.verification import verify_proof_bundle


FIXTURE = Path(__file__).parent / "fixtures" / "ticket-17" / "bundle-input.json"


def _artifacts() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _bundle(tmp_path: Path, artifacts: dict[str, object] | None = None) -> Path:
    bundle = tmp_path / "bundle"
    build_proof_bundle(bundle, _artifacts() if artifacts is None else artifacts)
    return bundle


def _repair_manifest(bundle: Path, changed_path: str) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = json.loads((bundle / changed_path).read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == changed_path:
            entry["digest"] = file_digest(changed_path, changed)
    projection = {**manifest, "files": [entry for entry in manifest["files"] if entry["path"] != "manifest.json"]}
    for entry in manifest["files"]:
        if entry["path"] == "manifest.json":
            entry["digest"] = content_digest(projection)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")


def _failure_codes(bundle: Path) -> set[str]:
    return {failure.code for failure in verify_proof_bundle(bundle).failures}


def test_rejects_missing_unlisted_and_digest_mismatched_files(tmp_path: Path) -> None:
    missing = _bundle(tmp_path / "missing")
    (missing / "metrics.json").unlink()
    assert "manifest_missing_file" in _failure_codes(missing)

    unlisted = _bundle(tmp_path / "unlisted")
    (unlisted / "unexpected.json").write_text("{}", encoding="utf-8")
    assert "manifest_unlisted_file" in _failure_codes(unlisted)

    digest_mismatch = _bundle(tmp_path / "digest")
    (digest_mismatch / "metrics.json").write_text('{"precision_at_k":1.0,"recall_at_k":0.0}', encoding="utf-8")
    assert "file_digest_mismatch" in _failure_codes(digest_mismatch)


@pytest.mark.parametrize(
    ("artifact", "change", "code"),
    [
        ("allocation-receipt.json", lambda value: value.update({"corpus_digest": "b" * 64}), "corpus_digest_mismatch"),
        ("edgequeue-ranking.json", lambda value: value.update({"review_queue": []}), "budget_violation"),
        ("ranker-cases.jsonl", lambda value: value[0].update({"split": "AH"}), "case_not_in_split"),
        ("baseline-rankings.json", lambda value: value.update({"leak": "scorer-only-01"}), "scorer_leakage"),
        ("evaluation-configuration.json", lambda value: value.update({"calibration_pack_version": "v1", "calibration_version_used": "v2"}), "calibration_version_mismatch"),
    ],
)
def test_rejects_authoritative_input_failures(tmp_path: Path, artifact: str, change, code: str) -> None:
    artifacts = _artifacts()
    change(artifacts[artifact])

    assert code in _failure_codes(_bundle(tmp_path, artifacts))


def test_rejects_invalid_evidence_unauthorized_adjudication_and_conflict(tmp_path: Path) -> None:
    artifacts = _artifacts()
    config = artifacts["evaluation-configuration.json"]
    assert isinstance(config, dict)
    config["authorized_reviewer_ids"] = ["human-1"]
    adjudication = {
        "case_id": "EQ-F01-DEV-01",
        "prior_record_digest": "a" * 64,
        "resulting_verdict": "FAIL",
        "reviewer_id": "human-1",
        "evidence_references": [{"case_id": "EQ-F01-DEV-02", "status": "wrong_case"}],
    }
    adjudications = artifacts["adjudications.jsonl"]
    assert isinstance(adjudications, list)
    adjudications.extend([adjudication, {**adjudication, "resulting_verdict": "PASS", "reviewer_id": "human-2"}])

    codes = _failure_codes(_bundle(tmp_path, artifacts))

    assert {"invalid_evidence", "unauthorized_adjudication", "adjudication_conflict"} <= codes


def test_rejects_a_repaired_digest_metric_tamper(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    metrics_path = bundle / "metrics.json"
    metrics_path.write_text('{"precision_at_k":1.0,"recall_at_k":0.0}', encoding="utf-8")
    _repair_manifest(bundle, "metrics.json")

    assert "metric_recomputation_mismatch" in _failure_codes(bundle)


def test_rejects_a_repaired_digest_oracle_regret_tamper(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    metrics_path = bundle / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["oracle_regret"] = 999
    metrics_path.write_text(canonical_json(metrics), encoding="utf-8")
    _repair_manifest(bundle, "metrics.json")

    assert "metric_recomputation_mismatch" in _failure_codes(bundle)


def test_rejects_a_noncanonical_manifest_file(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    assert "file_digest_mismatch" in _failure_codes(bundle)


def test_rejects_mismatched_scorer_cases_without_crashing(tmp_path: Path) -> None:
    artifacts = _artifacts()
    scorer_cases = artifacts["scorer-cases.jsonl"]
    assert isinstance(scorer_cases, list)
    scorer_cases[0]["case_id"] = "EQ-F01-DEV-02"

    assert "case_not_in_split" in _failure_codes(_bundle(tmp_path, artifacts))


def test_rejects_a_bundle_without_any_label_errors_without_crashing(tmp_path: Path) -> None:
    artifacts = _artifacts()
    ranker_cases = artifacts["ranker-cases.jsonl"]
    assert isinstance(ranker_cases, list)
    ranker_cases[0]["current_verdict"] = "FAIL"

    assert "metric_recomputation_mismatch" in _failure_codes(_bundle(tmp_path, artifacts))


def test_rejects_a_public_claim_that_differs_from_recomputation(tmp_path: Path) -> None:
    artifacts = _artifacts()
    claims = artifacts["claims-manifest.json"]
    assert isinstance(claims, dict)
    claims["claims"][0]["value"] = 0.0

    assert "public_claim_mismatch" in _failure_codes(_bundle(tmp_path, artifacts))


def test_verification_is_network_free_and_does_not_change_the_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _bundle(tmp_path)
    before = {path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()}

    def fail_network(*args, **kwargs):
        raise AssertionError("verification must not create network sockets")

    monkeypatch.setattr(socket, "socket", fail_network)
    result = verify_proof_bundle(bundle)
    after = {path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()}

    assert result.valid is True
    assert before == after
