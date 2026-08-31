# Ticket 20 evidence

This directory records a frozen-synthetic-corpus EvaluationRun.

The claim has one scope. It reports Allocation Holdout Recall at 8.

The fixture does not establish production performance or Calibration Promotion.

Development derives from 20 current-frozen traces under `development-traces/`
and `development-allocation-receipt.json`.

Allocation Holdout derives from 120 current-frozen traces under
`frozen-traces/` and three Allocation Receipts under `allocation-receipts/`.

The trace manifest binds 20 fresh Development traces and all 120 fresh
Allocation Holdout traces.

Fresh Recall at 8 was 0.30, 0.40, and 0.30 for attempts 1, 2, and 3.

Fresh Development Recall at 4 was 0.20.

Each trace records its runtime, request count, token use, and available cost.
