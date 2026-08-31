"""Run the Allocation Holdout three times and preserve every trace bundle."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from edgequeue.corpus import build_allocation_holdout_cases
from edgequeue.trace_capture import TraceBundle, run_case_assessment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "runs" / "allocation-holdout"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "case-assessment.schema.json"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
ATTEMPTS = (1, 2, 3)
WORKERS = 4


def needs_run(case_id: str, attempt: int) -> bool:
    return not (TRACE_ROOT / case_id / f"attempt-{attempt:02d}" / "final.json").exists()


def run_case(case, attempt: int) -> TraceBundle:
    return run_case_assessment(
        case.ranker_case,
        project_root=PROJECT_ROOT,
        trace_root=TRACE_ROOT,
        schema_path=SCHEMA_PATH,
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        attempt=attempt,
    )


def main() -> int:
    pending = [
        (case, attempt)
        for case in build_allocation_holdout_cases()
        for attempt in ATTEMPTS
        if needs_run(case.ranker_case.case_id, attempt)
    ]
    bundles: list[TraceBundle] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(run_case, case, attempt): (case.ranker_case.case_id, attempt)
            for case, attempt in pending
        }
        for future in as_completed(futures):
            bundle = future.result()
            bundles.append(bundle)
            print(
                f"{bundle.case_id} attempt={bundle.attempt} "
                f"return_code={bundle.return_code} elapsed_seconds={bundle.elapsed_seconds:.2f}"
            )

    manifest = {
        "split": "AH",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "attempts": ATTEMPTS,
        "case_count": len(build_allocation_holdout_cases()),
        "new_runs": [
            {
                "case_id": bundle.case_id,
                "attempt": bundle.attempt,
                "return_code": bundle.return_code,
                "elapsed_seconds": bundle.elapsed_seconds,
                "directory": str(bundle.directory),
            }
            for bundle in sorted(bundles, key=lambda item: (item.case_id, item.attempt))
        ],
    }
    TRACE_ROOT.mkdir(parents=True, exist_ok=True)
    (TRACE_ROOT / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if all(bundle.return_code == 0 for bundle in bundles) else 1


if __name__ == "__main__":
    raise SystemExit(main())
