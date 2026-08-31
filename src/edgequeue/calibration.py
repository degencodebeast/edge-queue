"""Create immutable Calibration Candidates from authorized Adjudications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from edgequeue.contracts import (
    canonical_json,
    content_digest,
    digest_contract,
    validate_adjudication_authority,
    validate_calibration_authority,
    validate_contract,
)
from edgequeue.scoring import AllocationMetrics, score_review_queue


_ISSUED_REPORT_IDS: set[int] = set()
_ISSUED_GATE_RESULT_IDS: set[int] = set()


@dataclass(frozen=True)
class CalibrationCandidate:
    """One immutable Calibration Candidate and its derived Calibration Case."""

    _record_json: str
    source_adjudication_digest: str
    calibration_case_digest: str

    def as_dict(self) -> dict[str, Any]:
        """Return a detached canonical candidate record."""
        return json.loads(self._record_json)

    @property
    def digest(self) -> str:
        """Return the content digest that identifies this candidate."""
        return digest_contract("calibration_candidate", self.as_dict())


class CalibrationHistory:
    """An append-only sequence of immutable Calibration Candidates."""

    __slots__ = ("__candidates", "__decisions", "__post_calibration_runs")

    def __init__(self) -> None:
        object.__setattr__(self, "_CalibrationHistory__candidates", ())
        object.__setattr__(self, "_CalibrationHistory__decisions", ())
        object.__setattr__(self, "_CalibrationHistory__post_calibration_runs", ())

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Calibration History is append-only")

    @property
    def candidates(self) -> tuple[CalibrationCandidate, ...]:
        """Return the immutable candidate sequence."""
        return self.__candidates

    @property
    def decisions(self) -> tuple["CalibrationDecision", ...]:
        """Return the immutable human-decision sequence."""
        return self.__decisions

    @property
    def post_calibration_runs(self) -> tuple["PostCalibrationRun", ...]:
        """Return the immutable Post-Calibration Holdout run sequence."""
        return self.__post_calibration_runs

    def append_candidate(self, candidate: CalibrationCandidate) -> "CalibrationHistory":
        """Return a history that contains one new candidate version."""
        candidate_id = candidate.as_dict()["candidate_id"]
        if any(
            existing.as_dict()["candidate_id"] == candidate_id
            for existing in self.candidates
        ):
            raise ValueError(f"Calibration Candidate {candidate_id} already exists")
        object.__setattr__(self, "_CalibrationHistory__candidates", (*self.candidates, candidate))
        return self

    def __append_decision(self, decision: "CalibrationDecision") -> None:
        object.__setattr__(self, "_CalibrationHistory__decisions", (*self.decisions, decision))

    def __append_holdout_run(self, run: "PostCalibrationRun") -> None:
        object.__setattr__(
            self,
            "_CalibrationHistory__post_calibration_runs",
            (*self.post_calibration_runs, run),
        )


@dataclass(frozen=True)
class CalibrationDecision:
    """One append-only authorized outcome for a Calibration Candidate."""

    candidate_digest: str
    status: str
    removal_reason: str | None
    _pack_json: str
    _promotion_json: str

    @property
    def pack(self) -> dict[str, Any]:
        """Return a detached immutable pack-version record."""
        return json.loads(self._pack_json)

    def promotion(self) -> dict[str, Any]:
        """Return a detached human promotion or rejection record."""
        return json.loads(self._promotion_json)


@dataclass(frozen=True)
class PostCalibrationHoldoutInput:
    """The first and only permitted evaluation input for the untouched holdout."""

    candidate_review_queue: tuple[str, ...]
    current_verdicts: Mapping[str, str]
    reference_verdicts: Mapping[str, str]
    controls: FrozenControls

    def __post_init__(self) -> None:
        """Copy holdout verdict mappings before scoring can read them."""
        object.__setattr__(self, "candidate_review_queue", tuple(self.candidate_review_queue))
        object.__setattr__(self, "current_verdicts", MappingProxyType(dict(self.current_verdicts)))
        object.__setattr__(self, "reference_verdicts", MappingProxyType(dict(self.reference_verdicts)))


@dataclass(frozen=True)
class PostCalibrationRun:
    """One immutable result from the untouched Post-Calibration Holdout."""

    candidate_digest: str
    metrics: AllocationMetrics


@dataclass(frozen=True)
class FrozenControls:
    """The configuration values that Calibration CI must hold fixed."""

    model_digest: str
    corpus_digest: str
    scorer_digest: str
    review_budget: int
    metrics_digest: str
    post_calibration_holdout_digest: str


@dataclass(frozen=True)
class SplitComparisonInput:
    """Frozen inputs for a prior-versus-candidate pack comparison."""

    split: str
    prior_review_queue: tuple[str, ...]
    candidate_review_queue: tuple[str, ...]
    current_verdicts: Mapping[str, str]
    reference_verdicts: Mapping[str, str]
    prior_controls: FrozenControls
    candidate_controls: FrozenControls

    def __post_init__(self) -> None:
        """Copy verdict mappings before the frozen comparison can use them."""
        object.__setattr__(self, "current_verdicts", MappingProxyType(dict(self.current_verdicts)))
        object.__setattr__(self, "reference_verdicts", MappingProxyType(dict(self.reference_verdicts)))


@dataclass(frozen=True)
class SplitComparison:
    """The independently scored metrics for one exposed corpus split."""

    split: str
    prior_metrics: AllocationMetrics
    candidate_metrics: AllocationMetrics

    @property
    def recall_improvement(self) -> float:
        """Return candidate Recall@4 minus prior Recall@4."""
        return self.candidate_metrics.recall_at_k - self.prior_metrics.recall_at_k


@dataclass(frozen=True)
class CalibrationCIReport:
    """The repeatable metric comparison for one Calibration Candidate."""

    candidate_digest: str
    controls: FrozenControls
    comparisons: tuple[SplitComparison, ...]
    regressions: tuple[BehavioralRegression, ...] = ()
    integrity_passed: bool = True
    trace_passed: bool = True
    reproducibility_passed: bool = True


@dataclass(frozen=True)
class BehavioralRegression:
    """One named behavioral or adversarial check for a candidate."""

    name: str
    passed: bool
    adversarial: bool = False


@dataclass(frozen=True)
class CalibrationGateResult:
    """The fail-closed Calibration CI decision before human review."""

    accepted: bool
    failure_reasons: tuple[str, ...]
    candidate_digest: str = ""


def evaluate_calibration_gate(
    report: CalibrationCIReport,
    regressions: Sequence[BehavioralRegression] | None = None,
) -> CalibrationGateResult:
    """Apply the fixed Recall@4, Precision@4, and regression claim gates."""
    bound_regressions = tuple(regressions) if regressions is not None else report.regressions
    failure_reasons: list[str] = []
    for comparison in report.comparisons:
        if comparison.recall_improvement < 0.20:
            failure_reasons.append(f"insufficient_recall_improvement:{comparison.split}")
        if comparison.candidate_metrics.precision_at_k < comparison.prior_metrics.precision_at_k:
            failure_reasons.append(f"precision_decrease:{comparison.split}")
    if not any(regression.adversarial for regression in bound_regressions):
        failure_reasons.append("adversarial_review_missing")
    if not report.integrity_passed:
        failure_reasons.append("integrity_check_failed")
    if not report.trace_passed:
        failure_reasons.append("trace_check_failed")
    if not report.reproducibility_passed:
        failure_reasons.append("reproducibility_check_failed")
    failure_reasons.extend(
        f"named_behavioral_regression:{regression.name}"
        for regression in bound_regressions
        if not regression.passed
    )
    result = CalibrationGateResult(
        not failure_reasons, tuple(failure_reasons), report.candidate_digest
    )
    if id(report) in _ISSUED_REPORT_IDS and bound_regressions == report.regressions:
        _ISSUED_GATE_RESULT_IDS.add(id(result))
    return result


def record_human_decision(
    history: CalibrationHistory,
    candidate: CalibrationCandidate,
    report: CalibrationCIReport,
    gate_result: CalibrationGateResult,
    promotion: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
) -> CalibrationHistory:
    """Append one authorized promotion or rejection after Calibration CI."""
    candidate_record = candidate.as_dict()
    candidate_digest = candidate.digest
    if candidate_digest not in {item.digest for item in history.candidates}:
        raise ValueError("Calibration Candidate is not in the append-only history")
    if any(decision.candidate_digest == candidate_digest for decision in history.decisions):
        raise ValueError("Calibration Candidate already has a human decision")
    if report.candidate_digest != candidate_digest:
        raise ValueError("Calibration CI report does not bind the candidate")
    if id(report) not in _ISSUED_REPORT_IDS:
        raise ValueError("Calibration CI report is not an issued immutable artifact")
    if (
        id(gate_result) not in _ISSUED_GATE_RESULT_IDS
        or gate_result.candidate_digest != candidate_digest
    ):
        raise ValueError("Calibration CI gate result must be issued for the candidate")
    validate_calibration_authority(promotion, reviewer_manifest)
    if promotion["candidate_digest"] != candidate_digest:
        raise ValueError("Calibration Promotion does not bind the candidate")
    if (
        promotion["predecessor_digest"] != candidate_record["predecessor_digest"]
        or promotion["rollback_target"] != candidate_record["rollback_target"]
    ):
        raise ValueError("Calibration Promotion does not preserve predecessor and rollback")
    if promotion["decision"] == "promote" and not gate_result.accepted:
        raise ValueError("Calibration CI must pass before human promotion")

    status = "promoted" if promotion["decision"] == "promote" else "rejected"
    pack = {
        "schema_version": "1.0",
        "pack_id": candidate_record["candidate_id"],
        "predecessor_digest": candidate_record["predecessor_digest"],
        "rollback_target": candidate_record["rollback_target"],
        "calibration_case_digests": candidate_record["calibration_case_digests"],
        "guideline_amendments": candidate_record["guideline_amendments"],
        "status": status,
    }
    pack["content_digest"] = content_digest(pack, excluded_keys={"content_digest"})
    validate_contract("calibration_pack", pack)
    decision = CalibrationDecision(
        candidate_digest=candidate_digest,
        status=status,
        removal_reason=str(promotion["rationale"]) if status == "rejected" else None,
        _pack_json=canonical_json(pack),
        _promotion_json=canonical_json(promotion),
    )
    history._CalibrationHistory__append_decision(decision)
    return history


def run_promoted_holdout_once(
    history: CalibrationHistory,
    candidate: CalibrationCandidate,
    report: CalibrationCIReport,
    holdout: PostCalibrationHoldoutInput,
) -> CalibrationHistory:
    """Run a promoted candidate once against the untouched Post-Calibration Holdout."""
    candidate_digest = candidate.digest
    decision = next(
        (item for item in history.decisions if item.candidate_digest == candidate_digest),
        None,
    )
    if decision is None or decision.status != "promoted":
        raise ValueError("Only an approved Calibration Candidate may run the holdout")
    if report.candidate_digest != candidate_digest or holdout.controls != report.controls:
        raise ValueError("Post-Calibration Holdout controls changed")
    if any(run.candidate_digest == candidate_digest for run in history.post_calibration_runs):
        raise ValueError("Post-Calibration Holdout already ran for this candidate")
    metrics = score_review_queue(
        review_queue=holdout.candidate_review_queue,
        current_verdicts=holdout.current_verdicts,
        reference_verdicts=holdout.reference_verdicts,
        review_budget=holdout.controls.review_budget,
    )
    history._CalibrationHistory__append_holdout_run(PostCalibrationRun(candidate_digest, metrics))
    return history


def compare_calibration_candidate(
    candidate: CalibrationCandidate,
    comparisons: Sequence[SplitComparisonInput],
    *,
    regressions: Sequence[BehavioralRegression] = (),
    integrity_passed: bool = True,
    trace_passed: bool = True,
    reproducibility_passed: bool = True,
) -> CalibrationCIReport:
    """Score prior and candidate packs on Development and Allocation Holdout."""
    if len(comparisons) != 2 or {comparison.split for comparison in comparisons} != {"DEV", "AH"}:
        raise ValueError("Calibration CI requires Development and Allocation Holdout comparisons")
    frozen_controls = comparisons[0].prior_controls
    results: list[SplitComparison] = []
    for comparison in comparisons:
        if (
            comparison.prior_controls != comparison.candidate_controls
            or comparison.prior_controls != frozen_controls
        ):
            raise ValueError("Calibration CI frozen controls changed")
        prior_metrics = score_review_queue(
            review_queue=comparison.prior_review_queue,
            current_verdicts=comparison.current_verdicts,
            reference_verdicts=comparison.reference_verdicts,
            review_budget=frozen_controls.review_budget,
        )
        candidate_metrics = score_review_queue(
            review_queue=comparison.candidate_review_queue,
            current_verdicts=comparison.current_verdicts,
            reference_verdicts=comparison.reference_verdicts,
            review_budget=frozen_controls.review_budget,
        )
        results.append(SplitComparison(comparison.split, prior_metrics, candidate_metrics))
    report = CalibrationCIReport(
        candidate.digest,
        frozen_controls,
        tuple(results),
        tuple(regressions),
        integrity_passed,
        trace_passed,
        reproducibility_passed,
    )
    _ISSUED_REPORT_IDS.add(id(report))
    return report


def create_calibration_candidate(
    *,
    candidate_id: str,
    authorized_adjudication: Mapping[str, Any],
    reviewer_manifest: Mapping[str, Any],
    predecessor_pack: Mapping[str, Any],
    guideline_amendments: Sequence[str],
    configuration_digests: Sequence[str],
) -> CalibrationCandidate:
    """Create one immutable candidate from an authorized correction Adjudication."""
    validate_adjudication_authority(authorized_adjudication, reviewer_manifest)
    if authorized_adjudication["action"] != "correct":
        raise ValueError("A Calibration Candidate requires a correcting Adjudication")
    validate_contract("calibration_pack", predecessor_pack)

    source_adjudication_digest = digest_contract("adjudication", authorized_adjudication)
    calibration_case = {
        "schema_version": "1.0",
        "case_id": authorized_adjudication["case_id"],
        "source_adjudication_digest": source_adjudication_digest,
        "prior_verdict": authorized_adjudication["prior_verdict"],
        "resulting_verdict": authorized_adjudication["resulting_verdict"],
        "rationale": authorized_adjudication["rationale"],
        "evidence_references": list(authorized_adjudication["evidence_references"]),
        "rubric_version": authorized_adjudication["rubric_version"],
    }
    calibration_case["content_digest"] = content_digest(
        calibration_case, excluded_keys={"content_digest"}
    )
    validate_contract("calibration_case", calibration_case)
    calibration_case_digest = digest_contract("calibration_case", calibration_case)

    predecessor_digest = str(predecessor_pack["content_digest"])
    record = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "predecessor_digest": predecessor_digest,
        "rollback_target": predecessor_digest,
        "source_adjudication_digests": [source_adjudication_digest],
        "calibration_case_digests": [calibration_case_digest],
        "guideline_amendments": list(guideline_amendments),
        "configuration_digests": list(configuration_digests),
        "status": "candidate",
        "nominator_id": authorized_adjudication["reviewer_id"],
        "nominator_role": "reviewer",
        "reviewer_manifest_version": reviewer_manifest["version"],
        "reviewer_manifest_digest": reviewer_manifest["content_digest"],
    }
    validate_calibration_authority(record, reviewer_manifest)
    return CalibrationCandidate(
        _record_json=canonical_json(record),
        source_adjudication_digest=source_adjudication_digest,
        calibration_case_digest=calibration_case_digest,
    )
