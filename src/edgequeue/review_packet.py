"""Render readable, non-authoritative Review Packets for selected cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any


class ReviewPacketError(ValueError):
    """A Review Packet input cannot describe the selected Review Queue."""


def render_review_packet(
    allocation_receipt: Mapping[str, Any],
    assessments: Sequence[Mapping[str, Any]],
    ranker_cases: Sequence[Mapping[str, Any]],
) -> str:
    """Return an HTML Review Packet without granting any decision authority."""
    selected_case_ids = _selected_case_ids(allocation_receipt)
    assessments_by_case = _records_by_case(assessments, "Case Assessments")
    cases_by_id = _records_by_case(ranker_cases, "RankerCases")
    if any(case_id not in assessments_by_case or case_id not in cases_by_id for case_id in selected_case_ids):
        raise ReviewPacketError("Review Queue references a case without review inputs")

    selected_cases = "".join(
        _case_section(case_id, assessments_by_case[case_id], cases_by_id[case_id])
        for case_id in selected_case_ids
    )
    boundary = allocation_receipt.get("selection_boundary")
    return "".join(
        (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
            "<title>EdgeQueue Review Packet</title>",
            "<style>body{font-family:system-ui;margin:2rem;max-width:72rem}"
            "table{border-collapse:collapse;width:100%;margin:1rem 0}"
            "th,td{border:1px solid #bbb;padding:.5rem;text-align:left;vertical-align:top}"
            ".verified{color:#126b32}.non-proof{color:#8a3b00;font-weight:600}"
            "code{white-space:normal}</style></head><body>",
            "<h1>Review Packet</h1>",
            "<p>This packet presents allocator recommendations. Only an authorized human Adjudication can change a canonical Verdict.</p>",
            f"<p>Receipt: <code>{_text(allocation_receipt.get('receipt_id'))}</code>. "
            f"Review Budget: {_text(allocation_receipt.get('review_budget'))}.</p>",
            "<h2>Selected cases</h2>",
            selected_cases,
            _selection_boundary(
                boundary, selected_case_ids, assessments_by_case, cases_by_id
            ),
            "</body></html>",
        )
    )


def _selected_case_ids(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    queue = receipt.get("review_queue")
    if not isinstance(queue, list) or not queue or any(not isinstance(case_id, str) for case_id in queue):
        raise ReviewPacketError("Review Packet requires a non-empty Review Queue")
    if len(set(queue)) != len(queue):
        raise ReviewPacketError("Review Queue contains duplicate case identifiers")
    return tuple(queue)


def _records_by_case(
    records: Sequence[Mapping[str, Any]], label: str
) -> dict[str, Mapping[str, Any]]:
    by_case: dict[str, Mapping[str, Any]] = {}
    for record in records:
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or case_id in by_case:
            raise ReviewPacketError(f"{label} require unique case identifiers")
        by_case[case_id] = record
    return by_case


def _case_section(
    case_id: str, assessment: Mapping[str, Any], ranker_case: Mapping[str, Any]
) -> str:
    for reference in assessment.get("evidence_references", []):
        if isinstance(reference, Mapping) and reference.get("status") == "verified" and reference.get("case_id") != case_id:
            raise ReviewPacketError("Verified evidence must belong to its selected case")
    events = {
        str(event.get("event_id")): event
        for event in ranker_case.get("trajectory_events", [])
        if isinstance(event, Mapping)
    }
    clauses = {str(clause.get("clause_id")): str(clause.get("text")) for clause in ranker_case.get("rubric_clauses", []) if isinstance(clause, Mapping)}
    clause_rows = "".join(
        f"<li><code>{_text(clause_id)}</code>: {_text(clauses.get(str(clause_id), 'Clause text is unavailable.'))}</li>"
        for clause_id in assessment.get("rubric_clause_ids", [])
    ) or "<li>No rubric clause was supplied.</li>"
    return "".join(
        (
            f"<section><h3>{_text(case_id)}</h3>",
            f"<p>Current Verdict: <strong>{_text(ranker_case.get('current_verdict'))}</strong>. "
            f"Case Assessment: <strong>{_text(assessment.get('status'))}</strong>. "
            f"Risk score: <strong>{_text(assessment.get('risk_score'))}</strong>.</p>",
            f"<p>{_text(assessment.get('explanation'))}</p>",
            "<h4>Rubric clauses</h4><ul>", clause_rows, "</ul>",
            "<h4>Evidence</h4><table><thead><tr><th>Event</th><th>Evidence content</th><th>Relation</th><th>Claim</th><th>Status</th></tr></thead><tbody>",
            "".join(_evidence_row(reference, events) for reference in assessment.get("evidence_references", []) if isinstance(reference, Mapping)) or "<tr><td colspan=\"5\">No evidence reference was supplied.</td></tr>",
            "</tbody></table></section>",
        )
    )


def _evidence_row(reference: Mapping[str, Any], events: Mapping[str, Mapping[str, Any]]) -> str:
    status = str(reference.get("status"))
    status_class = "verified" if status == "verified" else "non-proof"
    label = "verified support" if status == "verified" else f"non-proof: {status}"
    return (
        "<tr>"
        f"<td>{_text(reference.get('event_id'))}</td>"
        f"<td>{_text(events.get(str(reference.get('event_id')), {}).get('content', 'Event content is unavailable.'))}</td>"
        f"<td>{_text(reference.get('relation'))}</td>"
        f"<td>{_text(reference.get('claim'))}</td>"
        f"<td class=\"{status_class}\">{_text(label)}</td></tr>"
    )


def _selection_boundary(
    boundary: Any,
    selected_case_ids: Sequence[str],
    assessments_by_case: Mapping[str, Mapping[str, Any]],
    cases_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    if not isinstance(boundary, Mapping):
        return "<h2>Selection boundary</h2><p>There was no excluded case.</p>"
    excluded_case_id = boundary.get("excluded_case_id")
    selected_rows = "".join(
        "<tr>"
        f"<td>{_text(case_id)}</td><td>{_text(assessment.get('status'))}</td>"
        f"<td>{_text(assessment.get('risk_score'))}</td>"
        f"<td>{_text(cases_by_id[case_id].get('deterministic_score'))}</td></tr>"
        for case_id in selected_case_ids
        if case_id != excluded_case_id and case_id in assessments_by_case and case_id in cases_by_id
        for assessment in (assessments_by_case[case_id],)
    )
    return (
        "<h2>Selection boundary</h2><p>First excluded case: "
        f"<code>{_text(excluded_case_id)}</code>. "
        f"Risk score: {_text(boundary.get('excluded_risk_score'))}. "
        f"Deterministic score: {_text(boundary.get('excluded_deterministic_score'))}. "
        f"Status: {_text(boundary.get('excluded_status'))}.</p>"
        "<table><thead><tr><th>Selected case</th><th>Status</th><th>Risk score</th><th>Deterministic score</th></tr></thead><tbody>"
        f"{selected_rows}</tbody></table>"
    )


def _text(value: Any) -> str:
    return escape("" if value is None else str(value))
