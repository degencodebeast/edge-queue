"""Stable local command interfaces for the EdgeQueue workflow."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


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
        help="Record optional live provider behavior separately from offline proof.",
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
        help="Frozen Reviewer Manifest version.",
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

    verify = commands.add_parser(
        "verify", help="Verify a Proof Bundle offline without writing to it."
    )
    verify.add_argument("bundle", help="Proof Bundle directory.")
    verify.add_argument(
        "--json", action="store_true", help="Print the machine-readable result."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse a frozen command interface and report unimplemented later slices."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "judge":
        parser.error("judge execution is provided by the later proof slice")
    if args.command == "adjudicate":
        parser.error("adjudicate execution is provided by the later reviewer slice")
    parser.error("verify execution is provided by the later proof slice")


if __name__ == "__main__":
    raise SystemExit(main())
