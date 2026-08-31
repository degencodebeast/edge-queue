import json
from pathlib import Path

import pytest

from edgequeue.review_packet import render_review_packet


def _ticket_16_review_inputs() -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/ticket-16/fixed-batch-input.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = json.loads(
        (Path(__file__).parents[1] / "docs/evidence/ticket-16/fixed-batch-allocation-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assessments = []
    for definition, ranker_case in zip(
        fixture["assessment_definitions"], fixture["ranker_cases"], strict=True
    ):
        assessments.append(
            {
                "case_id": ranker_case["case_id"],
                "status": definition["status"],
                "risk_score": definition["risk_score"],
                "rubric_clause_ids": definition["rubric_clause_ids"],
                "evidence_references": [
                    {**reference, "case_id": ranker_case["case_id"]}
                    for reference in definition["evidence_references"]
                ],
                "explanation": definition["explanation"],
            }
        )
    return receipt, assessments, fixture["ranker_cases"]


def test_renders_selected_case_with_risk_finding_and_selection_boundary() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()

    packet = render_review_packet(receipt, assessments, ranker_cases)

    assert "<!doctype html>" in packet.lower()
    assert "EQ-F01-DEV-01" in packet
    assert "The task record contradicts the current Verdict." in packet
    assert "Create a migration that adds a non-null account status column." in packet
    assert "R1" in packet
    assert "EQ-F01-DEV-02" in packet
    assert "risk score" in packet.lower()


def test_marks_every_invalid_evidence_status_as_non_proof() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()
    statuses = ("unavailable", "malformed", "digest_mismatch", "forbidden", "wrong_case")
    assessments[0]["evidence_references"] = [
        {"case_id": "EQ-F01-DEV-01", "event_id": f"E{index}", "relation": "insufficient", "claim": status, "status": status}
        for index, status in enumerate(statuses, start=1)
    ]

    packet = render_review_packet(receipt, assessments, ranker_cases)

    assert all(f"non-proof: {status}" in packet for status in statuses)


def test_rejects_verified_evidence_from_another_case() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()
    assessments[0]["evidence_references"][0]["case_id"] = "EQ-F01-DEV-02"

    with pytest.raises(ValueError, match="Verified evidence"):
        render_review_packet(receipt, assessments, ranker_cases)


def test_rejects_verified_evidence_with_an_unknown_event() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()
    assessments[0]["evidence_references"][0]["event_id"] = "MISSING-EVENT"

    with pytest.raises(ValueError, match="Verified evidence"):
        render_review_packet(receipt, assessments, ranker_cases)


def test_compares_only_review_queue_cases_to_the_selection_boundary() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()
    third_case = {**ranker_cases[1], "case_id": "EQ-F02-DEV-01"}
    third_assessment = {**assessments[1], "case_id": "EQ-F02-DEV-01"}
    assessments.append(third_assessment)
    ranker_cases.append(third_case)

    packet = render_review_packet(receipt, assessments, ranker_cases)

    assert "EQ-F02-DEV-01" not in packet


def test_ticket_evidence_packet_is_reproducible_from_frozen_review_inputs() -> None:
    receipt, assessments, ranker_cases = _ticket_16_review_inputs()

    packet = render_review_packet(receipt, assessments, ranker_cases)

    evidence_path = Path(__file__).parents[1] / "docs/evidence/ticket-18/review-packet.html"
    assert evidence_path.read_text(encoding="utf-8") == f"{packet}\n"
