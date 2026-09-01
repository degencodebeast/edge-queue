# Ticket 23 pre-release qualification

Status: the replacement clean-room checks and Controller archive qualification passed. The public Video URL is the only unresolved external input.

## Candidate boundary

- Base SHA: `ac1cc7b5f8d1ae445365454d2d1f5dc75dd42473`.
- Branch: `ticket/23-verify-final-submission-clean-room`.
- Superseded release-measurement range: `9b98f1d315cc01ba8b2fc4eddc2dc8f7014c38fc` through `8e96cccb487c36dffa896be712864e48cbb7ed8f`.
- Replacement checkpoint SHA A3: `aafc3faee21d67be4ea4c372a363a6c57714b8f9`.
- Final Gate candidate: assigned when this report-only descendant is committed.
- Archive input: exact checkpoint SHA A3 `aafc3faee21d67be4ea4c372a363a6c57714b8f9`.
- Archive command: `uv run python scripts/build_release.py --sha aafc3faee21d67be4ea4c372a363a6c57714b8f9 --output-dir /tmp/edgequeue-ticket-23-sha-a3`.
- Release owner: the Controller. Ticket 23 archives are verification artifacts, not the final release set.

## Clean-room result

The Worker used Codex CLI `0.151.0` with `gpt-5.6-sol` at high reasoning.

The verification environment used Python `3.14.4`, uv `0.11.6`, and Git `2.52.0`.

The credential-free Root Verification Command was:

```sh
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY \
  -u GEMINI_API_KEY -u XAI_API_KEY -u MISTRAL_API_KEY \
  UV_OFFLINE=1 uv run edgequeue judge --output-dir <TEMPORARY-DIRECTORY>/judge
UV_OFFLINE=1 uv run edgequeue verify <TEMPORARY-DIRECTORY>/judge/proof-bundle
```

The replay completed in `0.065` seconds. The timed command took `0.25` seconds of wall time.

The replay made `0` requests. It used `0` tokens. Its model cost was `$0.00`.

The generated Proof Bundle was valid. Its bundle digest was `2a98ca565bc4b14452b9034c4b892451b095261c198fd0f440c0c95981543f75`.

The checked-in Ticket 21 Proof Bundle was valid. Its bundle digest was `3eca0104f3393533806ef0f71aff167c3a4adeef4b3c76853fbb48e23c24f70d`.

Proof Bundle file hashes were identical before and after the Root Verification Command. The command changed no checked-in Proof Bundle file.

## Public claims

Claims were recomputed from authoritative inputs and checked against both Claims Manifests.

- Allocation Holdout attempts produced Recall@8 values `0.30`, `0.40`, and `0.30`.
- The public broad claim is frozen-synthetic Allocation Holdout Recall@8 `0.30`.
- The illustrative four-case Development Judge Fixture has Recall@1 `1.00`.
- The deterministic baseline has Recall@1 `0.00` on that fixture.
- The Calibration Candidate was accepted but not promoted.
- The Post-Calibration Holdout was not run.
- No calibration-improvement or production-generality claim is made.

Public submission text does not state the superseded four-AH Judge Fixture claim. Historical `0.80` text appears only as an explicitly removed experiment.

## Trajectories and privacy

The Controller ledger contains `26` entries. The corrected export contains `29` source records.

The export covers Controller, Worker, Gate, and Internal review roles. It includes Ticket 22 and Ticket 23 sources.

Ticket 22 has one Worker source and two distinct Internal review sources. The Standards source identifies Lovelace at `/root/standards_review`. The Specification source identifies Hume at `/root/specification_review`.

No Ticket 22 Internal review record duplicates the Ticket 22 Worker source.

Each manifest record names one readable trajectory and one supporting raw-event excerpt.

The bounded export preserves the first `60` events and final `20` events. It fills the remaining `40` slots with the most recent signal events.

The Ticket 23 Gate and Worker readable and raw records now retain late blocker, feedback, repair, retry, checkpoint, and completion evidence.

The final export scan passed. It found no user-home path, private local path, credential, email address, rate-limit data, token-usage data, encrypted content, or private account data.

## Submission and provenance

The submission validator passed. The final full suite passed: `173 passed in 32.12s`.

`uv lock --check`, compileall, and `git diff --check` passed.

`PREEXISTING.md` records reused tools, dependencies, licences, data provenance, model provenance, and legacy archive exclusions.

The synthetic corpus contains no private production trajectory. Only an authorized human Adjudication can change a canonical Verdict.

Participant eligibility status: confirmed. Only the confirmation status is stored. No identity, location, contact, or payment data is stored.

## Video qualification

The local video plan is `4 minutes 20 seconds`, or `260` seconds. This is below the five-minute limit.

The fixture, summary, artifact-path, and command-output digests match `video-data.json`.

All listed local recording assets exist. The script uses the four-case Development Judge Fixture and preserves the public claim boundary.

