import json
from pathlib import Path

from edgequeue.contracts import content_digest, digest_contract, validate_contract
from edgequeue.evaluation_run import (
    build_allocation_receipt_from_captured_outputs,
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


def test_recomputes_checked_in_allocation_receipt_from_current_frozen_inputs() -> None:
    root = Path("docs/evidence/ticket-20/frozen-traces")
    ranker_cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path("corpus/ranker/allocation-holdout").glob("*.json"))
    ]
    evaluation_run = json.loads(
        Path("docs/evidence/ticket-20/evaluation-run.json").read_text(
            encoding="utf-8"
        )
    )

    attempt_one_receipt = None
    for attempt in (1, 2, 3):
        captured_outputs = [
            json.loads(
                (
                    root / case["case_id"] / f"attempt-{attempt:02d}" / "final.json"
                ).read_text(encoding="utf-8")
            )
            for case in ranker_cases
        ]
        receipt = json.loads(
            Path(
                f"docs/evidence/ticket-20/allocation-receipts/attempt-{attempt:02d}.json"
            ).read_text(encoding="utf-8")
        )
        metadata = json.loads(
            (root / ranker_cases[0]["case_id"] / f"attempt-{attempt:02d}" / "metadata.json").read_text(
                encoding="utf-8"
            )
        )

        recomputed = build_allocation_receipt_from_captured_outputs(
            ranker_cases=ranker_cases,
            captured_outputs=captured_outputs,
            allocator_config={"model": "gpt-5.6-luna", "reasoning_effort": "low"},
            receipt_id=f"ticket-20-allocation-holdout-attempt-{attempt:02d}",
            evaluation_run_id="ticket-20-allocation-holdout",
            corpus_digest=evaluation_run["corpus_digest"],
            split_digest=evaluation_run["split_digest"],
            review_budget=8,
            attempt=metadata["attempt"],
        )

        assert metadata["attempt"] == attempt
        assert recomputed == receipt
        if attempt == 1:
            attempt_one_receipt = receipt

    assert attempt_one_receipt is not None
    assert evaluation_run["allocation_receipt_digest"] == digest_contract(
        "allocation_receipt", attempt_one_receipt
    )
    assert evaluation_run["evaluation_core"]["allocation_receipt"]["digest"] == evaluation_run[
        "allocation_receipt_digest"
    ]


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


def test_derives_all_holdout_results_from_current_frozen_traces() -> None:
    ranker_cases = [
        json.loads(path.read_text())
        for path in sorted(Path("corpus/ranker/allocation-holdout").glob("*.json"))
    ]
    scorer_cases = [
        json.loads(path.read_text())
        for path in sorted(Path("corpus/scorer/allocation-holdout").glob("*.json"))
    ]
    evidence_root = Path("docs/evidence/ticket-20")
    results = json.loads((evidence_root / "evaluation-results.json").read_text())
    development_source = json.loads(
        Path("runs/development/evaluation.json").read_text(encoding="utf-8")
    )

    assert results["authoritative_sources"]["development_evaluation"] == {
        "path": "runs/development/evaluation.json",
        "content_digest": content_digest(development_source),
    }
    assert results["development"]["split"] == "DEV"
    assert results["development"]["edgequeue"] == development_source["fixed"]["edgequeue"]

    for attempt in (1, 2, 3):
        receipt = json.loads(
            (evidence_root / f"allocation-receipts/attempt-{attempt:02d}.json").read_text()
        )
        expected_metrics = recompute_allocation_metrics(
            review_queue=receipt["review_queue"],
            ranker_cases=ranker_cases,
            scorer_cases=scorer_cases,
            review_budget=8,
        )
        assert results["authoritative_sources"][f"attempt_{attempt:02d}_receipt"] == {
            "path": f"allocation-receipts/attempt-{attempt:02d}.json",
            "content_digest": digest_contract("allocation_receipt", receipt),
        }
        assert results["allocation_holdout_runs"][attempt - 1]["edgequeue"] == {
            "review_queue": receipt["review_queue"],
            "metrics": expected_metrics,
        }

    run = json.loads((evidence_root / "evaluation-run.json").read_text())
    assert run["review_queue"] == results["allocation_holdout_runs"][0]["edgequeue"]["review_queue"]
    assert run["request_count"] == 40
    assert run["available_cost"] is None
