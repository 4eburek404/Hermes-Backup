---
name: flight-search
version: 0.10.10
description: Use when Codex needs to find, compare, plan, or diagnose flight options with the Hermes flights CLI, including airfare checks, route assembly, hub planning, IATA/date-window searches, KupiBilet live aggregate search, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

## Overview

Flight-search answers flight-search questions from one compact CLI report. The normal path is deliberately narrow: normalize the request, run `route live-assemble --agent-brief`, read `data.agent_report`, and answer with the best viable option plus decision-useful caveats.

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

This skill also owns maintenance of its bundled CLI and report contracts. For user answers, run the runtime CLI in the Golden Path. For source or CLI maintenance, verify source/runtime provenance first and use `references/cli-maintenance.md`.

## When to Use

Use this skill when:

- the user asks to find, compare, check, or explain flight options, direct service, route availability, hubs, airports, dates, cabins, baggage, carrier choice, or ticketing/protection risk;
- the task needs IATA/city normalization, route assembly, KupiBilet/FLI live provider checks, or date-window/hub planning;
- the user asks to diagnose, maintain, audit, or improve the flight-search CLI, `data.agent_report`, schemas, provider policy, or source/runtime sync.

Do not use it for:

- buying or booking tickets; final purchase, fare rules, baggage-through, refund, and disruption protection require purchase-screen or airline/GDS proof;
- non-live advisory fare lookups when the user explicitly asks for static fare hints rather than route planning; label those as advisory data and do not treat them as validated itineraries;
- general visa, hotel, ground-transfer, or destination research unless it directly affects a flight-search decision.

## Golden Path

1. Normalize the user request:
   - convert relative dates to exact `YYYY-MM-DD`;
   - normalize IATA codes, city scope, exact airports, cabin, passengers, profile, carrier, direct-only, timing, baggage, and price constraints;
   - preserve named-airport constraints instead of silently widening to a city code;
   - capture ticketing intent: single-ticket/airline-responsible connection, provider aggregate offer, virtual/self-transfer tolerance, baggage, and carrier quality;
   - if the user gives an arrival deadline but no outbound departure date (for example “прилёт не позже утра 15-го”), search the latest plausible departure date first and, if needed, the previous date; treat “утро” as an explicit assumption (default: before local noon) unless the user supplied a stricter time;
   - capture airport/region preferences such as “avoid Moscow” as a ranking/selection constraint, not as an absolute hard filter unless the user says so; keep Moscow controls as fallback evidence but do not bury workable non-Moscow options;
   - choose the profile from the policy below.
2. Classify the route family before interpreting missing direct service or provider absence:
   - RU domestic;
   - RU-touching international;
   - global non-RU;
   - structurally constrained market;
   - carrier-specific question.
3. Run compact live assembly from the runtime skill CLI:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile PROFILE \
  --agent-brief
