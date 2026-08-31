# Engineering workflow

## Purpose

This document explains how EdgeQueue work becomes submission evidence.

## Build loop

1. Write one test at an agreed public seam.
2. Run the test and record the RED result.
3. Add the smallest code change that makes the test pass.
4. Run the focused test and the full test suite.
5. Add the change and its evidence to `IMPROVEMENT_CHANGELOG.md`.

## Evaluation loop

1. Freeze RankerCase and ScorerCase digests.
2. Run each allocator with the same case identifiers and review budget.
3. Use the canonical scorer to calculate all metrics.
4. Preserve failed runs, retries, and invalid runs.
5. Reject scorer leakage before metric calculation.

## Trace loop

For every submitted agent, preserve:

- agent instructions and output schema;
- JSONL event trace with tool responses;
- final structured output;
- model name, configuration, runtime, request count, tokens, and cost;
- retry records and human checkpoints.

The final submission will link each public claim to a frozen EvaluationRun artifact.
