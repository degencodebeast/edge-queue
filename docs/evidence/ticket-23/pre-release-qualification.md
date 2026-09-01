# Ticket 23 pre-release qualification

Status: clean-room qualification passed. The replacement Controller archive checkpoint is pending. The public Video URL is the only unresolved external input.

## Candidate boundary

- Base SHA: `ac1cc7b5f8d1ae445365454d2d1f5dc75dd42473`.
- Branch: `ticket/23-verify-final-submission-clean-room`.
- Superseded release-measurement range: `9b98f1d315cc01ba8b2fc4eddc2dc8f7014c38fc` through `89fa6a4228a2965f9a43941de2924b95a7cbf31d`.
- Replacement checkpoint SHA A2: assigned after this report is committed.
- Final Gate candidate: pending the replacement Controller archive checkpoint.
- Archive input: exact checkpoint SHA A2.
- Archive command: `uv run python scripts/build_release.py --sha <SHA-A2> --output-dir <CONTROLLER-OWNED-DIRECTORY-OUTSIDE-GIT>`.
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

The replay completed in `0.080` seconds. The timed command took `0.25` seconds of wall time.

The replay made `0` requests. It used `0` tokens. Its model cost was `$0.00`.

The generated Proof Bundle was valid. Its bundle digest was `92395675367fcef7dc6b333bf021c152856741535fa9e4d9a9e769b65e03b467`.

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

The final export scan passed. It found no user-home path, private local path, credential, email address, rate-limit data, token-usage data, encrypted content, or private account data.

## Submission and provenance

The submission validator passed. The final full suite passed: `172 passed in 30.73s`.

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

The replacement Standards and Specification reviews passed. No in-scope Critical or Major finding remains before checkpoint SHA A2.

## Controller archive checkpoint

The archive measurements for `9b98f1d315cc01ba8b2fc4eddc2dc8f7014c38fc` are superseded. They do not qualify the corrected trajectory corpus.

The Controller must build twice from exact checkpoint SHA A2 outside Git. The Controller must compare the two archives byte-for-byte.

The Controller must extract one archive into a no-Git environment. The Controller must run the full suite and Root Verification Command from that extraction.

Replacement archive measurements: pending Controller checkpoint.
