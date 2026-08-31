# Reproduction guide

## Requirements

- macOS or Linux with Git.
- Python 3.11 or newer.
- `uv`.
- No provider credential or network access for the default path.

Recorded verification environment: Python `3.14.4`, uv `0.11.6`, and Git `2.52.0`. The project supports Python 3.11 or newer.

## Clean setup

```sh
git clone https://github.com/degencodebeast/edge-queue
cd edge-queue
uv sync --frozen
```

The committed synthetic corpus supplies all required data. Do not add private trajectories or credentials.

## Baseline and advanced solution

```sh
UV_OFFLINE=1 uv run edgequeue judge --output-dir /tmp/edgequeue-judge
cat /tmp/edgequeue-judge/command-output.txt
```

The output compares the deterministic baseline and EdgeQueue on four Development cases under a Review Budget of one. Expect baseline Recall@1 `0.00` and EdgeQueue Recall@1 `1.00`.

## Evaluation and proof

```sh
UV_OFFLINE=1 uv run python scripts/score_development.py
UV_OFFLINE=1 uv run python scripts/score_allocation_holdout.py
UV_OFFLINE=1 uv run python scripts/check_holdout_leakage.py
UV_OFFLINE=1 uv run edgequeue verify /tmp/edgequeue-judge/proof-bundle
```

The broad public claim comes only from `docs/evidence/ticket-20/claims.json`: frozen-synthetic Allocation Holdout Recall@8 `0.30`. The four-case Judge Fixture is separate and illustrative.

## Expected runtime and cost

The recorded offline Judge Fixture took about `0.057` seconds. It made zero requests, used zero tokens, and incurred `$0.00` model cost. Runtime will vary by machine. The default workflow is offline and uses no model service.

## Archive a reviewed commit

Run this outside the repository. Replace the SHA only with the reviewed candidate SHA.

```sh
uv run python scripts/build_release.py --sha <40-character-candidate-sha> --output-dir /tmp/edgequeue-release
```

The command writes a ZIP and an external SHA-256 sidecar. It uses tracked blobs from that exact SHA, excludes Git metadata, environments, caches, bytecode, `.env`, and build outputs, and rejects archives above 50 MB.
