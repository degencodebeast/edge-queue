import json

import pytest

from edgequeue.adjudication import (
    AdjudicationError,
    append_adjudication,
    append_resolution_adjudication,
    canonical_verdict,
    create_adjudication,
    read_adjudication_history,
)
from edgequeue.contracts import content_digest, digest_contract


def _digest(name: str) -> str:
    return content_digest({"ticket": "18", "name": name})


def _manifest() -> dict[str, object]:
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "ticket-18-reviewers",
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
    }
    manifest["content_digest"] = content_digest(manifest)
    return manifest


def _context() -> dict[str, str]:
    return {
        "case_id": "EQ-F01-DEV-01",
        "prior_record_digest": _digest("frozen-initial-evaluation"),
        "prior_verdict": "PASS",
        "trajectory_digest": _digest("trajectory"),
        "allocation_receipt_digest": _digest("receipt"),
        "corpus_digest": _digest("corpus"),
        "split_digest": _digest("split"),
        "rubric_version": "1.0",
        "prompt_version": "1.0",
        "feature_version": "1.0",
        "model_config_digest": _digest("model-config"),
        "evaluation_config_digest": _digest("evaluation-config"),
    }


def _verified_evidence() -> list[dict[str, str]]:
    return [
        {
            "case_id": "EQ-F01-DEV-01",
            "event_id": "E1",
            "relation": "contradicts_current",
            "claim": "The task record contradicts the current Verdict.",
            "status": "verified",
        }
    ]


def test_appends_an_authorized_correction_bound_to_manifest_and_prior(tmp_path) -> None:
    manifest = _manifest()
    adjudication = create_adjudication(
        context=_context(),
        reviewer_manifest=manifest,
        reviewer_id="human-1",
        action="correct",
        resulting_verdict="FAIL",
        rationale="The verified task event contradicts the current Verdict.",
        evidence_references=_verified_evidence(),
        adjudication_id="adj-1",
    )
    history_path = tmp_path / "adjudications.jsonl"

    appended = append_adjudication(history_path, adjudication, manifest)

    assert appended == adjudication
    assert [json.loads(line) for line in history_path.read_text().splitlines()] == [
        adjudication
    ]


def test_rejects_an_unauthorized_reviewer() -> None:
    with pytest.raises(AdjudicationError, match="not authorized"):
        create_adjudication(
            context=_context(), reviewer_manifest=_manifest(), reviewer_id="agent-1",
            action="preserve", resulting_verdict="PASS", rationale="No human authority.",
            evidence_references=_verified_evidence(), adjudication_id="adj-unauthorized",
        )


def test_rejects_a_duplicate_adjudication_identifier(tmp_path) -> None:
    manifest = _manifest()
    adjudication = create_adjudication(
        context=_context(), reviewer_manifest=manifest, reviewer_id="human-1", action="preserve",
        resulting_verdict="PASS", rationale="The reviewer preserves the Verdict.",
        evidence_references=_verified_evidence(), adjudication_id="adj-duplicate",
    )
    history_path = tmp_path / "history.jsonl"
    append_adjudication(history_path, adjudication, manifest)

    with pytest.raises(AdjudicationError, match="duplicate"):
        append_adjudication(history_path, adjudication, manifest)


def test_blocks_competing_branches_until_an_authorized_resolver_records_resolution(tmp_path) -> None:
    manifest = _manifest()
    corrected = create_adjudication(
        context=_context(), reviewer_manifest=manifest, reviewer_id="human-1", action="correct",
        resulting_verdict="FAIL", rationale="Verified evidence supports correction.",
        evidence_references=_verified_evidence(), adjudication_id="adj-correct",
    )
    preserved = create_adjudication(
        context=_context(), reviewer_manifest=manifest, reviewer_id="human-1", action="preserve",
        resulting_verdict="PASS", rationale="A reviewer preserves the prior Verdict.",
        evidence_references=_verified_evidence(), adjudication_id="adj-preserve",
    )
    history_path = tmp_path / "history.jsonl"
    append_adjudication(history_path, corrected, manifest)
    append_adjudication(history_path, preserved, manifest)
    history = read_adjudication_history(history_path)

    assert canonical_verdict(prior_verdict="PASS", prior_record_digest=_context()["prior_record_digest"], case_id="EQ-F01-DEV-01", history=history, reviewer_manifests=[manifest]) is None
    assert read_adjudication_history(history_path.with_name("history-reviewer-manifests.jsonl")) == (manifest,)

    resolution = {
        "schema_version": "1.0", "adjudication_id": "resolution-1", "case_id": "EQ-F01-DEV-01",
        "conflict_adjudication_digests": [digest_contract("adjudication", corrected), digest_contract("adjudication", preserved)],
        "action": "correct", "resulting_verdict": "FAIL", "rationale": "The authorized resolver selects the correction.",
        "reviewer_id": "human-1", "reviewer_role": "conflict_resolver", "reviewer_manifest_version": "1.0",
        "reviewer_manifest_digest": manifest["content_digest"], "prior_record_digest": _context()["prior_record_digest"],
    }
    append_resolution_adjudication(history_path, resolution, manifest, [manifest, manifest])

    assert canonical_verdict(prior_verdict="PASS", prior_record_digest=_context()["prior_record_digest"], case_id="EQ-F01-DEV-01", history=read_adjudication_history(history_path), reviewer_manifests=[manifest]) == "FAIL"


def test_risk_finding_cannot_change_a_canonical_verdict() -> None:
    risk_finding = {"case_id": "EQ-F01-DEV-01", "status": "risk_finding", "risk_score": 100}

    assert canonical_verdict(prior_verdict="PASS", prior_record_digest=_context()["prior_record_digest"], case_id="EQ-F01-DEV-01", history=[risk_finding]) == "PASS"


def test_blocks_duplicate_outcomes_that_compete_on_one_prior_record(tmp_path) -> None:
    manifest = _manifest()
    history_path = tmp_path / "history.jsonl"
    for identifier in ("adj-one", "adj-two"):
        record = create_adjudication(
            context=_context(), reviewer_manifest=manifest, reviewer_id="human-1", action="preserve",
            resulting_verdict="PASS", rationale="The reviewer preserves the Verdict.",
            evidence_references=_verified_evidence(), adjudication_id=identifier,
        )
        append_adjudication(history_path, record, manifest)

    assert canonical_verdict(prior_verdict="PASS", prior_record_digest=_context()["prior_record_digest"], case_id="EQ-F01-DEV-01", history=read_adjudication_history(history_path), reviewer_manifests=[manifest]) is None
