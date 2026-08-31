# Ticket 14 contract validation

Date: 2026-08-31

Base SHA: `3ad1b0f649e3ef159ee54f7fb56c1c87cbf8b403`

## Contract surface

The shared contract module freezes schema version `1.0` for these records:

- corpus records: Case Specifications, Trajectory Events, Frozen Initial Evaluations, Shadow Evaluations, RankerCases, ScorerCases, Evaluator Manifests, Authoring Ledgers, Split Manifests, and Corpus Manifests;
- Case Assessments and Allocation Receipts;
- EvaluationRuns;
- Adjudications, Reviewer Manifests, Calibration Cases, Calibration Candidates, Calibration Packs, and Calibration Promotions;
- Proof Bundle manifests, Claims, Claims Manifests, Verification Failures, and Verification Results.

Each versioned JSON Schema closes its object with `additionalProperties: false`. Nested Case Assessment attempts, evidence references, split digest entries, proof file entries, and selection-boundary fields also reject unknown fields. The legacy prototype schema remains unchanged so the accepted trace fixtures remain compatible.

## RED-GREEN evidence

| Seam | RED command and result | GREEN command and result |
| --- | --- | --- |
| Contracts and unknown fields | `uv run pytest -q tests/test_contracts.py tests/test_cli_contracts.py` failed during collection with `ModuleNotFoundError: No module named 'edgequeue.contracts'`. | The same command passed with `50 passed`. |
| Canonical serialization and digests | `uv run pytest -q tests/test_digests.py` failed with a `RecursionError` after the compatibility wrapper was first added. | `uv run pytest -q tests/test_contracts.py tests/test_digests.py` passed. The original vector remains `e165eb0a9d56477c8fa3a33101bbc9c248941f94c3adbae8ec541071b31f2a5d`. |
| Versioned corpus records | The new corpus version assertions failed with `KeyError: 'schema_version'`. | `uv run pytest -q tests/test_corpus.py::test_builds_isolated_development_case_from_frozen_allocation` passed after the four corpus dataclasses gained version fields. |
| Named verification failures | `uv run pytest -q tests/test_contracts.py::test_verification_failures_use_frozen_named_codes` failed because `generic_failure` was accepted. | The same command passed after the frozen failure-code enumeration was added. |
| CLI contracts | Before the entry point, the help test could not import `edgequeue.cli`. | `uv run edgequeue judge --help`, `uv run edgequeue adjudicate --help`, and `uv run edgequeue verify --help` each exited `0`. |
| Authority and allocation invariants | `uv run pytest -q tests/test_contracts.py` reported `2 failed` for calibration nomination authority and Allocation Receipt queue invariants. | The same focused contract suite passed with `46 passed` after distinct reviewer/promoter roles, retry failure handling, adjudication verdict invariants, schema parity, self-digests, and deterministic receipt checks were added. |
| Proof manifest and corpus authority | New tests first failed because manifest hashing was circular and the corpus schemas accepted unrestricted identifiers, splits, and event types. Runtime corpus construction also exposed the existing `artifact` event. | The focused regression tests passed with `3 passed` after the manifest projection, named missing-file distinction, strict runtime constraints, and complete event enum were added. |
| Split, file, and schema authority | Review-directed RED tests failed for split-to-case binding, JSONL byte hashing, non-canonical JSONL text, missing root provenance bindings, and a cyclic Authoring Ledger field. | Runtime validation now loads all ten versioned corpus schemas, binds case IDs to splits, validates both root provenance digests, accepts only canonical JSON/JSONL text, and binds the ledger by content digest without a root cycle. The final focused run passed with `55 passed`. |
| Gate replacement: packaged schemas and corpus records | `uv run pytest -q tests/test_distribution.py tests/test_contracts.py::test_trajectory_event_accepts_every_normalized_event_kind tests/test_contracts.py::test_evaluator_manifest_requires_complete_frozen_configurations tests/test_contracts.py::test_authoring_ledger_requires_closed_candidate_attempt_records` failed with `8 failed`: a built wheel could not load schemas, five normalized event kinds were unsupported, and the two corpus records were incomplete. Review-directed reruns then failed with `2 failed` for unbound Manifest identifiers and omitted Ledger provenance, and `3 failed` for a missing reasoning summary and fewer than three evaluator records. | The initial command passed with `9 passed`. The final focused command passed with `11 passed` after the wheel includes schemas, runtime loads package resources, every normalized event kind is frozen, the Manifest binds one primary and two shadow configurations, and Ledger candidates bind blueprint, trajectory, evaluator-manifest, three evaluator attempts, decision, reviewer, and recorded-time fields. |
| Authorized corpus topology | Review found that a Ledger row could exceed three candidates, a Split Manifest could repeat or reorder case identifiers, and root references were not checked against supplied manifests and Ledger content. | `uv run pytest -q tests/test_contracts.py::test_authoring_ledger_requires_closed_candidate_attempt_records tests/test_contracts.py::test_split_manifest_rejects_duplicate_or_unordered_case_membership tests/test_contracts.py::test_corpus_manifest_binds_all_splits_and_the_supplied_ledger_digest` passed with `3 passed`. Runtime validation now bounds candidates, requires stable unique split membership, and binds exactly the supplied DEV, AH, PCH Split Manifests and Ledger digest. |
| Gate cycle 2: candidate-attempt policy | `uv run pytest -q tests/test_contracts.py::test_authoring_ledger_rejects_all_failed_candidates_for_one_row tests/test_contracts.py::test_authoring_ledger_rejects_multiple_accepted_candidates_for_one_row tests/test_contracts.py::test_authoring_ledger_rejects_a_third_primary_execution_attempt` failed with `3 failed`: the closed schema had no target Verdict or evaluator-role/output fields. | The same command passed with `3 passed` after Ledger records bound target and evaluator Verdicts, roles, retry sequences, row terminal state, first-match acceptance, and the three-candidate Corpus Freeze block. |
| Cycle 3 retry closure | A closure review reproduced an `execution_failure` followed by an accepted retry. | `uv run pytest -q tests/test_contracts.py::test_authoring_ledger_rejects_retry_after_execution_failure` passed after retries were limited to timeout, malformed response, and schema failure. |
| Gate cycle 3 row bindings | `uv run pytest -q tests/test_contracts.py::test_authoring_ledger_rejects_row_binding_probes` failed with `5 failed`: row-level target, Evaluator Manifest, Case Blueprint, terminal-candidate, and accepted-output bindings were absent. | The same parameterized public test passed with `5 passed` after the Ledger rejects all five histories. |

