"""Stable local command interfaces for the EdgeQueue workflow."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from edgequeue.adjudication import AdjudicationError, append_adjudication, create_adjudication
from edgequeue.contracts import ContractValidationError, digest_contract, validate_contract
from edgequeue.judge import JudgeFixtureError, format_judge_summary, record_live_run_unavailable, run_judge_fixture
from edgequeue.verification import verify_proof_bundle


def build_parser() -> argparse.ArgumentParser:
    """Build the frozen judge, adjudicate, and verify command interface."""
    parser = argparse.ArgumentParser(
        prog="edgequeue",
        description="Offline, content-bound EdgeQueue evaluation workflow.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    judge = commands.add_parser(
        "judge", help="Run the four-case offline Judge Fixture."
    )
    judge.add_argument(
        "--live",
        action="store_true",
        help="Reserved for a separately configured live provider; unavailable in Offline Replay.",
    )
    judge.add_argument(
        "--output-dir",
        help="Write generated judge artifacts to this directory.",
    )

    adjudicate = commands.add_parser(
        "adjudicate", help="Append one authorized human Adjudication."
    )
    adjudicate.add_argument("--case-id", required=True, help="Case identifier.")
    adjudicate.add_argument("--reviewer-id", required=True, help="Reviewer identity.")
    adjudicate.add_argument(
        "--decision",
        required=True,
        choices=("preserve", "correct", "abstain"),
        help="Authoritative human decision.",
    )
    adjudicate.add_argument(
        "--input", dest="input_path", help="Existing append-only record or review input."
    )
    adjudicate.add_argument(
        "--prior-record-digest",
        required=True,
        help="Digest of the authoritative record being adjudicated.",
    )
    adjudicate.add_argument(
        "--reviewer-manifest",
        required=True,
        help="Path to the frozen Reviewer Manifest JSON record.",
    )
    adjudicate.add_argument(
        "--rationale", required=True, help="Human rationale bound to the append-only record."
    )
    adjudicate.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="Evidence reference. Repeat for more than one.",
    )
    adjudicate.add_argument(
        "--output", dest="output_path", help="Path for the new append-only record."
    )
    adjudicate.add_argument(
        "--resulting-verdict",
        choices=("PASS", "FAIL", "UNDETERMINED"),
        help="Resulting Verdict. Required for a correct decision.",
    )
    adjudicate.add_argument(
        "--adjudication-id", required=True, help="Immutable Adjudication identifier."
    )

    verify = commands.add_parser(
        "verify", help="Verify a Proof Bundle offline without writing to it."
    )
    verify.add_argument("bundle", help="Proof Bundle directory.")
    verify.add_argument(
        "--json", action="store_true", help="Print the machine-readable result."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and run the frozen local command interfaces."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "judge":
        output_dir = Path(args.output_dir) if args.output_dir else Path("judge-output")
        if args.live:
            record = record_live_run_unavailable(output_dir)
            print(f"Live Run: {record['status']} ({record['reason']})")
            print(f"Artifacts: {output_dir}")
            return 0
        fixture_path = Path("corpus/fixtures/judge-fixture-v1.json")
        try:
            result = run_judge_fixture(fixture_path, output_dir)
        except (JudgeFixtureError, OSError, ValueError) as error:
            parser.error(str(error))
        print(format_judge_summary(result))
        return 0
    if args.command == "adjudicate":
        return _run_adjudicate(parser, args)
    result = verify_proof_bundle(Path(args.bundle))
    if args.json:
        print(json.dumps(result.as_dict(), separators=(",", ":"), sort_keys=True))
    else:
        print("Proof Bundle valid" if result.valid else "Proof Bundle invalid")
        for failure in result.failures:
            print(f"{failure.code}: {failure.message}")
    return 0 if result.valid else 1


def _run_adjudicate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Create and append one local human Adjudication from frozen JSON inputs."""
    if args.input_path is None or args.output_path is None:
        parser.error("adjudicate requires --input and --output")
    try:
        review_input = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
        manifest = json.loads(Path(args.reviewer_manifest).read_text(encoding="utf-8"))
        evidence = [json.loads(reference) for reference in args.evidence]
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"adjudicate input is invalid: {error}")
    try:
        context, event_ids = _bound_adjudication_context(review_input)
    except (AdjudicationError, ContractValidationError) as error:
        parser.error(str(error))
    if context["case_id"] != args.case_id:
        parser.error("--case-id does not match the selected frozen Review Queue case")
    if context.get("prior_record_digest") != args.prior_record_digest:
        parser.error("--prior-record-digest does not match the frozen Adjudication context")
    resulting_verdict = args.resulting_verdict or context.get("prior_verdict")
    if any(reference.get("event_id") not in event_ids for reference in evidence):
        parser.error("adjudicate evidence must reference an event in the selected case")
    try:
        record = create_adjudication(
            context=context,
            reviewer_manifest=manifest,
            reviewer_id=args.reviewer_id,
            action=args.decision,
            resulting_verdict=resulting_verdict,
            rationale=args.rationale,
            evidence_references=evidence,
            adjudication_id=args.adjudication_id,
        )
        append_adjudication(Path(args.output_path), record, manifest)
    except AdjudicationError as error:
        parser.error(str(error))
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))
    return 0


def _bound_adjudication_context(review_input: object) -> tuple[dict[str, object], set[str]]:
    """Derive authority bindings from the frozen selected case and receipt."""
    if not isinstance(review_input, dict):
        raise AdjudicationError("adjudicate input must be a Review Packet context object")
    ranker_case = review_input.get("ranker_case")
    receipt = review_input.get("allocation_receipt")
    context = review_input.get("context")
    if not isinstance(ranker_case, dict) or not isinstance(receipt, dict) or not isinstance(context, dict):
        raise AdjudicationError("adjudicate input requires ranker_case, allocation_receipt, and context")
    validate_contract("ranker_case", ranker_case)
    validate_contract("allocation_receipt", receipt)
    case_id = ranker_case["case_id"]
    if case_id not in receipt["review_queue"]:
        raise AdjudicationError("Adjudication case is not selected in the frozen Review Queue")
    bound = {
        **context,
        "case_id": case_id,
        "prior_record_digest": ranker_case["content_digest"],
        "prior_verdict": ranker_case["current_verdict"],
        "trajectory_digest": ranker_case["content_digest"],
        "allocation_receipt_digest": digest_contract("allocation_receipt", receipt),
        "corpus_digest": receipt["corpus_digest"],
        "split_digest": receipt["split_digest"],
    }
    event_ids = {event["event_id"] for event in ranker_case["trajectory_events"]}
    return bound, event_ids


if __name__ == "__main__":
    raise SystemExit(main())
