# Pre-existing work and provenance

## Before this competition

- Research and workflow references in `docs/research/` and `sample_projects/` informed presentation choices. They were not copied into EdgeQueue.
- Python, `uv`, Git, pytest, and Codex CLI were existing tools.
- No starter application, model weights, or template code was reused.

## Competition additions

The contracts, frozen synthetic corpus, allocator, review workflow, Proof Bundle, Judge Fixture, evidence, submission documents, archive tool, and trajectory exports were added for this project.

## Dependencies and licences

| Component | Use | Licence or terms |
| --- | --- | --- |
| Python standard library | CLI, archive, JSON, hashing | PSF licence |
| uv | reproducible environment management | MIT or Apache-2.0 |
| pytest | tests | MIT |
| Git | source control and exact-SHA archive input | GPL-2.0-only |
| Codex CLI | coding-agent work and preserved trajectories | OpenAI service terms |

`pyproject.toml` declares no runtime package dependency. The repository contains no model weights.

## Data and model provenance

The corpus contains synthetic Trajectory Evaluations created by the versioned compiler and frozen under `corpus/`. The default Judge Fixture replays committed outputs. It makes zero model requests and has `$0.00` offline model cost.

No private production trajectory, credential, or personal decision record belongs in this submission. See [`docs/trajectories/trace-manifest.json`](docs/trajectories/trace-manifest.json) for redacted agent-trace provenance.

## Legacy archive exclusions

Ticket 22 preserves frozen legacy records without rewriting them. The source archive excludes only `runs/**` and `docs/evidence/ticket-20/traces/**` because those historical records contain local home paths.

The archive retains current authoritative proof under `docs/evidence/ticket-20/development-traces/`, `docs/evidence/ticket-20/frozen-traces/`, `docs/evidence/ticket-20/allocation-receipts/`, `docs/evidence/ticket-20/evaluation-run.json`, `docs/evidence/ticket-20/evaluation-results.json`, `docs/evidence/ticket-20/claims.json`, and all Ticket 21 proof and video assets.
