# Ticket 20 evidence

This directory records a frozen-synthetic-corpus EvaluationRun.

The claim has one scope. It reports Allocation Holdout Recall at 8.

The fixture does not establish production performance or Calibration Promotion.

Development derives from `runs/development/evaluation.json`.

Allocation Holdout derives from 120 current-frozen traces under
`frozen-traces/` and three Allocation Receipts under `allocation-receipts/`.

The trace manifest binds all 40 cases and all three fresh attempts.

Fresh Recall at 8 was 0.30, 0.40, and 0.30 for attempts 1, 2, and 3.

Each trace records its runtime, request count, token use, and available cost.
