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

The Controller ran the approved draft snapshot twice outside Git.

- Draft snapshot SHA A3: `d642353f4223c3966ef9266eeb3326156e77639f`.
- Draft archive run 1: `edgequeue-d642353f4223-source.zip`, `2,215,215` bytes.
- Draft archive run 2: `edgequeue-d642353f4223-source.zip`, `2,215,215` bytes.
- Draft archive SHA-256, both runs: `2e68ab04f3dbba88e9f64d90c3a34010f12c7c4a88202b0c06bb4bfb5ef75813`.
- Sidecar: `edgequeue-d642353f4223-source.zip.sha256`; its content matches the archive checksum.
- Source tree: `cc6a59579cdbf022662ef33c1563d33fdab9173e`.
- Archive entries: `1,252`, including `RELEASE_MANIFEST.json`; `1,251` are tracked package files.
- Controller release set: `.scratch/edgequeue/release/ticket-22-draft-d642353/`.
- Controller checks passed: determinism, exclusions, required proof inclusion, home-path and credential scans, no-Git extraction, offline judge, and submission validation.

The archive command was:

```sh
uv run python scripts/build_release.py --sha d642353f4223c3966ef9266eeb3326156e77639f --output-dir /tmp/edgequeue-ticket-22-draft-a3-1
```

The release manifest stores the source SHA, source tree, and per-file digests. The external sidecar stores the archive checksum, avoiding a self-checksum cycle.

## Legacy-record archive exclusion

The archive excludes only `runs/**` and `docs/evidence/ticket-20/traces/**`. These frozen legacy records contain local home paths. Ticket 22 does not rewrite them.

The archive retains the current proof replacements: `docs/evidence/ticket-20/development-traces/**`, `docs/evidence/ticket-20/frozen-traces/**`, Allocation Receipts, evaluation records, metrics, claims, trace manifest, and Ticket 21 proof and video assets.

## Remaining blocker

The user must upload the recording and add its external Video URL to `docs/submission/submission.md` before final submission.
