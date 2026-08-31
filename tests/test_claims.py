import json
from pathlib import Path

from edgequeue.claims import generate_claims_manifest
from edgequeue.contracts import digest_contract, validate_claims_manifest


def test_generates_only_a_scoped_synthetic_corpus_claim() -> None:
    root = Path("docs/evidence/ticket-20")
    run = json.loads((root / "evaluation-run.json").read_text(encoding="utf-8"))
    ranker_cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path("corpus/ranker/allocation-holdout").glob("*.json"))]
    scorer_cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path("corpus/scorer/allocation-holdout").glob("*.json"))]

    manifest, claims = generate_claims_manifest(
        evaluation_run=run,
        ranker_cases=ranker_cases,
        scorer_cases=scorer_cases,
        supporting_artifact="metrics.json",
    )

    assert [claim["metric"] for claim in claims] == ["allocation_holdout_recall_at_8"]
    assert claims[0]["value"] == 0.8
    assert "frozen synthetic Allocation Holdout" in claims[0]["text"]
    assert "does not establish production performance" in claims[0]["text"]
    assert "does not establish" in claims[0]["text"]
    assert manifest["evaluation_run_digest"] == digest_contract("evaluation_run", run)
    assert validate_claims_manifest(manifest, claims) == manifest
