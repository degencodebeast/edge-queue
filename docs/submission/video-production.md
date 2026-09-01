# EdgeQueue Loom demo

Target duration: 2 minutes 55 seconds.

The whole demo follows one question: four AI verdicts, one known mistake, and time to review one case.

Authoritative fixture: `corpus/fixtures/judge-fixture-v1.json`.

## Before you record

Run this from the repository root:

```sh
uv sync --frozen
DEMO_OUTPUT="$(mktemp -d /tmp/edgequeue-video.XXXXXX)"
clear
```

Keep that terminal open. The `DEMO_OUTPUT` name points to the new folder where EdgeQueue will save the review page and proof files.

Open `README.md` in the VS Code Markdown Preview. Make the text large enough to read in Loom.

In Loom:

- Record the full screen.
- Turn on your microphone.
- Keep the script on your phone or another screen.
- Use `Option + Shift + P` to pause while you change windows.
- Resume only when the next screen is ready.

Do not show setup, passwords, notifications, or your full home directory.

## 0:00 to 0:18 | One wrong verdict

**Show:** The top of the rendered README.

**Say:**

> Four AI verdicts are waiting. One is wrong, and I can review only one. If I choose badly, the mistake stays. EdgeQueue helps me choose the case to check first.

## 0:18 to 0:36 | The basic rules miss it

**Show:** Scroll to the Judge Fixture row in the README results table.

**Say:**

> The basic warning rules choose F02. The known mistake is in F01, so they spend the only review slot on the wrong case.

## 0:36 to 1:02 | Run EdgeQueue

**Do:** Pause Loom. Switch to the prepared terminal. Resume Loom.

**Say before the command:**

> I will run EdgeQueue on the same four cases with the same one-case limit. This replay needs no API key.

**Run:**

```sh
UV_OFFLINE=1 uv run edgequeue judge --output-dir "$DEMO_OUTPUT"
```

**Say after the result appears:**

> EdgeQueue chooses F01. The basic rules got zero out of one. EdgeQueue got one out of one on this example.

Keep both selected case IDs and both scores on screen for three seconds.

## 1:02 to 1:35 | Show the reviewer what happened

**Run:**

```sh
open "$DEMO_OUTPUT/review-packet.html"
```

**Show:** The selected case, its evidence, and the first case that missed the cut.

**Say:**

> This is the page the reviewer gets. F01 is first, with the evidence and the reason it was chosen. The page also shows the first case left out.
>
> The biggest change was taking the final choice away from the AI. The AI can flag a risk. Code chooses the list. Only the reviewer can change the official verdict.
>
> Here the reviewer changes F01 from FAIL to UNDETERMINED. EdgeQueue keeps both results.

## 1:35 to 2:05 | Check the proof, then break it

**Do:** Pause Loom. Return to the terminal. Resume Loom.

**Say:**

> Every run leaves the cases, the review result, and the score. This command recalculates the score instead of trusting the saved number.

**Run:**

```sh
UV_OFFLINE=1 uv run edgequeue verify "$DEMO_OUTPUT/proof-bundle"
```

Hold `Proof Bundle valid` on screen.

**Say:**

> The original passes. This copy has a changed score and a repaired file hash.

**Run:**

```sh
UV_OFFLINE=1 uv run edgequeue verify \
  docs/evidence/ticket-21/artifacts/tampered-proof-bundle
```

This command must fail.

**Say:**

> It still fails because the saved score does not match the cases.

Hold `metric_recomputation_mismatch` on screen for three seconds.

## 2:05 to 2:35 | Show the result we removed

**Do:** Pause Loom. Return to the README results table. Resume Loom.

**Say:**

> An early version reported zero point eight on the wider test. Those runs did not match the final cases.
>
> With the final saved data, the results were zero point three, zero point four, and zero point three. I removed the zero point eight claim. They do not prove EdgeQueue beats the other methods, so I do not say they do.

## 2:35 to 2:55 | Close

**Show:** Return to the top of the rendered README.

**Say:**

> EdgeQueue found the mistake the basic rules missed. The wider ranking still needs work. Today, a reviewer can see why a case was chosen, correct it, and check the result later.
>
> That is EdgeQueue.

## If something goes wrong

If the Judge command fails, stop the recording and fix it. Do not show an old successful output.

If the browser does not open the new Review Packet, run:

```sh
open "$DEMO_OUTPUT/review-packet.html"
```

If the terminal output scrolls away, run:

```sh
cat "$DEMO_OUTPUT/command-output.txt"
```

If the video runs long, shorten the explanation of the removed result. Keep the bad baseline choice, the Review Packet, the changed-score refusal, and the honest limit.
