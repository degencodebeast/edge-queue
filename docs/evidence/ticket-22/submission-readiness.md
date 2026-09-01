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

The Controller created and preserved the approved A4 draft archive outside Git. The Gate independently rebuilt and verified A4.

- Draft snapshot SHA A4: `a5ff413585ef1687f66b21aaa4b7a63c7cc66781`.
- Draft archive: `edgequeue-a5ff413585ef-source.zip`, `2,216,245` bytes.
- Draft archive SHA-256, both runs: `9d8880db4a03f6d9eae311e075bcb7c83b303d54c2c794076d5fc5d4e23e6e4e`.
- Source tree: `8b3e746062753a04176732e4923a8644a39f9ecb`.
- Source identity binding: `d6b2385ffffa6b23b3998c82b6d14583416f61657c16f2005068be401054f353`.
- Controller release set: `.scratch/edgequeue/release/ticket-22-draft-a5ff413/`.
- Controller and Gate checks passed: determinism, exclusions, required proof inclusion, redaction scan, trajectory coverage, no-Git extraction, offline judge, proof verification, and submission validation.

The archive command was:

```sh
uv run python scripts/build_release.py --sha a5ff413585ef1687f66b21aaa4b7a63c7cc66781 --output-dir /tmp/edgequeue-ticket-22-draft-a4-1
```

The release manifest stores the source SHA, source tree, source identity binding, and per-file digests. The external sidecar stores the archive checksum, avoiding a self-checksum cycle.

## Legacy-record archive exclusion

The archive excludes only `runs/**` and `docs/evidence/ticket-20/traces/**`. These frozen legacy records contain local home paths. Ticket 22 does not rewrite them.

The archive retains the current proof replacements: `docs/evidence/ticket-20/development-traces/**`, `docs/evidence/ticket-20/frozen-traces/**`, Allocation Receipts, evaluation records, metrics, claims, trace manifest, and Ticket 21 proof and video assets.

## Remaining blocker

The user must upload the recording and add its external Video URL to `docs/submission/submission.md` before final submission.
