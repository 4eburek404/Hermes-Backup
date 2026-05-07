---
name: flight-search
description: Use when Codex needs to find, plan, compare, or diagnose flight options with the Hermes flights CLI, including airfare, tickets, routes, hub planning, IATA/date-window searches, Kupibilet live aggregate search, Travelpayouts cached sanity checks, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

Use this as the only flight-search skill. The normal workflow is one smooth path: run the Hermes flights CLI, read its compact report, and answer from that report. Do not start with cached APIs or raw provider tools.

## Golden Path

1. Normalize the request:
   - Convert relative dates to exact `YYYY-MM-DD`.
   - Normalize IATA codes; if a typo is likely, state the assumption.
   - Preserve user constraints: direct-only, carrier, airport, baggage, timing, price, or business/cheap priority.

2. Use the checked-out CLI:

```bash
cd cli/skill-clis/flights
python3 -m flights_cli --json doctor
```

3. Run live assembly with the compact report:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business \
  --agent-brief
```

Omit `--return-date` for one-way. Use `--profile cheap` only when the user explicitly asks for cheapest. Add `--aggregate-control-carrier SU` when Aeroflot/SVO or an all-SU route is plausible; repeat for another carrier only when the user cares about that carrier.

4. Read only `data.agent_report` in the normal path:
   - `answer_lines`
   - `recommended_options`
   - `priority_options`
   - `through_fare_checks`
   - `provider_failures`
   - `source_boundaries`
   - `hub_viability`
   - `rejected_pair_warnings`

5. Answer from the report:
   - Lead with the best viable option.
   - Show mandatory controls when present, especially all-SU/SVO, same-carrier, direct/nonstop, cheapest acceptable, or fastest acceptable.
   - Explain why a control is lower-ranked if it is not the main recommendation.
   - If `provider_failures` is non-empty, state the failed provider and do not replace it silently.
   - State source boundaries and purchase-screen verification.

## Do Not

- Do not call `travelpayouts_flight_search` or cached Travelpayouts/Aviasales helpers before the CLI.
- Do not treat cached `0 results` as proof that flights, direct routes, round trips, or through fares do not exist.
- Do not inspect raw `candidates` or `segment_results` in the normal workflow.
- Do not use `--include-candidates` unless debugging; it can create multi-megabyte JSON.
- Do not present summed separate-segment prices as airline/GDS through-fares.
- Do not hide `priority_options` just because they rank below the cheapest or fastest option.

## Debug Escalation

Use debug only when the compact report is missing, contradictory, or not enough to answer the user. Then read `references/debug-playbook.md` and rerun without `--agent-brief` or with targeted debug flags.

## References

- `references/report-contract.md` — how to read and answer from `agent_report`.
- `references/source-boundaries.md` — provider limits, cached absence, GDS/through-fare boundaries.
- `references/debug-playbook.md` — when and how to inspect larger CLI JSON safely.
