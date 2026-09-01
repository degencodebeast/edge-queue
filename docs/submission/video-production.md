# EdgeQueue demo script and capture plan

Target duration: 3 minutes 10 seconds.

Core story: four agent verdicts, one wrong verdict, and one available review slot.

Authoritative fixture: `corpus/fixtures/judge-fixture-v1.json`.

## Recording method

Use one Loom recording with your microphone enabled. Record the full screen so Loom captures the terminal and browser when you switch between them.

Speak live while you follow the timed sections. Keep the narration on a phone or second screen that Loom does not capture.

Pause Loom before you switch windows or prepare the next command. Resume when the correct screen is ready. On macOS, Loom uses `Option + Shift + P` to pause or resume by default.

Do not read shell commands aloud. Introduce each action, run it, and explain the result after it appears.

You do not need text overlays or a downloaded video file. Use the rendered README for the opening and closing text. Use terminal output and the generated Review Packet for the product evidence.

## Before recording

Use a 1920 by 1080 canvas. Put the terminal and browser side by side. Increase the terminal font until every line is readable at 720p.

Prepare the demo from the repository root:

```sh
uv sync --frozen
DEMO_OUTPUT="$(mktemp -d /tmp/edgequeue-video.XXXXXX)"
clear
```

Complete these commands before screen recording starts. Keep the same terminal open because `DEMO_OUTPUT` exists only in that shell.

Keep these files ready:

- `docs/evidence/ticket-21/artifacts/summary.json`
- `docs/evidence/ticket-20/claims.json`
- `docs/evidence/ticket-21/artifacts/tampered-proof-bundle/`
- `README.md`

Open `README.md` in the VS Code Markdown Preview. Zoom until the opening statement and results table are easy to read in Loom.

Do not show a user home path in the recording. Crop unrelated tabs, shell history, notifications, and personal information.

## Recording script

### 0:00 to 0:12 | The decision

**Screen:** Show the top of `README.md` in the VS Code Markdown Preview. The opening block supplies the on-screen text.

**On-screen text:**

```text
4 agent verdicts
1 wrong verdict
1 review slot
```

**Say live:**

> Four agent verdicts arrive for evaluation. One verdict is wrong. A qualified reviewer only has time to inspect one case. Which case should they open?

### 0:12 to 0:32 | The baseline misses

**Screen:** Keep the README opening visible. Point to the fixed Review Budget statement.

**Say live:**

> A deterministic warning baseline selects case F02. The actual Label Error is in F01, so the baseline spends the review slot on the wrong case. Recall at one is zero.

Pause on these values:

```text
Baseline: EQ-F02-DEV-01
False negative: EQ-F01-DEV-01
Recall@1: 0.00
```

### 0:32 to 1:02 | Run EdgeQueue

**Loom action:** Pause Loom. Switch to the prepared terminal. Resume Loom, then paste and run:

```sh
UV_OFFLINE=1 uv run edgequeue judge --output-dir "$DEMO_OUTPUT"
```

Do not read the command aloud. Hold the completed output for five seconds.

**Say live before running the command:**

> Now I will run EdgeQueue on the same four frozen Development cases with the same Review Budget of one. The ranker assesses evidence without access to hidden scoring labels. Deterministic code validates the records, enforces the budget, and owns the final queue order.

Let the real command finish. Do not replace its output with staged terminal text. The command already prints the comparison.

### 1:02 to 1:27 | The right case reaches the reviewer

**Screen:** Hold on the command output. Highlight both selected case IDs and the Recall values.

**Say live after the result appears:**

> EdgeQueue selects F01, the case that contains the known Label Error. Under the same budget, Recall at one is now one point zero. The reviewer gets the case the baseline missed.

Pause on these values:

```text
Baseline: EQ-F02-DEV-01
EdgeQueue: EQ-F01-DEV-01
Recall@1: 0.00 versus 1.00
```

