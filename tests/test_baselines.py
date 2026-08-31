from edgequeue.baselines import (
    allocate_deterministic,
    allocate_disagreement,
    allocate_lowest_confidence,
    allocate_random,
)


def test_lowest_confidence_uses_stable_case_identifier_ties() -> None:
    review_queue = allocate_lowest_confidence(
        confidence_by_case={
            "case-a": 80,
            "case-b": 10,
            "case-c": 10,
            "case-d": 40,
        },
        review_budget=2,
    )

    assert review_queue == ("case-b", "case-c")


def test_seeded_random_allocation_replays_the_same_queue() -> None:
    case_ids = ("case-a", "case-b", "case-c", "case-d")

    first_queue = allocate_random(
        case_ids=case_ids,
        review_budget=2,
        seed=37,
    )
    second_queue = allocate_random(
        case_ids=case_ids,
        review_budget=2,
        seed=37,
    )

    assert first_queue == second_queue
    assert len(first_queue) == 2
    assert len(set(first_queue)) == 2


def test_disagreement_ranks_three_way_conflict_above_two_to_one_conflict() -> None:
    review_queue = allocate_disagreement(
        verdicts_by_case={
            "case-a": ("PASS", "PASS", "PASS"),
            "case-b": ("PASS", "FAIL", "PASS"),
            "case-c": ("PASS", "FAIL", "UNDETERMINED"),
            "case-d": ("FAIL", "FAIL", "FAIL"),
        },
        review_budget=2,
    )

    assert review_queue == ("case-c", "case-b")


def test_deterministic_baseline_uses_stable_descending_risk_order() -> None:
    review_queue = allocate_deterministic(
        risk_by_case={
            "case-a": 20,
            "case-b": 70,
            "case-c": 70,
            "case-d": 10,
        },
        review_budget=2,
    )

    assert review_queue == ("case-b", "case-c")
