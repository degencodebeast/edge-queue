import json
import stat
from dataclasses import asdict, replace

import pytest

from edgequeue.corpus import (
    build_allocation_holdout_cases,
    build_development_cases,
    compile_complete_corpus,
    freeze_complete_corpus,
    scan_allocator_artifacts,
    validate_complete_corpus,
    validate_evaluation_run,
)
from edgequeue.contracts import ContractValidationError
from edgequeue.integrity import ScorerLeakageDetected
from edgequeue.contracts import validate_contract


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
    assert ranker_payload["schema_version"] == "1.0"
    assert scorer_payload["schema_version"] == "1.0"
    assert ranker_payload["rubric_clauses"][0]["schema_version"] == "1.0"
    assert ranker_payload["trajectory_events"][0]["schema_version"] == "1.0"
    validate_contract("ranker_case", ranker_payload)
    validate_contract("scorer_case", scorer_payload)


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


def test_freeze_complete_corpus_materializes_the_accepted_topology(tmp_path) -> None:
    frozen = freeze_complete_corpus(tmp_path)

    assert len(frozen.cases) == 80
    assert [manifest["split"] for manifest in frozen.split_manifests] == ["DEV", "AH", "PCH"]
    assert [len(manifest["case_digests"]) for manifest in frozen.split_manifests] == [20, 40, 20]
    assert len(frozen.root_manifest["root_corpus_digest"]) == 64
    assert (tmp_path / "ranker" / "development" / "EQ-F01-DEV-01.json").is_file()
    assert (tmp_path / "scorer" / "allocation-holdout" / "EQ-F01-AH-01.json").is_file()
    assert (tmp_path / "manifests" / "corpus.json").is_file()


def test_complete_compiler_preserves_the_fixed_reference_audit_and_allocation() -> None:
    frozen = compile_complete_corpus()

    assert sum(record["reference_audit"]["sample"] for record in frozen.provenance_records) == 20
    assert sum(case.scorer_case.kind == "label_error" for case in frozen.cases) == 20
    assert sum(case.scorer_case.kind == "hard_control" for case in frozen.cases) == 10


def test_complete_compiler_uses_stable_case_split_and_root_digests() -> None:
    first = compile_complete_corpus()
    second = compile_complete_corpus()

    assert first.cases[0].ranker_case.content_digest == second.cases[0].ranker_case.content_digest
    assert [manifest["manifest_digest"] for manifest in first.split_manifests] == [
        "e0531d96c0a8b8d96233f4dcac9ce9b3383db87d0d9ac101c746b766dfc8b46a",
        "04f63e41d339bc2bc3cdda86a74c5cf8b9c8a60034dfbc2556d50893ab9813e3",
        "1a04cf98c5f772427160bc9cf50237a77f31b804f029ded7be139d87b3824c71",
    ]
    assert first.root_manifest["root_corpus_digest"] == "ff509d989d9b2de1602528fc2b8c6a8d857786cc8b2c0c98456975c433c3ff61"


def test_intentional_scorer_leakage_rejects_the_run_and_every_visible_artifact_type(tmp_path) -> None:
    frozen = freeze_complete_corpus(tmp_path)
    safe_artifacts = {
        "prompt": "Assess the current Verdict from the RankerCase.",
        "risk_findings": {"case_id": "EQ-F01-DEV-01"},
        "review_queue": ["EQ-F01-DEV-01"],
        "allocation_receipt": {"case_id": "EQ-F01-DEV-01"},
        "exported_trajectories": [{"case_id": "EQ-F01-DEV-01", "content": "safe"}],
    }
    scan_allocator_artifacts(safe_artifacts, frozen)
    leakage = json.loads((tmp_path / "fixtures" / "intentional-leakage.json").read_text())

    with pytest.raises(ScorerLeakageDetected):
        scan_allocator_artifacts(leakage, frozen)

    assert validate_evaluation_run(leakage, frozen).disposition == "invalid"
    assert validate_evaluation_run(leakage, frozen).failure_code == "scorer_leakage"


def test_complete_corpus_validation_rechecks_authoritative_provenance_records() -> None:
    frozen = compile_complete_corpus()
    invalid_specification = {**frozen.case_specifications[0], "unexpected": True}
    invalid_frozen = replace(
        frozen,
        case_specifications=(invalid_specification, *frozen.case_specifications[1:]),
    )

    with pytest.raises(ContractValidationError, match="unknown field"):
        validate_complete_corpus(invalid_frozen)


def test_freeze_rejects_a_changed_immutable_corpus(tmp_path) -> None:
    freeze_complete_corpus(tmp_path)

    with pytest.raises(ValueError, match="immutable"):
        freeze_complete_corpus(tmp_path)


def test_freeze_rejects_a_preexisting_file_target(tmp_path) -> None:
    target = tmp_path / "corpus-target"
    target.write_text("not a corpus directory\n")

    with pytest.raises(ValueError, match="immutable"):
        freeze_complete_corpus(target)


def test_ranker_evidence_does_not_disclose_a_hidden_reference_verdict() -> None:
    case = build_development_cases()[0]
    decisive_evidence = case.ranker_case.trajectory_events[1].content

    assert case.scorer_case.reference_verdict == "UNDETERMINED"
    assert "UNDETERMINED" not in decisive_evidence
    assert "Verdict Transition" not in decisive_evidence
    changed_scorer = replace(
        case.scorer_case,
        reference_verdict="PASS",
        kind="control",
    )

    assert asdict(case.ranker_case) == asdict(replace(case, scorer_case=changed_scorer).ranker_case)


def test_evaluation_run_rechecks_the_frozen_corpus_before_scanning() -> None:
    frozen = compile_complete_corpus()
    invalid_frozen = replace(
        frozen,
        evaluator_manifest={**frozen.evaluator_manifest, "unexpected": True},
    )

    result = validate_evaluation_run({"prompt": "safe"}, invalid_frozen)

    assert result.disposition == "invalid"
    assert result.failure_code == "frozen_corpus_invalid"


def test_freeze_makes_every_corpus_path_non_writable(tmp_path) -> None:
    freeze_complete_corpus(tmp_path)
    paths = [tmp_path, *tmp_path.rglob("*")]

    try:
        assert all(not path.stat().st_mode & stat.S_IWUSR for path in paths)
    finally:
        for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
            path.chmod(0o755 if path.is_dir() else 0o644)