```

For round trips, add `--return-date YYYY-MM-DD`; the live assembly builds outbound and return journeys and round-trip candidate generation requires both directions.

Important Kupibilet round-trip parity rule: `kb-roundtrip` is the preferred narrow probe when the user specifically wants a KupiBilet-style single round-trip order / "туда-обратно одним билетом". It queries Kupibilet `frontend_search` with two `trips` entries (`origin→destination` on depart date and `destination→origin` on return date) and filters variants whose two `segments` match the requested carrier/flights. Treat that result as the provider's round-trip checkout offer; do not answer from summed one-way `kb-search` or `route live-assemble` directional candidates when the two-trip provider result is available. See `references/kupibilet-roundtrip-cli.md` for command shape, semantics, and verification.

For carrier-specific questions (Aeroflot/SU-only, Ural/U6-only, etc.), add `--aggregate-control-carrier CARRIER` to the `route live-assemble` command and treat the resulting provider aggregate controls as the primary carrier-existence evidence. `coverage_diagnostics.planned_controls` may list carrier probes that were not executed; do not read `not_executed` as empty-provider evidence. If the compact report still lacks carrier details, run narrow `kb-search ORIGIN DEST --only-carrier CARRIER` probes for the full route and exact hub legs (for example `SVX→SVO`, `SVO→MSQ`, `MSQ→SVO`, `SVO→SVX`).

The runtime CLI does not currently expose a ready multi-city/open-jaw live-search command or arbitrary leg-list parser. For multi-city/open-jaw work, run separate route assemblies per city pair or use offline `route validate`/`route rank` on manually supplied `journeys` JSON, and label it as diagnostic rather than validated live multi-city search. For dry `route plan` diagnostics on reverse RU-touching legs (for example China city → SVX), inspect generated segment commands: auto `ru-priority` can surface Moscow/IST control segments that are useful as coverage probes but not clean one-stop itinerary paths; when the decision requires specific hubs, rerun with explicit `--hub SVO --hub IST --hub DXB` (or the user’s hubs) and treat that as targeted planning evidence, not ticket availability.

If the runtime import/path fails or provenance looks suspect, use `references/debug-playbook.md` → `Runtime Provenance`; do not silently fall back to another checkout and report that as the user-facing result.

4. Read only `data.agent_report`.
5. Answer from `human_answer.text` when present; it is the deterministic provider-neutral traveler-facing renderer. Cross-check decision-critical details against:
   - `recommended_options`;
   - `priority_options`;
   - `through_fare_checks`;
   - `provider_failures`;
   - `source_boundaries`;
   - `display` / `answer_lines` as evidence/debug inputs only.

Use `doctor` only when environment provenance looks suspect; it is not an answer source.

## Decision Rules

- Ticketing frontier policy:
  - search and rank unified/provider-aggregate offers before relying on segment-by-segment assembly when the user cares about missed-connection responsibility;
  - classify ticketing evidence for each serious option: airline/GDS/purchase-screen single booking proven > provider aggregate with one variant/price and no virtual/self-transfer signal > provider aggregate with `virtual_connection`/virtual-interline signal > CLI-summed separate segments;
  - do not call a route "single PNR" until a booking screen, airline/GDS fare, fare rules, or route receipt proves it;
  - a provider aggregate can be one seller checkout while still not proving airline through-check, baggage-through, or disruption liability.
- MCT discipline:
  - use airport/carrier Minimum Connection Time as the technical floor for connection feasibility; prefer exact airport evidence over generic buffers;
  - for borderline or decision-critical connections, consult `https://minimumconnectiontime.com/airport/IATA` (and airline/GDS/IATA data when available) before judging the connection;
  - MCT is a legal/technical minimum, not a business-comfort target; add operational buffer for large terminals, passport/security, baggage, virtual/self-transfer, low-cost terminals, or irregular operations;
  - ordinary overnight waits can be acceptable only when they create a deliberate airport-hotel + morning onward pattern; show this as a comfort/operations trade-off, not an automatic rejection;
  - very long layovers (about 18h+; e.g. 23h) are not quality/reliability options by themselves. Classify them as forced stopover/fallback choices unless the user explicitly wants a stopover or the alternative risk is materially worse.
- Terminal/gate evidence discipline:
  - terminal letters/numbers are operational facts, not airline/airport metadata; do not infer terminals from airport code, same carrier, alliance, hub, "north/south terminal complex", or historical carrier-move narratives;
  - if `data.agent_report` or provider output lacks explicit terminal fields, say `терминалы не подтверждены`, not "same terminal";
  - a same-terminal claim requires explicit same terminal code for each relevant flight/leg from a dated provider, airline, airport, GDS, or booking-screen source for the exact travel date; "same airport" is not terminal-continuity proof;
  - for decision-critical or tight connections, verify terminals with a targeted current source before judging risk, and if terminal proof is unavailable, rank with a conservative large-airport buffer and state the uncertainty;
  - gate numbers are day-of operational data and usually not stable enough for planning; use them only as live day-of evidence, not advance itinerary proof.
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
- For RU-origin/RU-touching international routes, explicitly check Moscow one-stop controls (SVO/DME/VKO) before concluding that no good one-stop options exist; keep Moscow controls visible as a separate yes/no finding even when the compact report ranks non-Moscow options first.
- Use `display.text` / `display.options` as evidence for itinerary details only when they match the user’s requested scope and carry sufficient details; do not copy the whole display block as the final answer if it would violate `## User Answer Style`.
- For carrier-specific or exact-airport questions, do not let generic/global `display.text` override carrier-matching evidence. Cross-check `recommended_options` and `priority_options`; if the requested carrier appears only as `provider_aggregate_candidate` / directional priority options, answer the carrier question from those entries (especially `user_facing_label`, price, itinerary elapsed, layover total, direction, ticketing note) and label them as directional/provider-aggregate candidates, not full round-trip proof.
- If `display.text` says details are not included or the priority option has `segments: []`, do not invent flight numbers/times. Use fields already present in the option; when exact flight numbers or leg timing are decision-critical, run narrow carrier/leg debug probes (`kb-search ... --only-carrier CARRIER` for the full route and likely hub legs) or state the evidence gap.
- Before surfacing multiple `display.options`, cross-check the matching `recommended_options`/`priority_options` entries and suppress any option with `ok=false`, `risk.reject=true`, `invalid_time_order`, or negative connection time; compact display can include invalid ranked artifacts during degraded/debug searches.