The user must record and upload the final video. The user must then add its public Video URL to `docs/submission/submission.md`.

The missing public Video URL is an external qualification blocker.

Participant eligibility is confirmed. Only the confirmation status is stored.

## Verification commands

```text
uv run pytest -q tests/test_submission.py
uv run pytest -q
uv lock --check
uv run python -m compileall -q src tests scripts
git diff --check
uv run python scripts/verify_submission.py --project-root .
```

The focused submission test first found a ledger binding gap. The RED result was `1 failed, 4 passed`.

After the Controller added exact internal-review source IDs, the focused test was GREEN: `5 passed`.

Gate cycle 2 found that the bounded exporter discarded final events after it sorted an oversized signal set.

The authorized CLI-seam regression was RED because the export lost the late blocker, checkpoint, and completion tail: `1 failed`.

After the bounded selection repair, the same regression was GREEN: `1 passed`. The final focused submission suite was GREEN: `6 passed in 12.84s`.

Full-suite results are recorded in `checks.json`. Archive-checkpoint results are recorded below and in the Controller checkpoint handoff.

## Internal reviews

Two independent read-only `gpt-5.6-terra` reviewers checked the change.

The Standards review found that the internal-review export did not isolate reviewer events. It also found that the privacy statuses did not agree.

The Controller added both exact reviewer sources. Each Ticket 23 reviewer now has a separate readable trajectory and raw-event excerpt.

The Worker also aligned the privacy evidence. The final export preserves reviewer instructions, actions, tool responses, feedback, and results.

The Specification review found the same privacy mismatch. It also identified the exact-SHA and archive fields completed by this report update.

Both reviews identified the Video URL and eligibility confirmation as external inputs. The user later confirmed eligibility. The Video URL remains unresolved.

After the Controller added both reviewer JSONL sources, the Standards and Specification reviews passed. No in-scope Critical or Major finding remained before SHA A.

Gate cycle 1 later found that the Ticket 22 reviewer sources were labeled as Worker continuations. The Ticket 22 Internal review record also duplicated the primary Worker source.

The Controller corrected the authoritative ledger. The replacement export binds the primary source to Worker and both reviewer sources to Internal review.

The Gate BLOCK is the RED evidence for this provenance gap. The focused submission tests remained GREEN, so no speculative or protected-surface test was added.

The replacement Standards and Specification reviews passed before SHA A2 and after the archive checkpoint.

Gate cycle 2 then found that the Ticket 23 excerpts omitted late feedback, repair, and completion events. This finding superseded SHA A2 and `8e96cccb487c36dffa896be712864e48cbb7ed8f` for release measurement.

The Controller authorized one CLI-seam regression and the narrow `select_events` repair. The regenerated Gate and Worker artifacts retain the cycle-1 provenance blocker and the repair/checkpoint evidence.

The SHA A3 Standards and Specification reviews passed. No in-scope Critical or Major finding remains.

The Controller qualified the replacement archive. The report-only descendant is ready for the final Gate cycle.

## Controller archive checkpoint

The archive measurements for SHA A, SHA A2, and all descendants through `8e96cccb487c36dffa896be712864e48cbb7ed8f` are superseded. They do not qualify the corrected completion-aware trajectory corpus.

The Controller built twice from exact checkpoint SHA A3 outside Git. The two archives were byte-identical.

- Archive name: `edgequeue-aafc3faee21d-source.zip`.
- Archive size: `2,053,989` bytes.
- Archive SHA-256: `b8c1f8a904797261143d096707669a8dbc7c0dab6aea49ba2df6847f40cac3ad`.
- Source-tree digest: `897243d6df0346a8610d15b7b2fb2bb8d33f9ade`.
- Source identity binding: `eb4cdf8fa29ecd255aa94ad52d6b286dbef005b31171f7b002d78302342382db`.
- Archive contents: `1,269` tracked files plus the release manifest.
- Controller preservation path: `.scratch/edgequeue/release/ticket-23-verification-aafc3fa/`.

The Controller extracted the archive into a no-Git environment. The full suite passed: `173 passed in 19.03s`.

The extracted Ticket 23 Gate and Worker exports each contain `120` chronological events. Both retain late blocker, repair, checkpoint, and completion evidence.

The extracted credential-free, offline Judge and verifier passed. Replay took `0.123` seconds. Observed wall time was `0.888278` seconds.

The extracted run made `0` requests. It used `0` tokens. Its model cost was `$0.00`.

The extracted Proof Bundle digest was `32e19e08ae382bcf6b5e7cfe8f17883edb921f637500afd44d66154aeeca0fed`. The tamper check returned `metric_recomputation_mismatch`.

Proof immutability, lock validation, compileall, the submission validator, and checked-in Proof Bundle verification passed in the extracted checkpoint.

`checks.json` preserves the pre-archive SHA A3 checkpoint state. This section records the later Controller-owned archive qualification.
