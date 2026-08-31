import json

from edgequeue.results import load_case_assessment


def test_loads_the_ranking_fields_from_a_saved_final_output(tmp_path) -> None:
    final_output = tmp_path / "final.json"
    final_output.write_text(
        json.dumps(
            {
                "case_id": "case-a",
                "status": "risk_finding",
                "risk_score": 82,
                "reason_codes": ["missing_check"],
            }
        ),
        encoding="utf-8",
    )

    assessment = load_case_assessment(final_output, deterministic_score=40)

    assert assessment.case_id == "case-a"
    assert assessment.status == "risk_finding"
    assert assessment.risk_score == 82
    assert assessment.deterministic_score == 40
