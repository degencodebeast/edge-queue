# Ticket 19 Calibration CI report

This offline report uses `tests/fixtures/ticket-19/calibration-input.json`.

## Frozen controls

- Model digest: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Corpus digest: `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- Scorer digest: `cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc`
- Review Budget: `4`
- Metrics digest: `dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd`
- Post-Calibration Holdout digest: `eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee`

## Accepted candidate record

- Candidate: `candidate-ticket-19-evidence-accepted`
- Candidate digest: `3a5d2a249be1b762e57034f7c723c3e319412a484e6e0d8627b30aa8a98c593c`
- Source Adjudication digest: `be44211a04b2cec26e317ac6453e04aa54fe070cef8b107e0ada95e6065a43dd`
- Calibration Case digest: `41083f27ef0c848e09d3ca75231190a352289f46b918933a0b94f3de94970ed4`
- Predecessor and rollback digest: `2d26ea6e026e957eb9278b40675453beb4e483bb7e62aec4859517ba89e042b4`
- Nominator: authorized `human-reviewer` with the `reviewer` role.
- Promotion: authorized `human-promoter` with the `calibration_promoter` role.
- Named adversarial regression: `adversarial-signal-gaming` passed.

| Split | Prior Recall@4 | Candidate Recall@4 | Prior Precision@4 | Candidate Precision@4 |
| --- | ---: | ---: | ---: | ---: |
| Development | 0.50 | 1.00 | 0.25 | 0.50 |
| Allocation Holdout | 0.50 | 1.00 | 0.25 | 0.50 |

The candidate improved Recall@4 by `0.50` on each exposed split. Precision@4 did not decrease.

The promoted candidate ran once on the Post-Calibration Holdout. It produced Recall@4 `1.00`, Precision@4 `0.50`, no false negatives, and oracle regret `0`.

## Rejected candidate record

- Candidate: `candidate-ticket-19-evidence-rejected`
- Candidate digest: `a957f87bfabc7713b97a01a04ec624cbef1ae46d81c7f83ed737188d447dda51`
- Source and predecessor records match the accepted fixture record.
- Authorized human decision: reject.
- Failure: `named_behavioral_regression:adversarial-signal-gaming`.
- Removal reason: `Removed after the named behavioral regression.`

The rejected Calibration Pack remains in the append-only history. It cannot be promoted.

## Execution record

- Execution mode: offline deterministic fixture.
- Model requests: `0`.
- Tokens: `0`.
- Cost: `0`.
- Network calls: `0`.
