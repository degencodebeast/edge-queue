import json
from pathlib import Path

from edgequeue.contracts import content_digest, validate_contract
from edgequeue.evaluation_run import (
    build_evaluation_run,
    derive_archived_evaluation_results,
    preserve_evaluation_results,
    recompute_saved_evaluation_result,
    recompute_allocation_metrics,
)


def _digest(name: str) -> str:
    return content_digest({"ticket": "20", "name": name})


def test_builds_a_content_bound_evaluation_run() -> None:
    core = {
        name: {"fixture": name}
        for name in (
            "corpus_manifest",
            "split_manifest",
            "ranker_case_bundle",
            "rubric_snapshot",
            "initial_evaluation_snapshot",
            "evidence_validation_manifest",
            "allocator_prompt",
            "allocator_model_config",
            "feature_version",
            "ranking_policy",
            "evaluation_config",
            "scorer_reference_manifest",
            "canonical_scorer",
            "runtime_dependency_manifest",
            "risk_findings",
            "review_queue",
            "allocation_receipt",
            "raw_run_outputs",
        )
    }
    receipt = {
        "schema_version": "1.0",
        "receipt_id": "receipt-20",
        "evaluation_run_id": "run-20",
        "corpus_digest": _digest("corpus"),
        "split_digest": _digest("split"),
        "allocator_config_digest": content_digest({"name": "offline-fixture"}),
        "review_budget": 1,
        "assessments": [],
        "review_queue": ["case-1"],
        "first_excluded_case_id": None,
        "selection_boundary": None,
    }
    core["allocation_receipt"] = receipt

    run = build_evaluation_run(
        evaluation_run_id="run-20",
        corpus_digest=_digest("corpus"),
        split_digest=_digest("split"),
        evaluation_config={"review_budget": 1},
        allocator_config={"name": "offline-fixture"},
        command=["uv", "run", "edgequeue", "judge"],
        code_commit="08e1a8575e5ed20f00b1d9700517fee2ee17facd",
        git_tree="clean-tree",
        tested_working_tree={"tree": "clean-tree"},
        evaluation_core=core,
        allocation_receipt=receipt,
        case_ids=["case-1"],
        review_queue=["case-1"],
        raw_artifact_refs=["traces/case-1/final.json"],
        runtime_seconds=0.25,
        request_count=0,
        token_count=0,
        available_cost=0.0,
    )

    assert run["evaluation_config_digest"] == content_digest({"review_budget": 1})
    assert run["command_digest"] == content_digest(["uv", "run", "edgequeue", "judge"])
    assert run["allocation_receipt_digest"] == content_digest(receipt)
    assert run["evaluation_core"]["canonical_scorer"]["name"] == "canonical_scorer"
    assert validate_contract("evaluation_run", run) == run


def test_recomputes_metrics_from_authoritative_scorer_cases() -> None:
    metrics = recompute_allocation_metrics(
        review_queue=["case-a", "case-b"],
        ranker_cases=[
            {"case_id": "case-a", "current_verdict": "PASS", "defect_family": "family-one"},
            {"case_id": "case-b", "current_verdict": "FAIL", "defect_family": "family-two"},
            {"case_id": "case-c", "current_verdict": "PASS", "defect_family": "family-one"},
        ],
        scorer_cases=[
            {"case_id": "case-a", "reference_verdict": "FAIL"},
            {"case_id": "case-b", "reference_verdict": "FAIL"},
            {"case_id": "case-c", "reference_verdict": "FAIL"},
        ],
        review_budget=2,
    )

    assert metrics == {
        "recall_at_k": 0.5,
        "precision_at_k": 0.5,
        "false_negative_ids": ["case-c"],
        "oracle_regret": 1,
        "defect_families": {
            "family-one": {"label_error_count": 2, "selected_label_error_count": 1, "recall_at_k": 0.5},
            "family-two": {"label_error_count": 0, "selected_label_error_count": 0, "recall_at_k": None},
        },
    }


def test_preserves_development_and_three_accepted_holdout_results() -> None:
    fixture = Path("tests/fixtures/ticket-20/accepted-results.json")
    source = json.loads(fixture.read_text(encoding="utf-8"))
    results = preserve_evaluation_results(**source)

    assert results["development"]["split"] == "DEV"
    assert len(results["allocation_holdout_runs"]) == 3