### 1:27 to 1:57 | Evidence and human authority

**Screen:** Open the generated Review Packet:

```sh
open "$DEMO_OUTPUT/review-packet.html"
```

Show the Review Budget, selected case, risk score, evidence, and first excluded case.

**Say live:**

> This is the packet an Evaluation Operations Lead receives. It explains why F01 crossed the selection boundary and links the finding to frozen evidence. Our most important improvement was separating semantic judgment from deterministic authority. The agent recommends a case. It cannot change the canonical Verdict. Only an authorized human can do that.

Scroll to the correction.

> Here, the reviewer changes F01 from FAIL to UNDETERMINED. The correction is append-only and bound into the evidence trail.

### 1:57 to 2:29 | Verify, then attack the proof

**Loom action:** Pause Loom. Return to the same terminal. Resume and run:

```sh
UV_OFFLINE=1 uv run edgequeue verify "$DEMO_OUTPUT/proof-bundle"
```

Hold `Proof Bundle valid` for three seconds.

**Say live:**

> The run produces a Proof Bundle. Verification recomputes its bindings and metrics instead of trusting the saved claim. The untouched bundle passes.

Run the checked-in hostile case:

```sh
UV_OFFLINE=1 uv run edgequeue verify \
  docs/evidence/ticket-21/artifacts/tampered-proof-bundle
```

This command must return a failure. That failure is the expected product behavior.

**Say live:**

> This copy contains a changed Recall value and a repaired file digest. EdgeQueue still rejects it because the reported metric no longer matches the underlying cases.

Hold on:

```text
Proof Bundle invalid
metric_recomputation_mismatch
```

### 2:29 to 2:52 | State the evidence boundary

**Screen:** Pause Loom. Open the README `Measured results` table in Markdown Preview. Resume Loom.

**Say live:**

> The one point zero result comes from this four-case Judge Fixture. It demonstrates the workflow, not production performance. On the separate frozen synthetic Allocation Holdout, the public Recall at eight result is zero point three zero. The broad gate rejects a general improvement claim.

> We previously recorded a broader zero point eight zero result. Authoritative frozen reruns disproved it, so we removed it instead of defending a number the evidence could not support.

### 2:52 to 3:10 | Close

**Screen:** Return to the top of the rendered README. The repository link and opening statement serve as the end card.

**Say live:**

> EdgeQueue helps evaluation teams spend limited expert time on cases most likely to contain a wrong verdict. The ranker assesses risk. Deterministic code verifies the evidence. The reviewer owns the correction.

**Visible README text:**

```text
EdgeQueue
Find wrong agent verdicts before review time runs out.

github.com/degencodebeast/edge-queue
Offline replay: 0 requests | 0 tokens | $0.00 model cost
```

## Recording priorities

Show the result during the first minute. Do not start with architecture.

Keep the baseline and EdgeQueue case IDs visible together. This comparison is the central product moment.

Show the generated Review Packet. A browser view makes the reviewer workflow easier to understand than terminal output alone.

Keep `metric_recomputation_mismatch` visible for two seconds. This is the memorable refusal in the demo.

Say the synthetic-data limit aloud. The short fixture result and broad holdout result answer different questions.

Use real command output. If a command finishes quickly, pause on the result.

Use Loom pause and resume between sections. Do not leave window switching or preparation time in the final recording.

## Fallback capture plan

If the live Judge command fails during recording, stop the take and fix the environment. Do not substitute a staged success.

If the browser does not open the generated packet, open the checked-in packet:

```sh
open docs/evidence/ticket-21/artifacts/review-packet.html
```

If the Judge output scrolls out of view, print its saved copy:

```sh
cat "$DEMO_OUTPUT/command-output.txt"
```

If the recording exceeds 3 minutes 20 seconds, shorten the evidence-boundary section. Preserve the comparison, Review Packet, proof verification, tamper rejection, and limits statement.
