# Ticket 15 corpus freeze

Date: 2026-08-31

Base SHA: `f9b3d0c2ec6eb78b54d82bbeec3cb0da743f034b`

## Freeze command

```sh
uv run python -c 'from pathlib import Path; from edgequeue.corpus import freeze_complete_corpus; frozen = freeze_complete_corpus(Path("corpus")); print(frozen.root_manifest["root_corpus_digest"])'
```

Immutable corpus version: `1.0.0`

Root Corpus Digest: `ff509d989d9b2de1602528fc2b8c6a8d857786cc8b2c0c98456975c433c3ff61`

## Schema versions

- `case-specification`: `1.0`
- `trajectory-event`: `1.0`
- `frozen-initial-evaluation`: `1.0`
- `shadow-evaluation`: `1.0`
- `ranker-case`: `1.0`
- `scorer-case`: `1.0`
- `evaluator-manifest`: `1.0`
- `authoring-ledger`: `1.0`
- `split-manifest`: `1.0`
- `corpus-manifest`: `1.0`

## Freeze results

- Cases: `80`.
- Development Split: `20` cases.
- Allocation Holdout: `40` cases.
- Post-Calibration Holdout: `20` cases.
- Label Errors: `20`.
- Hard Controls: `10`.
- Reference Audit: `20` resolved samples.
- RankerCase files: `80` in the ranker-only tree.
- ScorerCase files: `80` in the scorer-only tree.
- Scorer Sentinels: `80` unique values.
- Judge Fixture: `corpus/fixtures/judge-fixture-v1.json` contains four frozen Allocation Holdout cases.
- Split Manifest Digests: `e0531d96c0a8b8d96233f4dcac9ce9b3383db87d0d9ac101c746b766dfc8b46a`, `04f63e41d339bc2bc3cdda86a74c5cf8b9c8a60034dfbc2556d50893ab9813e3`, and `1a04cf98c5f772427160bc9cf50237a77f31b804f029ded7be139d87b3824c71`.

The compiler validates each record before its digest calculation. It validates stable split order and uniqueness. It binds evaluator and Authoring Ledger digests into the Root Corpus Manifest. It preserves authoring, evaluator, Reference Audit, and human-resolution provenance for every case.

The compiler compares each compiled case with its accepted Q31-A row. It checks split, kind, difficulty, Verdict Transition, and Signal Profile. It normalizes cross-split task and evidence templates. It rejects exact duplicates and unreviewed five-token Jaccard matches at or above `0.65`. It requires one Authoring Ledger row for every Q31-A allocation row. It writes every corpus file as `0444` and every corpus directory as `0555`. A later freeze rejects the non-empty target.

The allocator-visible scan covers prompts, Risk Findings, Review Queues, Allocation Receipts, and exported trajectories. The intentional leakage fixture contains one frozen Scorer Sentinel. The scan rejects it. The EvaluationRun disposition becomes `invalid` with `scorer_leakage`.

## RED and GREEN checks

| Seam | RED result | GREEN result |
| --- | --- | --- |
| Complete corpus freeze | `uv run python -m pytest -q tests/test_corpus.py::test_freeze_complete_corpus_materializes_the_accepted_topology` failed because `freeze_complete_corpus` did not exist. | The same command passed after compiler, validation, manifests, and separate trees were added. |
| Reference Audit and allocation | `uv run python -m pytest -q tests/test_corpus.py::test_complete_compiler_preserves_the_fixed_reference_audit_and_allocation` failed: `30 != 20` audit samples. | The same command passed after the fixed 20-case audit sample was selected. |
| Stable digests | The digest-vector test failed after the accepted event record change altered the frozen content. | The focused corpus suite passed after the final split and Root Corpus digest vectors were recorded. |
| Prompt compatibility blocker | `uv run --group dev python -m pytest -q` failed because the established prompt test required `E3 artifact`. | `uv run --group dev python -m pytest -q tests/test_corpus.py tests/test_prompting.py` passed with `8 passed`. |
| Complete suite | The first `uv run pytest -q` could not start because the inherited lane pytest launcher referenced another worktree. | `uv sync --offline --group dev --reinstall-package pytest && uv run pytest -q` passed with `104 passed in 13.46 seconds`. |

## Runtime and cost

All commands ran locally. No live model or network call occurred.

- Model requests: `0`.
- Model tokens: `0`.
- Available model cost: `$0`.
- Full suite runtime: `13.46` seconds.

## Scope and risks

The corpus is synthetic. The frozen result supports only the stated synthetic-corpus claim. EvaluationRuns from another Root Corpus Digest must not be compared as one experiment.
