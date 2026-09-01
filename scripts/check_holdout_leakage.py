"""Reject Allocation Holdout runs that expose scorer-only fields or sentinels."""

from __future__ import annotations

from pathlib import Path

from edgequeue.corpus import build_allocation_holdout_cases
from edgequeue.integrity import reject_scorer_leakage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "docs" / "evidence" / "ticket-20" / "frozen-traces"


def main() -> int:
    scorer_sentinels = {
        case.scorer_case.scorer_sentinel for case in build_allocation_holdout_cases()
    }
    artifacts = {}
    for path in sorted(TRACE_ROOT.glob("EQ-*/attempt-*/*")):
        if path.is_file():
            artifacts[str(path.relative_to(TRACE_ROOT))] = path.read_text(encoding="utf-8")
    reject_scorer_leakage(
        artifacts,
        forbidden_field_names={"reference_verdict", "scorer_sentinel"},
        scorer_sentinels=scorer_sentinels,
    )
    print(f"checked_files={len(artifacts)} leakage=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
