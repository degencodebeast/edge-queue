# Ticket 22 submission-readiness report

## Draft package

- Base SHA: `673e5ec25fcea40ad80316434f2cfb2b5f2568bb`.
- Candidate SHA: pending final Ticket 22 commit.
- Public broad claim: frozen-synthetic Allocation Holdout Recall@8 `0.30` from `docs/evidence/ticket-20/claims.json`.
- Illustrative claim: four-case Development Judge Fixture Recall@1 `1.00` versus deterministic baseline `0.00` from Ticket 21 proof artifacts.
- Calibration: candidate gate accepted, not promoted, PCH not run, no calibration-improvement claim.
- Historical evidence: Ticket 15 states an AH fixture. Ticket 21 superseded that sentence with the four-case Development fixture. Ticket 15 evidence remains unchanged.

## Required files

- `README.md`, `IMPROVEMENT_CHANGELOG.md`, `REPRODUCTION.md`, `PREEXISTING.md`, and `.env.example` are present.
- `docs/submission/` contains copy-ready Markdown, local HTML, video script, timed shots, capture commands, and asset list.
- `docs/trajectories/trace-manifest.json` records 21 redacted ledger sources, including Controller, Worker, Gate, and internal-review roles.

## Draft archive measurement

The Controller must run the approved draft snapshot twice outside Git:

```sh
uv run python scripts/build_release.py --sha <draft-package-snapshot-sha> --output-dir /tmp/edgequeue-ticket-22-draft-1
uv run python scripts/build_release.py --sha <draft-package-snapshot-sha> --output-dir /tmp/edgequeue-ticket-22-draft-2
```

- Draft archive filename 1: pending Controller measurement.
- Draft archive size 1: pending Controller measurement.
- Draft SHA-256 1: pending Controller measurement.
- Draft archive filename 2: pending Controller measurement.
- Draft archive size 2: pending Controller measurement.
- Draft SHA-256 2: pending Controller measurement.

The release manifest stores the source SHA and per-file digests. The external sidecar stores the archive checksum, avoiding a self-checksum cycle.

## Legacy-record archive exclusion

The archive excludes only `runs/**` and `docs/evidence/ticket-20/traces/**`. These frozen legacy records contain local home paths. Ticket 22 does not rewrite them.

The archive retains the current proof replacements: `docs/evidence/ticket-20/development-traces/**`, `docs/evidence/ticket-20/frozen-traces/**`, Allocation Receipts, evaluation records, metrics, claims, trace manifest, and Ticket 21 proof and video assets.

## Remaining blocker

The user must upload the recording and add its Video URL to `docs/submission/submission.md` before final submission.
