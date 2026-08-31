# Ticket 16 fixed-batch allocation

## Scope

This Offline Replay uses two frozen Development Split RankerCases.

The Review Budget is `K=1`.

The allocator made no model or network call.

The run used two accepted Case Assessments.

The receipt binds the canonical content digest of those two frozen RankerCases.

It also binds the Development Split membership and the offline allocator configuration.

The tracked input source is `tests/fixtures/ticket-16/fixed-batch-input.json`.

`test_recomputes_the_fixed_batch_allocation_receipt_from_tracked_input` recomputes every receipt binding and exact receipt from that source.

## Allocation result

| Queue position | Case identifier | Assessment status | Risk score | Deterministic score |
| --- | --- | --- | ---: | ---: |
| Selected | `EQ-F01-DEV-01` | `risk_finding` | 82 | 72 |
| First excluded | `EQ-F01-DEV-02` | `risk_finding` | 51 | 42 |

`EQ-F01-DEV-01` outranked `EQ-F01-DEV-02` at `risk_score`.

The preceding status fields match.

The deterministic score and case identifier remain exact ordering fields.

The canonical receipt is [fixed-batch-allocation-receipt.json](fixed-batch-allocation-receipt.json).

## Baselines and scoring

The implementation runs these fair baselines with the same Review Budget:

- seeded random;
- lowest confidence;
- disagreement only;
- deterministic only;
- oracle.

The canonical scorer recomputes Recall at K, Precision at K, false negatives, and oracle regret.

Recall at K is the sole primary ranking metric.

## TDD record

| Slice | RED command and result | GREEN command and result |
| --- | --- | --- |
| Case Assessment validation and retry | `uv run pytest -q tests/test_ranking.py` failed during collection because `edgequeue.allocation` did not exist. | The same command passed: `4 passed in 0.03s`. |
| Exact-K deterministic ordering | `uv run pytest -q tests/test_ranking.py::test_create_review_queue_rejects_duplicate_unknown_and_wrong_budget_cases` failed because `InvalidReviewBatch` did not exist. | `uv run pytest -q tests/test_ranking.py` passed: `5 passed in 0.03s`. |
| Fair baselines | `uv run pytest -q tests/test_baselines.py::test_runs_five_fair_baselines_with_one_review_budget` failed because `allocate_fair_baselines` did not exist. | `uv run pytest -q tests/test_baselines.py` passed: `5 passed in 0.01s`. |
| Primary metric | `uv run pytest -q tests/test_scoring.py::test_declares_recall_at_k_as_the_only_primary_ranking_metric` failed because `PRIMARY_RANKING_METRIC` did not exist. | `uv run pytest -q tests/test_scoring.py` passed: `5 passed in 0.01s`. |
| Receipt and boundary explanation | `uv run pytest -q tests/test_ranking.py::test_binds_all_assessments_and_explains_the_first_excluded_case` failed because `allocate_review_queue` did not exist. | `uv run pytest -q tests/test_ranking.py` passed: `6 passed in 0.03s`. |
| Retry immutability and invalid disposition | `uv run pytest -q tests/test_ranking.py::test_retries_one_identical_execution_failure_then_invalidates_second tests/test_ranking.py::test_retries_a_schema_failure_then_accepts_the_second_assessment tests/test_ranking.py::test_accepts_an_agent_abstention_for_one_ranker_case` failed: `AssessmentBatchRun` had no `disposition`. | `uv run pytest -q tests/test_ranking.py` passed: `8 passed in 0.04s`. |
| EvaluationRun invalidation | `uv run pytest -q tests/test_ranking.py::test_marks_the_evaluation_run_invalid_and_preserves_remaining_batch_state` failed because `invalidate_evaluation_run` did not exist. | `uv run pytest -q tests/test_ranking.py` passed: `9 passed in 0.05s`. |
| Tracked receipt derivation | `uv run pytest -q tests/test_ranking.py::test_recomputes_the_fixed_batch_allocation_receipt_from_tracked_input` failed because the receipt assessment digests used an earlier output-digest source. | The same command passed: `1 passed in 0.02s`. |

Derivation command: `uv run pytest -q tests/test_ranking.py::test_recomputes_the_fixed_batch_allocation_receipt_from_tracked_input`.

The Ticket 16 focused check passed: `20 passed in 0.06s`.

The complete required suite passed: `105 passed in 2.23s`.

## Run records

| Field | Value |
| --- | --- |
| Runtime | 0.06 seconds for the Ticket 16 focused check. 2.23 seconds for the required suite. |
| Request count | 0 |
| Token count | 0 |
| Available cost | 0 |
| Failure records | RED results shown above. No final focused-test failure. |

The frozen v1 Case Assessment contract rejects execution-failure retries inside an accepted assessment record.

The allocation runner therefore preserves retry outcomes separately and invalidates a run after the second failure.
