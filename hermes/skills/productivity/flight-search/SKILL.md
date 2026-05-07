---
name: flight-search
description: Use when Codex needs to find, plan, compare, or diagnose flight options with the Hermes flights CLI, including airfare, tickets, routes, hub planning, IATA/date-window searches, Kupibilet live aggregate search, Travelpayouts cached sanity checks, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

Use this as the only flight-search skill. The normal workflow is one smooth path: run the Hermes flights CLI, read its JSON response, and answer from that response. Do not start with cached APIs or raw provider tools.

## Golden Path

1. Normalize the request:
   - Convert relative dates to exact `YYYY-MM-DD`.
   - Normalize IATA codes; if a typo is likely, state the assumption.
   - Preserve user constraints: direct-only, carrier, airport, baggage, timing, price, or business/cheap priority.

2. Locate and verify the CLI:

```bash
# Find the checkout path at runtime — it moves between sessions
FLI_DIR=$(find /tmp -maxdepth 3 -path '*/skill-clis/flights' -type d 2>/dev/null | head -1)
cd "$FLI_DIR" && python3 -m flights_cli --json doctor
```

The CLI lives at a temp checkout path (e.g. `/tmp/hermes-*/cli/skill-clis/flights`). Do NOT assume it is under `~/.hermes/skills/`.

3. Run live assembly:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business
```

Omit `--return-date` for one-way. Use `--profile cheap` only when the user explicitly asks for cheapest. Add `--aggregate-control-carrier SU` when Aeroflot/SVO or an all-SU route is plausible; repeat for another carrier only when the user cares about that carrier.

⚠️ **Do NOT use `--agent-brief`** — it does not exist in the current CLI version and will cause an error. The full JSON output is the canonical output; read `recommendations` and `ranked_candidates` directly.

4. Read the JSON response — key fields in the normal path:
   - `data.recommendations` — `best_ranked`, `fastest_acceptable`, `cheapest_acceptable`
   - `data.ranked_candidates` — full ranked list with risk scores and connection validation
   - `data.live_search.hub_viability` — which hubs worked and which didn't
   - `data.live_search.failures` — provider failures (must be stated to the user)
   - `data.live_search.plan.warnings` — important caveats about separate tickets, etc.

5. Answer from the JSON response:
   - Lead with `data.recommendations.best_ranked` as the primary recommendation.
   - Also report `fastest_acceptable` and `cheapest_acceptable` if present.
   - Show top 3–5 ranked candidates from `data.ranked_candidates` (those with `ok: true` and `risk.reject: false`).
   - For each option show: carriers, price, elapsed time, connection time and airport, risk grade.
   - If `data.live_search.failures` is non-empty, state the failed provider and do not replace it silently.
   - State source boundaries and purchase-screen verification.
   - Do NOT present separate-segment prices as through-fares.
   - Do NOT hide options ranked below cheapest/fastest if they have notable advantages.

## Do Not

- Do not call `travelpayouts_flight_search` or cached Travelpayouts/Aviasales helpers before the CLI. The skill's Golden Path starts and ends with `flights_cli route live-assemble`.
- Do not treat cached `0 results` as proof that flights, direct routes, round trips, or through fares do not exist.
- Do NOT use the bare `fli` CLI (`fli flights …`) as a substitute — it gives unranked raw results without connection validation, risk scoring, or hub assembly.
- Do not inspect raw `candidates` or `segment_results` in the normal workflow.
- Do not use `--include-candidates` unless debugging; it can create multi-megabyte JSON.
- Do not present summed separate-segment prices as airline/GDS through-fares.
- Do not hide `priority_options` just because they rank below the cheapest or fastest option.

## Pitfalls

1. **`--agent-brief` does not exist.** The current CLI version has no `--agent-brief` flag. Passing it causes an immediate `unrecognized arguments` error. Always read the full JSON output and extract `recommendations` and `ranked_candidates` yourself.
2. **CLI checkout path is unstable.** The flights CLI lives inside a temp checkout (e.g. `/tmp/hermes-*/cli/skill-clis/flights`). Always locate it at runtime with `find` or `which fli`, then `cd` there before running `python3 -m flights_cli`. Do NOT hardcode a path.
3. **Do not bypass this skill.** Raw tools (travelpayouts, bare `fli`) give unranked, unvalidated results. The CLI adds route intelligence, hub assembly, connection validation, and risk scoring. Always use the CLI first — the user expects this workflow and will correct you if you skip it.
4. **`data.agent_report` may be absent.** The current CLI version outputs flat `data.recommendations` and `data.ranked_candidates`, not a nested `data.agent_report` object. Read the top-level keys directly.
5. **FLI airport-name normalization can be wrong.** FLI MCP may return airport names instead of IATA codes (e.g. `Barcelona International Airport`, `Dubai International Airport`, `London Heathrow Airport`). The current adapter can extract the first three letters (`BAR`, `DUB`, `LON`, `CHA`) and assembly may still rank false routes. In debug, inspect `ranked_candidates[].candidate.journeys[].segments` and ensure the final segment destination equals the requested airport (e.g. `BCN`, not `BAR`) before reporting FLI-backed results.

## Debug Escalation

Use debug only when the JSON response is missing, contradictory, or not enough to answer the user. Then read `references/debug-playbook.md` and rerun with targeted debug flags.

## References

- `references/report-contract.md` — how to read and answer from the CLI response.
- `references/source-boundaries.md` — provider limits, cached absence, GDS/through-fare boundaries.
- `references/debug-playbook.md` — when and how to inspect larger CLI JSON safely.