# EdgeQueue

**Find wrong agent verdicts before expert review time runs out.**

EdgeQueue helps evaluation teams decide which AI-agent verdicts to review when expert time is limited.

```text
4 agent verdicts
1 hidden Label Error
1 review slot
```

In this demo, both methods rank the same four cases without seeing the correct answers. The baseline spends its review slot on the wrong case. EdgeQueue sends the hidden Label Error to the reviewer.

[Run the Judge](#judge-it-in-90-seconds) · [Open the Review Packet](docs/evidence/ticket-21/artifacts/review-packet.html) · [See the results](#measured-results) · [Reproduce the evidence](REPRODUCTION.md) · [Read the changelog](IMPROVEMENT_CHANGELOG.md)

Repository: <https://github.com/degencodebeast/edge-queue>

## The problem

Reviewing every agent verdict is often too slow. Random selection can waste a review slot. Confidence-only selection can miss a verdict that is confidently wrong.

The ranking system must work without seeing hidden reference answers. It must obey the Review Budget, and it must leave every official Verdict change to a human reviewer.

## What EdgeQueue does

EdgeQueue follows one review path:

1. Give every ranking method the same frozen cases and Review Budget.
2. Show the ranking agent the case evidence, but never the correct answers.
3. Check every finding with deterministic code and fill only the available review slots.
4. Show the reviewer why each case was selected and which case fell just outside the queue.
5. Record the human correction without rewriting the original record.
6. Package the cases, decisions, and metrics so anyone can verify them later.

The ranking agent can flag a risk. Deterministic code builds the queue. Only an authorized human can change the official Verdict.

## Judge it in 90 seconds

Requirements: Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/degencodebeast/edge-queue
cd edge-queue
uv sync --frozen
UV_OFFLINE=1 uv run edgequeue judge --output-dir /tmp/edgequeue-judge
UV_OFFLINE=1 uv run edgequeue verify /tmp/edgequeue-judge/proof-bundle
```

Expected result:

```text
Baseline deterministic_only: EQ-F02-DEV-01
EdgeQueue: EQ-F01-DEV-01
Primary Recall@1: baseline=0.00 EdgeQueue=1.00
Calibration Candidate: accepted; not promoted; no PCH claim
Proof Bundle: valid
Tamper result: metric_recomputation_mismatch
Offline Replay: about 0.057s, requests=0, tokens=0, model_cost=$0.00
```

This path uses a committed synthetic fixture. It makes no network or model call. Its full evidence is in [`docs/evidence/ticket-21/artifacts/`](docs/evidence/ticket-21/artifacts/).

The baseline misses the hidden error while EdgeQueue sends it to review. The generated Proof Bundle passes verification. The command also checks an altered copy and rejects it because the saved score no longer matches the cases.

The calibration line records a candidate that passed its initial checks. EdgeQueue did not promote that candidate or claim that it improved the wider results. `No PCH claim` means that EdgeQueue did not run a Post-Calibration Holdout.

## What the reviewer sees

The generated [Review Packet](docs/evidence/ticket-21/artifacts/review-packet.html) shows:

- how many cases the reviewer can inspect;
- the selected case and its evidence;
- its score under the fixed rules;
- why it was selected;
- which case fell just outside the queue;
- the human correction.

In the Judge Fixture, EdgeQueue selects `EQ-F01-DEV-01`. The reviewer changes its official Verdict from `FAIL` to `UNDETERMINED`. EdgeQueue appends the correction and links it to the evidence instead of rewriting the earlier record.

## Measured results

The four-case demo proves that the complete review and verification path works. It does not prove that EdgeQueue ranks better in general. The larger evaluation did not show a reliable improvement over the strongest baseline.

| Evaluation | Cases | Budget | Baseline | EdgeQueue | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Judge Fixture, Development | 4 | `K=1` | Recall@1 `0.00` | Recall@1 `1.00` | Illustrative workflow proof |
| Fresh Development | 20 | `K=4` | Strongest baseline Recall@4 `0.60` | Recall@4 `0.20` | No improvement claim |
| Allocation Holdout, three frozen attempts | 40 | `K=8` | Strongest baseline Recall@8 `0.30` | `0.30`, `0.40`, `0.30` | Broad gate rejected |

The public Allocation Holdout claim is Recall@8 `0.30`, the worst result across three frozen attempts. The mean is `0.333`. The strongest deterministic baseline is `0.30`, and seeded random Recall@8 p95 is `0.40`. The broad gate therefore rejects a general improvement claim.

Evidence behind these results:

- [Judge Fixture summary](docs/evidence/ticket-21/artifacts/summary.json)
- [Allocation Holdout claim](docs/evidence/ticket-20/claims.json)
- [Claims Manifest](docs/evidence/ticket-20/claims-manifest.json)
- [Fresh frozen evaluation evidence](docs/evidence/ticket-20/README.md)

## How it works

```mermaid
flowchart LR
    A[Frozen RankerCases] --> B[Evidence-linked Case Assessments]
    B --> C[Deterministic validation and scoring]
    C --> D[Review Budget and ordered Review Queue]
    D --> E[Human Review Packet]
    E --> F[Append-only Adjudication]
    F --> G[Claims and Proof Bundle]
    H[Hidden ScorerCases] --> I[Metric recomputation]
    D --> I
    I --> G
```

`RankerCase` records contain only evidence that the allocator can see. `ScorerCase` records contain hidden Reference Verdicts and scorer sentinels. Validation prevents hidden labels from reaching the allocator.

Case Assessments are non-authoritative. Deterministic code validates their schema, binds them to frozen content, applies the scoring policy, enforces exactly `K` unique known cases, and creates the Allocation Receipt.

The Proof Bundle does not trust saved metrics. Offline verification recomputes bindings and metrics. A hostile bundle with a changed Recall value and repaired file digest still fails with `metric_recomputation_mismatch`.

## What changed during the hackathon

| Iteration | What changed | Outcome |
| --- | --- | --- |
| Fixed-budget baselines | Added fair same-case, same-budget comparators | Established the baseline contract |
| Semantic ranking | Added evidence-linked findings and abstention | Kept semantic judgment without giving it queue authority |
| Scorer isolation | Split allocator-visible and hidden scoring records | Prevented labels from steering allocation |
| Human authority | Added append-only Adjudications | Kept canonical corrections under reviewer control |
| Proof verification | Added content bindings and metric recomputation | Rejected repaired-digest tampering |
| Frozen rerun | Replaced an invalid broad `0.80` result | Published `0.30` and rejected the broad gate |

The frozen rerun removed a reported `0.80` result because its trace inputs did not bind to the final RankerCases. The correction remains documented in [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md).

## Reproduce the evaluation

```sh
UV_OFFLINE=1 uv run python scripts/score_development.py
UV_OFFLINE=1 uv run python scripts/score_allocation_holdout.py
UV_OFFLINE=1 uv run python scripts/check_holdout_leakage.py
uv run pytest -q
```

Expected checkpoints:

- Development EdgeQueue Recall@4: `0.20`.
- Holdout attempts: `0.30`, `0.40`, and `0.30`.
- Holdout decision: `reject`.
- Leakage scan: `checked_files=600 leakage=none`.
- Test suite: `176 passed` in the verified environment.

See [REPRODUCTION.md](REPRODUCTION.md) for setup, runtime, cost, and release-archive commands.

## Technical overview

- Python 3.11 or newer.
- No runtime dependencies.
- `pytest` for verification.
- Versioned JSON Schemas packaged with the wheel.
- Canonical UTF-8 JSON and SHA-256 content digests.
- Offline `judge`, `adjudicate`, and `verify` commands.
- Deterministic ZIP creation with an external SHA-256 sidecar.

```text
src/edgequeue/          allocation, adjudication, proof, and verification code
schemas/                versioned public contracts
corpus/                 frozen synthetic corpus and Judge Fixture
scripts/                evaluation, privacy, trajectory, and release commands
tests/                  contract, public-seam, and submission tests
docs/evidence/          content-bound run and review evidence
docs/trajectories/      redacted Controller, Worker, Gate, and review traces
docs/submission/        copy-ready submission and video plan
```

## Evidence and limits

| Boundary | Status |
| --- | --- |
| Data | Synthetic only |
| Default execution | Credential-free and offline |
| Model calls in Judge Fixture | 0 requests, 0 tokens, `$0.00` model cost |
| Calibration Candidate | Accepted, not promoted |
| Post-Calibration Holdout | Not run |
| Broad improvement claim | Rejected |
| Production-generality claim | Not made |
| Canonical Verdict changes | Authorized human only |

Production use requires qualified reviewers, approved data, and a separately validated live provider path.

## Submission evidence

- [Reproduction guide](REPRODUCTION.md)
- [Improvement Changelog](IMPROVEMENT_CHANGELOG.md)
- [Pre-existing work and provenance](PREEXISTING.md)
- [Copy-ready submission](docs/submission/submission.md)
- [Video script and capture plan](docs/submission/video-production.md)
- [Redacted agent trajectory manifest](docs/trajectories/trace-manifest.json)
- [Submission-readiness report](docs/evidence/ticket-22/submission-readiness.md)
- [Pre-release qualification report](docs/evidence/ticket-23/pre-release-qualification.md)

To inspect EdgeQueue, run the 90-second Judge Fixture, open its Review Packet, and verify the generated Proof Bundle.
