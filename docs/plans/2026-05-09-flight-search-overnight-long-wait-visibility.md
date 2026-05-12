# Plan: flight-search P1/P2 overnight and long-wait visibility

Current status: completed / verified offline

## Goal
Make overnight and very long connections visible in `agent_report` as operational trade-offs without automatically penalizing/hiding an itinerary solely because the wait is overnight or long.

## Constraints
- Offline-only verification; no live flight searches/API calls were run.
- Do not recreate raw JSON analyzer/workflow.
- Preserve P0 completeness: recommendation/control details referenced by `agent_report` keep `detail_status` and segment details when available.
- Preserve P1 Moscow gateway control behavior.
- Do not touch unrelated dirty files.

## Implemented contract shape
- `recommended_options[].connections[]` and `priority_options[].connections[]` now expose `tradeoffs` for connection-level waits.
- Long same-airport waits, currently >= 8h, get a `long_wait` tradeoff.
- Overnight waits get an `overnight_wait` tradeoff when the wait crosses the local calendar date or touches late-night/early-morning boundary.
- `answer_lines[]` includes compact `Connection trade-off: ...` wording when the best option has these tradeoffs.
- Risk scoring no longer adds `long_layover` or `night_connection` points solely for an otherwise valid wait; connection safety issues such as too-short, airport mismatch, cross-airport transfer, missing times, low-cost/leisure carrier, visa/self-transfer remain risk factors.

## TDD log
1. RED test added: `test_agent_report_overnight_tradeoffs.py` with a valid 13h25 overnight IST same-airport connection. It initially failed because `tradeoffs` were absent.
2. GREEN implementation:
   - `validation.py`: separated long/overnight wait labeling from connection risk; added `connection_tradeoffs(...)`.
   - `agent_report.py`: includes `tradeoffs` in connection summaries and surfaces a compact `Connection trade-off: ...` line.
   - `agent_report.v1.schema.json`: connection objects require `tradeoffs`, with structured `connection_tradeoff` items.
   - `test_agent_report_contract.py`: schema fixture updated for the new required field.
   - `tests/helpers.py`: subprocess tests propagate `PYTHONDONTWRITEBYTECODE=1`.
3. Docs updated:
   - `references/report-contract.md`
   - `references/overnight-gateway-detour.md`

## Verification
All commands were run offline under `/home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli` unless noted.

- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_agent_report_overnight_tradeoffs.py'` — `Ran 1 test in 0.206s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_agent_report_contract.py'` — `Ran 12 tests in 0.132s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_agent_report_p0_completeness.py'` — `Ran 1 test in 0.210s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_agent_report_p1_moscow_control.py'` — `Ran 1 test in 0.217s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_route_workflows.py' -k agent_report` — `Ran 1 test in 0.200s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests` — `Ran 90 tests in 7.711s`, OK.
- `PYTHONDONTWRITEBYTECODE=1 python -m flights_cli --json doctor` — exit `0`, `ok=true`.
- `git diff --check -- skills/productivity/flight-search` — clean.
- `agent_report.v1.schema.json` compactness — 694 lines, 15,945 bytes; contract limit still satisfied.
- Pycache cleanup/search — `__pycache__` and `*.pyc` under `flight-search/cli` absent after cleanup.

## Notes
- This does not make overnight waits “bad” by itself. It makes them visible, so the agent can explain the trade-off and compare alternatives.
- No live provider searches/API calls were run.