## User Answer Style

- Start with the operational answer, not the tool narrative: `нашёл / не нашёл / evidence неполное`, then the recommended choice and why.
- Write for a traveler/dispatcher, not as a JSON field dump. Do not expose internal labels such as `#`, `rank`, `probe_id`, `provider_aggregate_candidate`, or `coverage_diagnostics` unless the user asks for diagnostics.
- Telegram format: avoid pipe tables. Use compact bullets with one itinerary per line and no blank line between every field.
- For round trips, default structure:
  1. **Лучшая пара / рекомендация** — outbound line, return line, total price, ticketing/protection caveat.
  2. **Альтернативы туда** — each viable one-way option on one line.
  3. **Альтернативы обратно** — each viable one-way option on one line.
  4. **Отсекаю / fallback** — only if useful: very long layovers, unprotected/self-transfer, multi-stop, or non-matching carriers.
  5. **Проверить перед покупкой** — single PNR/protection, baggage-through, fare rules, terminals if connection risk matters.
- Preferred itinerary-line shape is built by `human_answer_renderer.py`, not by agent prose: `SU1437 18:10–18:55 → SU1844 20:35–21:55 | 01 авг | SVO 1ч40 | всего 5ч45 | 16 664 ₽`. Departure and arrival time must be visible for each flight/segment; do not collapse a connection into only the first departure and final arrival (`SU1437→SU1844 | 01 авг 18:10–21:55`). If a later segment departs on a different calendar date, include that segment date inline, e.g. `DP6544 05:30–06:00 → B2976 02 авг 09:50–11:15 | 01 авг | ...`. Add short labels such as `ночная`, `прилёт +1`, `длинная стыковка`, `fallback` when they change the decision.
- For carrier-specific questions, answer the carrier-route result first and keep the carrier scope visible: `Аэрофлот/SU: найдено ...`; do not broaden to other carriers in the main answer unless the user asks or alternatives materially change the recommendation. If the user says “ищите ещё” after a carrier-specific result, continue in the same carrier scope first; broaden only as a clearly separated section.
- Do not write “это всё, что есть” unless the exact carrier/full-route controls were executed and the evidence boundary is stated. Prefer `агрегатор сейчас показывает такие SU-кандидаты` when evidence is provider-bounded.
- Use diagnostic caveats sparingly and decision-usefully: `single PNR/багаж не доказаны — проверить на booking screen` is useful; raw provider-boundary text is not.
- For one-ticket round-trip requests, separate carrier existence from ticketing proof: two one-way options on the same carrier are still only one-way evidence until booking-screen or fare-rule proof shows a single round-trip purchase.
- If the report lacks flight numbers, terminals, or segment times, say what is missing and run a narrow probe when decision-critical. Do not invent details to make the answer look complete.

## Absence and Caveat Discipline

- Empty provider output is not proof of absence by itself. Use that as an internal evidence rule, not as a generic final-answer disclaimer.
- Separate provider/horizon uncertainty, provider coverage gaps, constraint mismatches, runtime/provider failures, structural unavailability, and ticketing/protection uncertainty.
- When stable route-level constraints make regular nonstop service structurally unavailable, state the practical conclusion directly and move to viable connecting options.
- Do not phrase structurally constrained markets as "the provider did not prove absence" when the useful traveler answer is that direct service is not available in normal booking channels.
- Provider-boundary caveats belong in the final answer only when they change the user's decision or explain degraded evidence.
- Final answers must be traveler-useful, not tool-diagnostic.

## Runtime Rules

- Respect `source_boundaries` and `provider_failures` from `data.agent_report`, but do not automatically print them.
- Current live provider policy chooses the source mix. Do not hardcode provider assumptions beyond what the report states. Provider-aware airport priority rules live in `references/provider-aware-airport-priority.md`.
- Through-fare, single-PNR, baggage-through, refund, and disruption-protection claims require proof from `through_fare_checks`, provider raw ticketing fields, or the purchase screen.
- `--ticketing single` is not proof of a protected single PNR; it can change connection feasibility thresholds, but the final answer must still say protection/baggage-through/fare rules are unproven unless `through_fare_checks`, provider raw ticketing fields, or the booking screen prove them.
- Treat raw `virtual_connection` / virtual-interline signals as a separate evidence class: useful discovery, but not airline-responsible through-ticket proof unless the seller/airline explicitly provides missed-connection protection.
- Static catalogs normalize names, codes, geography, carrier/alliance labels, and aircraft labels. They do not prove schedules, fares, seat availability, direct service, or carrier service.

