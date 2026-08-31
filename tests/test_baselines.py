from edgequeue.baselines import (
    allocate_deterministic,
    allocate_disagreement,
    allocate_lowest_confidence,
    allocate_random,
    allocate_fair_baselines,
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


def test_runs_five_fair_baselines_with_one_review_budget() -> None:
    queues = allocate_fair_baselines(
        confidence_by_case={"case-a": 90, "case-b": 20, "case-c": 60},
        verdicts_by_case={
            "case-a": ("PASS", "PASS", "PASS"),
            "case-b": ("PASS", "FAIL", "PASS"),
            "case-c": ("FAIL", "FAIL", "FAIL"),
        },
        deterministic_scores_by_case={"case-a": 30, "case-b": 70, "case-c": 40},
        current_verdicts={"case-a": "PASS", "case-b": "PASS", "case-c": "FAIL"},
        reference_verdicts={"case-a": "FAIL", "case-b": "PASS", "case-c": "FAIL"},
        review_budget=2,
        random_seed=37,
    )

    assert set(queues) == {
        "seeded_random",
        "lowest_confidence",
        "disagreement_only",
        "deterministic_only",
        "oracle",
    }
    assert all(len(queue) == 2 and len(set(queue)) == 2 for queue in queues.values())
