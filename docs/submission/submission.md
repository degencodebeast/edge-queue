# Copy-ready micro1 submission

## Title

EdgeQueue — find wrong agent verdicts before expert review time runs out

## Description

Evaluation Operations Leads can receive more agent trajectory verdicts than qualified reviewers can inspect. EdgeQueue treats expert attention as a fixed Review Budget. It ranks likely Label Errors from evidence, then lets deterministic code validate the evidence and order the queue. An authorized human remains the only actor who can correct a canonical Verdict.

The simple baseline selects cases through deterministic warning signals. The advanced workflow adds evidence-linked Case Assessments, scorer isolation, deterministic queue authority, append-only human Adjudications, and an offline Proof Bundle that recomputes metrics and rejects a repaired-digest tamper.

The short Judge Fixture is a four-case Development example. Under `K=1`, EdgeQueue gets Recall@1 `1.00`; the deterministic baseline gets `0.00`. This illustrates the full flow without claiming broad performance. The separate frozen-synthetic Allocation Holdout public claim is Recall@8 `0.30`. It does not establish production performance, Calibration Promotion, or calibration improvement.

The project uses synthetic data and simulated actions. Production use requires qualified reviewers and approved data.

GitHub: https://github.com/degencodebeast/edge-queue

Video URL: **Required before submission. Add the uploaded video URL here.**

Evidence: `docs/evidence/ticket-20/claims.json`, `docs/evidence/ticket-21/artifacts/proof-bundle/claims.json`, and `docs/trajectories/trace-manifest.json`.
