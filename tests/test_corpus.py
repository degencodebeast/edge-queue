from dataclasses import asdict

from edgequeue.corpus import build_allocation_holdout_cases, build_development_cases


def test_builds_isolated_development_case_from_frozen_allocation() -> None:
    case = build_development_cases()[0]
    ranker_payload = asdict(case.ranker_case)
    scorer_payload = asdict(case.scorer_case)

    assert case.ranker_case.case_id == "EQ-F01-DEV-01"
    assert case.ranker_case.current_verdict == "FAIL"
    assert case.scorer_case.reference_verdict == "UNDETERMINED"
    assert "reference_verdict" not in ranker_payload
    assert "scorer_sentinel" not in ranker_payload
    assert scorer_payload["scorer_sentinel"].startswith("SCORER_ONLY_EQ_F01_DEV_01_")


def test_builds_the_twenty_cases_required_for_the_development_split() -> None:
    cases = build_development_cases()
    case_ids = {case.ranker_case.case_id for case in cases}

    assert len(cases) == 20
    assert case_ids == {
        f"EQ-F{family:02d}-DEV-{case:02d}"
        for family in range(1, 11)
        for case in range(1, 3)
    }
    assert sum(case.scorer_case.kind == "label_error" for case in cases) == 5
    assert sum(case.scorer_case.kind == "hard_control" for case in cases) == 5


def test_builds_the_forty_cases_required_for_the_allocation_holdout() -> None:
    cases = build_allocation_holdout_cases()
    case_ids = {case.ranker_case.case_id for case in cases}

    assert len(cases) == 40
    assert case_ids == {
        f"EQ-F{family:02d}-AH-{case:02d}"
        for family in range(1, 11)
        for case in range(1, 5)
    }
    assert sum(case.scorer_case.kind == "label_error" for case in cases) == 10
    assert sum(case.scorer_case.kind == "hard_control" for case in cases) == 5
