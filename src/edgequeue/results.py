"""Load saved Case Assessment outputs for canonical scoring."""

from __future__ import annotations

import json
from pathlib import Path

from edgequeue.ranking import CaseAssessment


def load_case_assessment(
    final_output_path: Path,
    *,
    deterministic_score: int,
) -> CaseAssessment:
    """Load allocator ranking fields from one final Case Assessment output."""
    payload = json.loads(final_output_path.read_text(encoding="utf-8"))
    return CaseAssessment(
        case_id=payload["case_id"],
        status=payload["status"],
        risk_score=payload["risk_score"],
        deterministic_score=deterministic_score,
    )
