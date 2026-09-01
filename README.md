# EdgeQueue

EdgeQueue helps an Evaluation Operations Lead spend a fixed Review Budget on agent verdicts most likely to be wrong. It creates an evidence-linked Review Queue. An authorized human owns every correction.

Repository: <https://github.com/degencodebeast/edge-queue>

## 90-second judge path

```sh
git clone https://github.com/degencodebeast/edge-queue
cd edge-queue
uv sync --frozen
UV_OFFLINE=1 uv run edgequeue judge --output-dir /tmp/edgequeue-judge
UV_OFFLINE=1 uv run edgequeue verify /tmp/edgequeue-judge/proof-bundle
```

Expected output:

```text
Baseline deterministic_only: EQ-F02-DEV-01
EdgeQueue: EQ-F01-DEV-01
Primary Recall@1: baseline=0.00 EdgeQueue=1.00
Calibration Candidate: accepted; not promoted; no PCH claim
Proof Bundle: valid
Tamper result: metric_recomputation_mismatch
Offline Replay: about 0.057s, requests=0, tokens=0, model_cost=$0.00
```

The command uses a committed synthetic fixture. It makes no network or model call. See [`docs/evidence/ticket-21/artifacts/`](docs/evidence/ticket-21/artifacts/).

## User, bottleneck, and boundary

An Evaluation Operations Lead may have more Trajectory Evaluations than qualified reviewers can inspect. Reviewing every case is too slow. Reviewing only low-confidence cases can miss confident Label Errors.

EdgeQueue ranks likely Label Errors from allocator-visible evidence. Deterministic code validates evidence, orders cases, and enforces the Review Budget. Only an authorized human Adjudication can change a canonical Verdict.

The proof uses synthetic data and simulated actions. It does not support a production claim. Production use requires qualified reviewers and approved data.

## Baseline and advanced solution

The simple baseline is `deterministic_only`. It selects one case from the same four-case fixture using deterministic warning signals. The advanced solution uses an evidence-linked Case Assessment, then deterministic validation and ordering.

Run the realistic end-to-end comparison:

```sh
UV_OFFLINE=1 uv run edgequeue judge --output-dir /tmp/edgequeue-judge
cat /tmp/edgequeue-judge/command-output.txt
```

The Judge Fixture is illustrative only. It is a four-case Development fixture with `K=1`: EdgeQueue Recall@1 is `1.00`; the deterministic baseline is `0.00`. Its authoritative sources are [`claims.json`](docs/evidence/ticket-21/artifacts/proof-bundle/claims.json), [`claims-manifest.json`](docs/evidence/ticket-21/artifacts/proof-bundle/claims-manifest.json), and [`summary.json`](docs/evidence/ticket-21/artifacts/summary.json).

The broad result is separate. On the frozen synthetic Allocation Holdout, EdgeQueue recovered Recall@8 `0.30`. This narrow result does not establish production performance or Calibration Promotion. Its sole public source is [`docs/evidence/ticket-20/claims.json`](docs/evidence/ticket-20/claims.json), bound by its [Claims Manifest](docs/evidence/ticket-20/claims-manifest.json).

## Evaluation and proof

```sh
UV_OFFLINE=1 uv run python scripts/score_development.py
UV_OFFLINE=1 uv run python scripts/score_allocation_holdout.py
UV_OFFLINE=1 uv run python scripts/check_holdout_leakage.py
```

These commands use frozen traces. They are not live model runs. See [REPRODUCTION.md](REPRODUCTION.md) for data, output, runtime, and cost.

The fixture reports a Calibration Candidate that passed its candidate gate. It was not promoted. The Post-Calibration Holdout was not run. EdgeQueue does not claim calibration improvement.

## Main failure mode and hot take

The main failure was corpus drift. Frozen reruns disproved the previous `0.80` holdout result. The corrected public result is `0.30`; the removed result remains documented in [IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md).

Hot take: confidence is not a review policy. Teams should measure how they allocate human attention, then require evidence before an agent recommendation can affect a person.

## Submission package

- [Reproduction guide](REPRODUCTION.md)
- [Improvement Changelog](IMPROVEMENT_CHANGELOG.md)
- [Pre-existing work and provenance](PREEXISTING.md)
- [Copy-ready submission](docs/submission/submission.md)
- [Video script and capture plan](docs/submission/video-production.md)
- [Redacted agent trajectories](docs/trajectories/trace-manifest.json)
- [Submission-readiness report](docs/evidence/ticket-22/submission-readiness.md)