## Error Handling

- If the CLI fails or JSON cannot be parsed, report the concrete failure layer and rerun only safe provenance commands.
- If direct terminal capture of the CLI JSON fails to parse because of truncation/control characters, rerun the same provider-read-only search redirecting stdout to a `mktemp` file under `/tmp`, parse it with tolerant JSON loading (for example Python `json.loads(text, strict=False)`), read `data.agent_report`, and remove the temp file when no longer needed; do not inspect raw segment dumps unless escalating to debug.
- If a provider fails, read `provider_failures` and explain degraded evidence only when it is decision-relevant.
- If a route or date appears unavailable, classify the absence before answering.
- If a requested constraint is not satisfied by the report, say which field proves that and what targeted live probe would reduce uncertainty.
- If the compact report clips a decision-critical cheapest, fastest, direct, same-carrier, carrier-requested, avoid-Moscow/non-Moscow, or Moscow-control option, escalate to debug instead of inventing details.
- For RU→China requests with a soft “avoid Moscow” constraint and an arrival deadline, see `references/china-avoid-moscow-arrival-deadline.md` for the targeted probe pattern: run the compact report for primary airports/dates, then narrow `kb-search` with a larger limit and post-filter for Moscow airports, arrival cutoff, and stop count.

## Skill-Owned CLI Maintenance Checks

Use this when the user asks about this skill's version, whether a backup/source copy matches runtime, or whether the bundled CLI footprint is justified.

- Verify provenance before answering: compare the runtime skill root (`$HERMES_HOME/skills/productivity/flight-search`, usually `$HOME/.hermes` + `/skills/productivity/flight-search`) with the relevant source/backup root, including branch/status when the source is a git repo.
- Compare `SKILL.md` frontmatter version, SHA-256/bytes for changed files, file-set equality, and a concise diff/stat for differing files before saying versions or content match.
- Keep detailed maintenance, source/runtime sync, generated-artifact, and schema-layout rules in `references/cli-maintenance.md`.

## Human Answer Renderer Maintenance

Use this when improving final user-visible flight output. The provider-neutral seam is `data.agent_report` -> `human_answer` -> Telegram/Markdown answer; do not copy provider-specific plugin formatter wording one-to-one.

- Implement final-output changes in `cli/flights_cli/reporting/human_answer_renderer.py`, not by making agents copy `display.text`, `answer_lines`, or debug labels.
- Keep `human_answer` in `cli/flights_cli/contracts/agent_report.v1.schema.json` and `cli/tests/test_agent_report_contract.py` synchronized with renderer changes.
- Preserve provider neutrality: renderer input is normalized report fields, not Travelpayouts/KupiBilet/FLI client objects, cache semantics, booking URLs, or provider caveat text.
- Test for negative format guarantees: no `agent report:`, `Best CLI-ranked option`, `Coverage diagnostics`, `provider_aggregate_candidate`, `provider-aggregate:`, pipe tables, or raw `probe_id` in user-facing text.
- For round trips, test the exact answer shape: recommendation pair first, then outbound alternatives, return alternatives, and decision-useful purchase checks; sections should be separated as readable Telegram blocks, not field-by-field dumps.
- For connected itineraries, tests must assert per-segment flight times such as `SU1437 18:10–18:55 → SU1844 20:35–21:55`, reject collapsed whole-journey ranges such as `SU1437→SU1844 | 01 авг 18:10–21:55`, and cover overnight/multi-day layovers where a later segment date must be visible inline (`B2976 02 авг 09:50–11:15`).
- After renderer changes run `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_human_answer_renderer.py tests/test_agent_report_contract.py tests/test_final_answer_contract.py tests/test_flight_display.py tests/test_provider_aggregate_candidates.py -q`, then the full `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q` before reporting completion.

## Do Not

