"""Prompt rendering for allocator-visible EdgeQueue cases."""

from __future__ import annotations

from edgequeue.corpus import RankerCase


def render_case_assessment_prompt(case: RankerCase) -> str:
    """Render one Case Assessment prompt from a RankerCase."""
    rubric = "\n".join(
        f"- {clause.clause_id}: {clause.text}" for clause in case.rubric_clauses
    )
    events = "\n".join(
        f"- {event.event_id} {event.event_type}: {event.content}"
        for event in case.trajectory_events
    )
    return f"""You are the EdgeQueue allocator.

Assess whether the current Verdict may be wrong.
Use only the rubric and Trajectory Events below.
Do not treat your answer as an authoritative correction.
Return one JSON object that matches the supplied output schema.

Each evidence relation applies to the current Verdict:
- supports_current means the evidence supports the current Verdict.
- contradicts_current means the evidence contradicts the current Verdict.
- insufficient means the evidence cannot support or contradict the current Verdict.

Case ID: {case.case_id}
Current Verdict: {case.current_verdict}
Current rationale: {case.current_rationale}
Current confidence: {case.primary_confidence}

Rubric:
{rubric}

Trajectory Events:
{events}

Create a Risk Finding when verified evidence indicates the current Verdict may be wrong.
Use Agent Abstention when the permitted evidence cannot support a Risk Finding.
"""
