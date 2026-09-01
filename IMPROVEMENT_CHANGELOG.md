# Improvement Changelog

This record preserves successful, failed, and removed experiments. Every public result has an evidence link.

## Baseline — fair fixed-budget queues

**Tried.** Lowest confidence, evaluator disagreement, deterministic risk, seeded random, and an oracle ceiling.

**Why.** The advanced solution needed fair same-case, same-budget comparators.

**Evidence.** [`tests/test_baselines.py`](tests/test_baselines.py) and [`tests/test_experiment.py`](tests/test_experiment.py).

**Decision.** Keep the non-oracle baselines. Use Recall@K as the primary ranking metric.

## Evidence-linked semantic ranking

**Tried.** One Case Assessment per RankerCase, with an agent risk finding or abstention.

**Why.** Simple signals cannot explain evidence contradictions.

**Evidence.** [`docs/evidence/ticket-16/fixed-batch-allocation.md`](docs/evidence/ticket-16/fixed-batch-allocation.md).

**Decision.** Keep semantic judgment. Keep validation, order, and budget enforcement deterministic.

## Scorer isolation and human authority

**Tried.** Separate RankerCase and ScorerCase records, scorer sentinels, append-only Adjudications, and an offline Proof Bundle.

**Why.** Hidden Reference Verdicts must not steer allocation. Agents must not correct people automatically.

**Evidence.** [`docs/evidence/ticket-17/`](docs/evidence/ticket-17/) and the frozen Proof Bundle verification reports.

**Decision.** Reject scorer leakage. Require an authorized human Adjudication for every canonical correction.

## Removed experiment — the previous 0.80 holdout result

**Tried.** Earlier traces reported Allocation Holdout Recall@8 `0.80`.

**Failure.** Authoritative frozen reruns disproved it. The earlier trace inputs did not bind to the final frozen RankerCases.

**Evidence.** [`docs/evidence/ticket-20/README.md`](docs/evidence/ticket-20/README.md) records fresh frozen runs at `0.30`, `0.40`, and `0.30`. The authoritative public claim is [`docs/evidence/ticket-20/claims.json`](docs/evidence/ticket-20/claims.json): Recall@8 `0.30`.

**Decision.** Remove every stale broad `0.80` public claim. Preserve the failure. Do not tune against revealed holdout labels.

## Judge Fixture — end-to-end proof

**Tried.** A four-case Development Judge Fixture with one confident Label Error and one misleading hard control.

**Evidence.** [`docs/evidence/ticket-21/artifacts/summary.json`](docs/evidence/ticket-21/artifacts/summary.json) and [`video-data.json`](docs/evidence/ticket-21/artifacts/video-data.json) record EdgeQueue Recall@1 `1.00` versus deterministic baseline `0.00`.

**Decision.** Use this fixture only as an illustration. Keep it separate from the broad holdout result.

## Calibration limit and next action

The candidate gate accepted the Calibration Candidate. It was not promoted. PCH was not run. Do not claim calibration improvement.

Ticket 23 must verify the draft archive from a clean environment. The final uploader must add the uploaded video URL without changing evidence claims.
