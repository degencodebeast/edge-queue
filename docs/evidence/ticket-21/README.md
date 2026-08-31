# Ticket 21 Judge Fixture evidence

Run the evidence with this command:

```sh
uv run edgequeue judge --output-dir docs/evidence/ticket-21/artifacts
```

The complete output is in `judge-output.txt`.

The `artifacts/` directory contains the Review Packet, correction, Calibration Candidate, Proof Bundle, and tamper report.

`artifacts/video-data.json` is the digest-bound handoff for Ticket 22 video capture.

It binds the authoritative four-case DEV fixture, command output, summary, and artifact paths.

`live-run/live-run.json` records that no configured live provider was available. It is separate from frozen proof.

The accepted Calibration Candidate remains unpromoted. PCH was not run. No calibration-improvement claim is made.

This evidence supersedes the older four-AH-case Judge Fixture statement in Ticket 15 historical evidence.
