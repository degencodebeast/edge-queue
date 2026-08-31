# Improvement Changelog

This file records material changes to EdgeQueue. Each entry names the evidence that guided the next decision.

## 2026-08-31 — Shared contract spine

**Change.** Added versioned, fail-closed contracts for corpus records, Case Assessments, EvaluationRuns, Allocation Receipts, Adjudications, Calibration records, Proof Bundles, Claims, and Verification results. Added canonical UTF-8 JSON serialization, declared timestamp exclusion, named verification failures, and frozen `judge`, `adjudicate`, and `verify` command help interfaces.

**Why.** Parallel EdgeQueue slices need one authority for fields, versions, serialization, and failure names.

**Evidence.** `docs/evidence/ticket-14/contract-validation.md` records RED-GREEN commands, the independent digest vector, 25 versioned schema files, packaged-schema wheel verification, CLI help checks, and the full `85 passed` suite.

**Decision.** Later slices must use schema version `1.0` and must not add fields without a schema-version change.

## 2026-08-31 — Baseline contract

**Change.** Defined three fair baseline allocators. They select lowest confidence, evaluator disagreement, and deterministic risk. The prototype also includes an oracle ceiling and seeded random allocation.

**Why.** The challenge requires a meaningful comparison against a reasonable basic solution on the same cases and budget.

**Evidence.** `tests/test_baselines.py` and `tests/test_experiment.py` run each allocator against the same case identifiers and review budget.

**Decision.** Keep all non-oracle baselines. Do not use the oracle as a comparison baseline.

## 2026-08-31 — Canonical scoring

**Change.** Added a canonical scorer for label-error `Recall@K`, `Precision@K`, false negatives, and oracle regret.

**Why.** Allocator explanations cannot prove ranking quality. The scorer must calculate metrics from frozen current and Reference Verdicts.

**Evidence.** `tests/test_scoring.py` rejects duplicate, unknown, and wrong-cardinality Review Queues.

**Decision.** All public metrics must come from an EvaluationRun. No README or video claim may use a hand-calculated value.

## 2026-08-31 — Corpus integrity and scorer isolation

**Change.** Added canonical SHA-256 content digests. Split allocator-visible RankerCase data from scorer-only ScorerCase data.

**Why.** The Allocation Holdout needs a trustworthy boundary. A scorer-only Reference Verdict must not enter allocator context.

**Evidence.** `tests/test_digests.py` uses an independent SHA-256 vector. `tests/test_experiment.py` requires separate ranker and scorer records. `tests/test_integrity.py` detects forbidden scorer content.

**Decision.** Use per-case sentinels and reject an EvaluationRun when they appear in allocator artifacts.

## 2026-08-31 — Structured allocator smoke test

**Change.** Tested the Case Assessment prompt against one realistic missing-verification case.

**Why.** The agent must return structured evidence that relates to the current Verdict.

**Evidence.** `prototype/smoke/case-assessment-output-luna-low.json` records a valid Risk Finding. `schemas/case-assessment.schema.json` defines the required response.

**Decision.** Preserve the prompt, output schema, model configuration, JSONL events, and final response for every submitted agent run.

## 2026-08-31 — First isolated corpus case

**Change.** Added `EQ-F01-DEV-01` as a RankerCase and a separate ScorerCase.

**Why.** The case tests whether an evaluator can distinguish missing verification from evidence of failure.

**Evidence.** `tests/test_corpus.py` verifies the frozen verdict transition and checks that the RankerCase excludes scorer-only fields.

**Decision.** Expand the Development Split only after this boundary passes.

## 2026-08-31 — Fixed-budget ranking falsification

**Change.** Ran the Development Split once and the 40-case Allocation Holdout three times. Each run used the same Review Budget and the same canonical scorer.

**Why.** The project must prove that its semantic allocator recovers more hidden Label Errors than simple signal-based queues.

**Evidence.** `runs/development/evaluation.json` reports Development Recall@4 of `0.80`. `runs/allocation-holdout/evaluation.json` reports Holdout Recall@8 of `0.80` in all three runs. The strongest simple baseline scored `0.00`. Random p95 scored `0.40`. `scripts/check_holdout_leakage.py` scanned 600 Holdout trace files and found no scorer-only field or sentinel.

**Decision.** Proceed with the scoped claim: on the frozen synthetic corpus, EdgeQueue recovered more Label Errors than the defined simple baselines under the same fixed budget. Do not claim that this result generalizes to all production evaluation workflows.

## Current limitation

The Post-Calibration Holdout and the final clean-room verification are not complete. The project must not claim a calibration improvement until those checks pass.
