"""Run the Development Split and preserve one trace bundle per Case Assessment."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from edgequeue.corpus import build_development_cases
from edgequeue.trace_capture import TraceBundle, run_case_assessment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "runs" / "development"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "case-assessment.schema.json"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
WORKERS = 4


def needs_run(case_id: str) -> bool:
    final_output = TRACE_ROOT / case_id / "attempt-01" / "final.json"
    return not final_output.exists()


def run_case(case) -> TraceBundle:
    return run_case_assessment(
        case.ranker_case,
        project_root=PROJECT_ROOT,
        trace_root=TRACE_ROOT,
        schema_path=SCHEMA_PATH,
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
    )


def main() -> int:
    pending_cases = [case for case in build_development_cases() if needs_run(case.ranker_case.case_id)]
    bundles: list[TraceBundle] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(run_case, case): case.ranker_case.case_id for case in pending_cases}
        for future in as_completed(futures):
            bundle = future.result()
            bundles.append(bundle)
            print(f"{bundle.case_id} return_code={bundle.return_code} elapsed_seconds={bundle.elapsed_seconds:.2f}")

    manifest = {
        "split": "DEV",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "case_count": len(build_development_cases()),
        "new_runs": [
            {
                "case_id": bundle.case_id,
                "return_code": bundle.return_code,
                "elapsed_seconds": bundle.elapsed_seconds,
                "directory": str(bundle.directory),
            }
            for bundle in sorted(bundles, key=lambda item: item.case_id)
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
