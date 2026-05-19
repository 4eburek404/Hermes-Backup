---
name: flight-search
version: 0.10.1
description: Use when Codex needs to find, compare, plan, or diagnose flight options with the Hermes flights CLI, including airfare checks, route assembly, hub planning, IATA/date-window searches, Kupibilet live aggregate search, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

## Purpose

Flight-search answers flight-search questions from one compact CLI report. The normal path is deliberately narrow: normalize the request, run `route live-assemble --agent-brief`, read `data.agent_report`, and answer with the best viable option plus decision-useful caveats.

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

## Golden Path

1. Normalize the user request:
   - convert relative dates to exact `YYYY-MM-DD`;
   - normalize IATA codes, city scope, exact airports, cabin, passengers, profile, carrier, direct-only, timing, baggage, and price constraints;
   - preserve named-airport constraints instead of silently widening to a city code;
   - choose the profile from the policy below.
2. Classify the route family before interpreting missing direct service or provider absence:
   - RU domestic;
   - RU-touching international;
   - global non-RU;
   - structurally constrained market;
   - carrier-specific question.
3. Run compact live assembly:

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile PROFILE \
  --agent-brief
```

4. Read only `data.agent_report`.
5. Answer from:
   - `display`;
   - `answer_lines`;
   - `recommended_options`;
   - `priority_options`;
   - `through_fare_checks`;
   - `provider_failures`;
   - `source_boundaries`.

Use `doctor` only when environment provenance looks suspect; it is not an answer source.

## Decision Rules

- Profile policy:
  - use `business` when the user prioritizes business travel, comfort, predictability, or reliability and the current CLI supports it;
  - use `safe` when the user explicitly wants maximum connection safety;
  - use `balanced` for neutral intent;
  - use `cheap` only when the user explicitly asks for cheapest or price-first options.
- Stop policy:
  - prefer direct and one-stop journeys;
  - show two-stop only when no viable direct/one-stop exists or the report explicitly marks fallback/reportability;
  - do not recommend three-or-more-connection itineraries in normal answers.
- Negative direct or carrier claims require targeted direct/carrier controls unless stable route-level constraints already make the route structurally unavailable.
- For carrier-specific questions, answer the carrier-route question first, then show alternatives.
- For domestic RU routes with viable direct options, do not bury objectively cheaper/faster direct flights behind hub or carrier preference.
- For RU-origin international routes, keep coherent Moscow/SVO controls visible when the report marks them as viable and decision-relevant.
- Use `display.text` verbatim for itinerary lines; it already carries flight lines, layovers, and total elapsed time.

## Absence and Caveat Discipline

- Empty provider output is not proof of absence by itself. Use that as an internal evidence rule, not as a generic final-answer disclaimer.
- Separate provider/horizon uncertainty, provider coverage gaps, constraint mismatches, runtime/provider failures, structural unavailability, and ticketing/protection uncertainty.
- When stable route-level constraints make regular nonstop service structurally unavailable, state the practical conclusion directly and move to viable connecting options.
- Do not phrase structurally constrained markets as "the provider did not prove absence" when the useful traveler answer is that direct service is not available in normal booking channels.
- Provider-boundary caveats belong in the final answer only when they change the user's decision or explain degraded evidence.
- Final answers must be traveler-useful, not tool-diagnostic.

## Runtime Rules

- Respect `source_boundaries` and `provider_failures` from `data.agent_report`, but do not automatically print them.
- Current live provider policy chooses the source mix. Do not hardcode provider assumptions beyond what the report states.
- Through-fare, single-PNR, baggage-through, refund, and disruption-protection claims require proof from `through_fare_checks` or the purchase screen.
- Static catalogs normalize names, codes, geography, carrier/alliance labels, and aircraft labels. They do not prove schedules, fares, seat availability, direct service, or carrier service.

## Error Handling

- If the CLI fails or JSON cannot be parsed, report the concrete failure layer and rerun only safe provenance commands.
- If a provider fails, read `provider_failures` and explain degraded evidence only when it is decision-relevant.
- If a route or date appears unavailable, classify the absence before answering.
- If a requested constraint is not satisfied by the report, say which field proves that and what targeted live probe would reduce uncertainty.
- If the compact report clips a decision-critical cheapest, fastest, direct, same-carrier, carrier-requested, or Moscow-control option, escalate to debug instead of inventing details.

## Do Not

- Do not answer from static catalogs as flight availability.
- Do not print generic provider-boundary disclaimers when a stronger route-level conclusion is available.
- Do not surface three-or-more-connection routes as recommendations, alternatives, or interesting cheap options.
- Do not present summed separate-segment prices as confirmed airline/GDS through fares.
- Do not hide `priority_options` just because they rank below the cheapest or fastest option.
- Do not add historical migration narratives to active Markdown.
- Do not use old or deprecated provider paths.
- Do not inspect raw candidates or segment dumps in the normal workflow.

## References

- `references/report-contract.md` - how to read `data.agent_report` into a user answer.
- `references/source-boundaries.md` - source limits, absence taxonomy, airport boundaries, and proof boundaries.
- `references/debug-playbook.md` - targeted diagnostics for current live report behavior.
- `references/cli-maintenance.md` - maintenance invariants and validation checklist.
