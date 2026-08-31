# Ticket 18 TDD record

## RED and GREEN evidence

| Slice | RED command and result | GREEN command and result |
| --- | --- | --- |
| Review Packet | `uv run pytest -q tests/test_review_packet.py::test_renders_selected_case_with_risk_finding_and_selection_boundary` failed because `edgequeue.review_packet` did not exist. | The same command passed: `1 passed`. |
| Human Adjudication | `uv run pytest -q tests/test_adjudication.py::test_appends_an_authorized_correction_bound_to_manifest_and_prior` failed because `edgequeue.adjudication` did not exist. | The same command passed: `1 passed`. |
| Local CLI | `uv run pytest -q tests/test_cli_contracts.py::test_adjudicate_appends_one_local_authorized_record` failed because `--resulting-verdict` and `--adjudication-id` were unavailable. | The focused Ticket 18 tests passed: `15 passed`. |

## Final checks

- `uv run pytest -q tests/test_review_packet.py tests/test_adjudication.py tests/test_cli_contracts.py` passed: `15 passed`.
- `uv run pytest -q` passed: `144 passed`.
- `git diff --check 08e1a8575e5ed20f00b1d9700517fee2ee17facd...HEAD` passed.

## Offline execution record

- Runtime: focused check 0.26 seconds; required suite 17.79 seconds.
- Request count: 0.
- Token count: 0.
- Available cost: 0.
- Failed attempts: the three RED results above. No final check failed.
