# Tutu search-flights agent evaluation

This consumer evaluates the first three `tutu-search-flights` product scenarios: Scenario 1 checks that search results reflect the recorded Tutu result; Scenario 2 checks that the agent does not invent a cabin-baggage weight absent from that result; Scenario 3 checks party-total prices and their association with the matching fare and fare conditions.

- Candidate skill source: pinned commit `55effd14b8245125cf9c47e65aad4dd84e8ec24a`; `run_eval.py` verifies the resolved commit for every run.
- Reproducible original baseline: `ab1ae0ff622be6a78466ccc12f3be71bdb0abceb`, retained as the separate `baseline` source in the manifest. Select it with `--skill-version baseline`; candidate is the default.
- The manifest lists the three comparison models. Each invocation selects exactly one using `--model <model-id>`; scenarios, prompts, fixtures, execution limits, and evaluation rules remain fixed.
- The skill is materialized from Git for each run, not copied into this branch.
- Replay seam: the production MCP SDK HTTP request to `mcp.tutu.ru/mcp` is intercepted by `replay/sitecustomize.py` and answered from the scenario's recorded fixture. The production CLI, parsing, transformation, agent reasoning, and final answer are not replaced.
- Scenario 3 uses the byte-identical recorded party fixture from candidate commit `ab1ae0ff622be6a78466ccc12f3be71bdb0abceb` (`2 adults + 1 child`). Deterministic outcome checks reject a multiplied group total and prices or conditions attributed to a different fare before consulting the semantic judge.
- Safety: `replay/egress_proxy.py` blocks live Tutu CONNECT requests; Trajectory also fails on a blocked attempt.
- Outcome: deterministic checks reject unsupported flight identifiers, carrier/offer associations, prices, fares, baggage quantities, times, dates, durations, and airport codes. Scenario 2 additionally checks that a stated hand-luggage weight is present as a cabin-baggage weight for the referenced offer. The semantic judge is an additional check for natural-language claims the deterministic checks cannot reliably parse; it cannot override a deterministic failure.
- Trajectory: requires the candidate CLI to complete and one successful `search_avia` MCP call at the recorded boundary with the fixture's search arguments, plus no forbidden alternate route. Failed replay-mismatch attempts stay in evidence but do not count as served results.

Run the deliberately bounded one-scenario/one-model/one-repeat smoke. Scenario 1 remains the default; select Scenario 2 or Scenario 3 explicitly:

```bash
python3 evals/tutu-search-flights/run_eval.py --scenario missing-cabin-baggage-weight
python3 evals/tutu-search-flights/run_eval.py --scenario party-price-and-fare
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