## Direct validation results

The direct contract check produced:

```text
contract: PASS
unknown-field: unknown_field: case_assessment contains unknown field(s): unknown
serialization: {"a":"é","z":"a\nb"}
digest-vector: 36eff7525546a92edd80e6b57196e624176a4d6491410ead50497213008caef3
schemas: 25 versioned files parse
```

The displayed digest vector is independently calculated as SHA-256 over the UTF-8 bytes for `{"a":"é","z":"a\nb"}`. The test vector separately hard-codes the UTF-8 bytes and expected digest for `{"a":"é","b":2}`. The timestamp test confirms that declared `created_at` values do not change content digests when passed as excluded fields. `digest_contract` excludes the declared non-authoritative timestamp field set by default.

## Required checks

- Focused Ledger closure tests: `7 passed`.
- Full suite: `uv run pytest -q` returned `94 passed`.
- Lock and syntax checks: `uv lock --check`, `git diff --check`, and `uv run python -m compileall -q src tests` passed.
- CLI help checks: judge, adjudicate, and verify each returned exit code `0`.
- Evidence artifact verification: this report contains the required RED and GREEN commands, digest vectors, named failure result, and CLI results.

## Internal review fixes

The first Standards and Specification reviews found authority gaps. Repeat reviews found further contract gaps. Those findings are addressed by distinct reviewer/promoter roles, retry failure handling, verdict invariants, bounded unique receipt queues, case-bound trajectory schemas, self-digest checks, Evaluation Core references, structured verification failures, runtime use of versioned corpus schemas, strict corpus identifiers and enums, split binding, pre-digest corpus validation, canonical JSON/JSONL file checks, required root provenance bindings, non-circular Proof Bundle manifest binding, package-resource schema loading, complete normalized event kinds, and bound Evaluator Manifest and Authoring Ledger records. The final review pair found no Critical or Major findings. Both reviewers recorded the open-ended `schema_versions` map as a Minor risk; the Specification reviewer also noted that CLI tests do not assert every option string. The candidate requires verified same-case evidence for every Risk Finding, enforces `offline: true` and `read_only: true`, validates nested schema versions, binds Reviewer Manifest entries to explicit identities and roles, adds Resolution Adjudications and calibration nomination authority, binds adjudications and calibration records to the Reviewer Manifest digest, binds Allocation Receipt entries to assessment digests and configuration, enforces exclusive Case Assessment states, aligns runtime and schema top-level fields, and rejects canonical key collisions after line-ending normalization.

## Runtime and cost

No live model or network calls occurred. Implementation and checks used local commands only. Model request count: `0`. Model token count: `0`. Available model cost: `$0`.

## Scope notes

The command handlers remain explicit later-slice seams. Ticket 14 freezes their names and arguments. Later proof and reviewer tickets provide execution behavior. The existing scoring, ranking, integrity, digest, and trace modules retain their public behavior.
