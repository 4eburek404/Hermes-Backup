# Tutu search-flights agent evaluation

This consumer evaluates only the first `tutu-search-flights` product scenario: search results in the agent's final answer must reflect the recorded Tutu result.

- Candidate skill source: pinned `origin/new-tutu` commit `ab1ae0ff622be6a78466ccc12f3be71bdb0abceb`; the skill is materialized for each run, not copied into this branch.
- Replay seam: the production MCP SDK HTTP request to `mcp.tutu.ru/mcp` is intercepted by `replay/sitecustomize.py` and answered from `fixtures/baseline.json`. The production CLI, parsing, transformation, agent reasoning, and final answer are not replaced.
- Safety: `replay/egress_proxy.py` blocks live Tutu CONNECT requests; Trajectory also fails on a blocked attempt.
- Outcome: deterministic checks reject unsupported flight identifiers, carrier/offer associations, prices, fares, baggage quantities, times, dates, durations, and airport codes. The semantic judge is an additional check for natural-language claims the deterministic checks cannot reliably parse; it cannot override a deterministic failure.
- Trajectory: requires the candidate CLI to complete and one successful `search_avia` MCP call at the recorded boundary with the fixture's search arguments, plus no forbidden alternate route. Failed replay-mismatch attempts stay in evidence but do not count as served results.

Run the deliberately bounded one-scenario/one-model/one-repeat smoke:

```bash
python3 evals/tutu-search-flights/run_eval.py
```

Evidence is written outside the repository under `~/.hermes/evals/tutu-search-flights/runs/`. Run the deterministic and harness regression contracts with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/contract/test_tutu_search_flights_eval_contract.py \
  tests/contract/test_eval_harness_contract.py \
  tests/contract/test_eval_harness_skill_source_contract.py \
  tests/contract/test_flight_calendar_ics_eval_consumer.py \
  tests/contract/test_flight_calendar_ics_eval_mutation_contract.py
```