def test_recomputes_the_saved_development_result_from_frozen_cases() -> None:
    saved = json.loads(Path("runs/development/evaluation.json").read_text(encoding="utf-8"))
    ranker_cases = [json.loads(path.read_text()) for path in sorted(Path("corpus/ranker/development").glob("*.json"))]
    scorer_cases = [json.loads(path.read_text()) for path in sorted(Path("corpus/scorer/development").glob("*.json"))]

    results = recompute_saved_evaluation_result(
        saved_result=saved,
        ranker_cases=ranker_cases,
        scorer_cases=scorer_cases,
    )

    assert results["edgequeue"]["recall_at_k"] == 0.8


def test_derives_development_and_all_holdout_results_from_archived_sources() -> None:
    development_source = json.loads(Path("runs/development/evaluation.json").read_text(encoding="utf-8"))
    holdout_source = json.loads(Path("runs/allocation-holdout/evaluation.json").read_text(encoding="utf-8"))
    development_ranker = [json.loads(path.read_text()) for path in sorted(Path("corpus/ranker/development").glob("*.json"))]
    development_scorer = [json.loads(path.read_text()) for path in sorted(Path("corpus/scorer/development").glob("*.json"))]
    holdout_ranker = [json.loads(path.read_text()) for path in sorted(Path("corpus/ranker/allocation-holdout").glob("*.json"))]
    holdout_scorer = [json.loads(path.read_text()) for path in sorted(Path("corpus/scorer/allocation-holdout").glob("*.json"))]

    results = derive_archived_evaluation_results(
        development_source=development_source,
        development_ranker_cases=development_ranker,
        development_scorer_cases=development_scorer,
        allocation_holdout_source=holdout_source,
        allocation_holdout_ranker_cases=holdout_ranker,
        allocation_holdout_scorer_cases=holdout_scorer,
    )

    assert results["development"]["fixed"] == development_source["fixed"]
    assert results["development"]["seeded_random"]["p95_recall_at_k"] == 0.4
    assert [run["fixed"] for run in results["allocation_holdout_runs"]] == [
        holdout_source["attempts_detail"][str(attempt)]["fixed"]
        for attempt in (1, 2, 3)
    ]
    assert [run["edgequeue"]["recall_at_k"] for run in results["allocation_holdout_runs"]] == [0.8, 0.8, 0.8]
    assert [run["simple_baseline"]["recall_at_k"] for run in results["allocation_holdout_runs"]] == [0.0, 0.0, 0.0]
    assert [run["seeded_random"]["p95_recall_at_k"] for run in results["allocation_holdout_runs"]] == [0.4, 0.4, 0.4]

    evidence = json.loads(Path("docs/evidence/ticket-20/evaluation-results.json").read_text(encoding="utf-8"))
    assert evidence["authoritative_sources"] == {
        "development_evaluation": {
            "path": "runs/development/evaluation.json",
            "content_digest": content_digest(development_source),
        },
        "allocation_holdout_evaluation": {
            "path": "runs/allocation-holdout/evaluation.json",
            "content_digest": content_digest(holdout_source),
        },
    }
    assert evidence["development"] == {
        "split": "DEV",
        "review_budget": 4,
        "edgequeue": results["development"]["fixed"]["edgequeue"],
        "strongest_simple_baseline_recall_at_k": 0.0,
        "seeded_random": results["development"]["seeded_random"],
    }
    assert evidence["allocation_holdout_runs"] == [
        {
            "run_id": result["run_id"],
            "split": result["split"],
            "review_budget": result["review_budget"],
            "edgequeue": result["fixed"]["edgequeue"],
            "simple_baseline": result["simple_baseline"],
            "seeded_random": result["seeded_random"],
        }
        for result in results["allocation_holdout_runs"]
    ]

    run = json.loads(Path("docs/evidence/ticket-20/evaluation-run.json").read_text(encoding="utf-8"))
    assert run["review_queue"] == results["allocation_holdout_runs"][0]["fixed"]["edgequeue"]["review_queue"]
    assert run["runtime_seconds"] == 13.356252193450928
    assert run["request_count"] == 1
    assert run["token_count"] == 16270
    assert run["available_cost"] is None

    metrics = json.loads(Path("docs/evidence/ticket-20/metrics.json").read_text(encoding="utf-8"))
    assert {key: metrics[key] for key in ("recall_at_k", "precision_at_k", "false_negative_ids", "oracle_regret", "defect_families")} == recompute_allocation_metrics(
        review_queue=run["review_queue"],
        ranker_cases=holdout_ranker,
        scorer_cases=holdout_scorer,
        review_budget=8,
    )