- Do not answer from static catalogs as flight availability.
- Do not print generic provider-boundary disclaimers when a stronger route-level conclusion is available.
- Do not surface three-or-more-connection routes as recommendations, alternatives, or interesting cheap options.
- Do not present summed separate-segment prices as confirmed airline/GDS through fares.
- Do not present same-airport, same-carrier, or same terminal-complex facts as "same terminal" unless explicit terminal fields prove it for the exact flights/date.
- Do not hide `priority_options` just because they rank below the cheapest or fastest option.
- Do not add historical migration narratives to active Markdown.
- Do not override the active provider and airport-priority policy documented in `references/provider-aware-airport-priority.md`.
- Do not inspect raw candidates or segment dumps in the normal workflow.

## Common Pitfalls

1. **Using static advisory fare helpers as route search.** The normal answer path is `route live-assemble --agent-brief`; non-live fare helper output does not validate connections, ticketing risk, hub viability, or provider aggregate offers.
2. **Treating metadata or doctor output as flight evidence.** Static catalogs and `doctor` prove environment/catalog facts only, not schedules, fares, seats, direct service, or availability.
3. **Overclaiming ticketing protection.** `--ticketing single`, same-carrier legs, and provider aggregate offers do not prove airline-responsible single PNR, baggage-through, or missed-connection protection without purchase-screen, airline/GDS, fare-rule, or explicit upstream proof.
   - For one-ticket round-trip requests, two separate one-way offers on the same carrier are still only one-way evidence until booking-screen or fare-rule proof shows a single round-trip purchase.
4. **Silently widening airports.** Preserve named-airport constraints such as `IST`, `LHR`, `SVO`, `DME`, or `VKO`; city-code scope is not airport-continuity proof.
5. **Surfacing invalid compact artifacts.** Cross-check `display.options` against `recommended_options` / `priority_options` and suppress options with `ok=false`, rejection risk, invalid time order, or negative connection time.
6. **Falling back to an unproven checkout.** If runtime import/path is suspect, run the provenance checks in `references/debug-playbook.md`; do not mix source, runtime, and temporary checkouts in one answer without naming the evidence layer.
7. **Printing tool diagnostics instead of travel advice.** Provider failures and source boundaries belong in the answer only when they change the decision or explain degraded evidence.
8. **Hallucinating terminals.** Airport code, same carrier, hub status, or a shared terminal complex do not prove same terminal. If explicit terminal fields are absent, state that terminals are unconfirmed and use conservative large-airport connection risk.

## Verification Checklist

- [ ] User constraints normalized: exact date, origin/destination scope, named airports, passengers, cabin, profile, carrier, stops, baggage, timing, and ticketing intent.
- [ ] `route live-assemble --agent-brief` run from the runtime CLI, or runtime provenance failure reported before any fallback.
- [ ] JSON parsed and answer based on `data.agent_report`, not raw segment dumps or static catalogs.
- [ ] `recommended_options`, `priority_options`, `through_fare_checks`, `provider_failures`, and `source_boundaries` checked before final wording.
- [ ] Direct, carrier-specific, exact-airport, or Moscow one-stop controls run or verified when the decision rules require them.
- [ ] Ticketing/protection/baggage-through claims backed by proof or explicitly labeled as unproven.
- [ ] Terminal claims backed by explicit dated terminal fields for the exact flights/date, or labeled as unconfirmed and ranked with conservative airport-transfer risk.
- [ ] Caveats are decision-useful and traveler-facing; generic provider disclaimers omitted when a stronger route-level conclusion exists.
- [ ] For CLI/source maintenance: source/runtime paths, branch/HEAD/status, version markers, focused tests/doctor, generated artifacts, and parity/sync scope verified.

## References

- `references/report-contract.md` - how to read `data.agent_report` into a user answer.
- `references/final-answer-rendering-rca.md` - RCA and fix pattern for raw/debug flight output leaking into Telegram answers or hiding carrier-specific controls.
- `references/source-boundaries.md` - source limits, absence taxonomy, airport boundaries, and proof boundaries.
- `references/debug-playbook.md` - targeted diagnostics for current live report behavior.
- `references/cli-maintenance.md` - maintenance invariants and validation checklist.
- `references/provider-aware-airport-priority.md` - active provider scope, IST/LON/MOW airport priority, KupiBilet/FLI dispatch boundaries, RU-priority validation, and smoke invariants.
- `references/round-trip-ticketing-evidence.md` - evidence hierarchy and wording for carrier-specific one-ticket round-trip requests.
- `references/kupibilet-roundtrip-cli.md` - `kb-roundtrip` command shape, provider semantics, baggage handling, and verification after CLI maintenance.
- `references/kupibilet-feature-research.md` - KupiBilet public feature/add-on research, operational interpretation of smart routes, payments/refunds/bonuses, and runtime CLI evidence for `frontend_search`.
