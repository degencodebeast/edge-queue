# Five-minute video script and capture plan

Duration: 4 minutes 20 seconds. Use the four-case Development Judge Fixture only. Source every frame and number from [`video-data.json`](../evidence/ticket-21/artifacts/video-data.json), its bound [`summary.json`](../evidence/ticket-21/artifacts/summary.json), and `corpus/fixtures/judge-fixture-v1.json`.

| Time | Shot | Narration and overlay |
| --- | --- | --- |
| 0:00–0:25 | Evaluation inbox and Review Budget graphic | “An Evaluation Operations Lead cannot inspect every agent verdict. The costly question is which one gets an expert review.” |
| 0:25–0:50 | Baseline terminal output | “The simple deterministic baseline picks `EQ-F02-DEV-01`. It recovers no Label Error: Recall@1 is 0.00.” |
| 0:50–1:40 | Run `edgequeue judge` in one terminal | “EdgeQueue reads evidence, creates a Case Assessment, validates it deterministically, and selects `EQ-F01-DEV-01`.” |
| 1:40–2:10 | Split comparison of queue and metrics | “On the same four cases and budget of one, EdgeQueue gets Recall@1 1.00. The baseline gets 0.00.” |
| 2:10–2:45 | Review Packet, correction, Proof Bundle | “The highest-impact change was separating semantic ranking from deterministic authority. A human correction remains required.” |
| 2:45–3:15 | Changelog card | “We removed an earlier broad 0.80 result. Authoritative frozen reruns disproved it. The separate holdout claim is Recall@8 0.30.” |
| 3:15–3:45 | Reproduction command and proof verification | “A judge can run this offline. The recorded replay took about 0.057 seconds with zero requests, zero tokens, and zero model cost.” |
| 3:45–4:20 | Limits card and GitHub link | “The proof uses synthetic data. Production needs qualified reviewers and approved data. Hot take: confidence is not a review policy.” |

## Capture commands

```sh
UV_OFFLINE=1 uv run edgequeue judge --output-dir /tmp/edgequeue-video
cat /tmp/edgequeue-video/command-output.txt
UV_OFFLINE=1 uv run edgequeue verify /tmp/edgequeue-video/proof-bundle
```

Record the terminal at 1080p. Capture the command output, the generated Review Packet, and the Proof Bundle result. Do not show credentials, source paths from a user home, or unrelated panes.

## Recording assets

- `docs/evidence/ticket-21/artifacts/command-output.txt`: terminal text.
- `docs/evidence/ticket-21/artifacts/summary.json`: comparison and limits.
- `docs/evidence/ticket-21/artifacts/video-data.json`: required source bindings.
- `corpus/fixtures/judge-fixture-v1.json`: four-case frame list.
- `docs/evidence/ticket-21/artifacts/review-packet.html`: human-review visual.
