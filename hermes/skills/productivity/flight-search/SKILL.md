---
name: flight-search
version: 0.9.1
description: Use when Codex needs to find, compare, plan, or diagnose flight options with the Hermes flights CLI, including airfare checks, route assembly, hub planning, IATA/date-window searches, Kupibilet live aggregate search, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

## Purpose

Flight-search is the Hermes skill for answering flight-search questions from one compact CLI report. The normal path is deliberately narrow: normalize the request, run `route live-assemble --agent-brief`, read `data.agent_report`, and answer with the best viable option plus required caveats.

The live search path uses:

- Kupibilet for Russia-touching legs and aggregate controls.
- FLI MCP for non-Russia/global legs when the sidecar is available.
- Travelpayouts static catalog files only for city, airport, airline, and aircraft metadata.

Travelpayouts/Aviasales price-search surfaces are retired. Do not start a search with them, and do not treat their absence as route absence; static catalogs remain the only normal Travelpayouts layer.

## Golden Path

1. Normalize the user request:
   - Convert relative dates to exact `YYYY-MM-DD`.
   - Normalize IATA codes and state any typo assumption.
   - Resolve city names to airport scope. For Dubai, default to DXB primary plus DWC secondary; include SHJ only when the user asks for Sharjah, Air Arabia/G9, cheapest UAE-wide options, or a provider result already returns SHJ.
   - Preserve constraints: direct-only, carrier, airport, baggage, timing, price, business/cheap priority.
   - Prefer direct and one-stop journeys; show two-stop only when no viable direct or one-stop exists; never show three-or-more-connection itineraries in normal answers.

2. Run `doctor` once per session or when the CLI environment looks suspect:

```bash
cd ${HERMES_SKILL_DIR}/cli
python3 -m flights_cli --json doctor
```

3. Run the compact live assembly:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business \
  --agent-brief
```

Omit `--return-date` for one-way. Use `--profile cheap` only when the user explicitly asks for cheapest.

`--agent-brief` runs a small non-direct full-route aggregate control so provider-assembled one-PNR-like offers are visible when segment assembly would only see direct legs. Provider offers with 3+ stops or in-path airport changes are cut immediately after provider normalization; the report only keeps compact counts for those suppressed offers. Add `--aggregate-control-carrier SU` when an Aeroflot/SVO or all-SU control is decision-relevant. Repeat for another carrier only when the user asks about that carrier.

4. In normal mode, read only `data.agent_report`:
   - `display`
   - `answer_lines`
   - `recommended_options`
   - `priority_options`
   - `through_fare_checks`
   - `provider_failures`
   - `source_boundaries`
   - `hub_viability`
   - `rejected_pair_warnings`

5. Before answering, sanity-check decision-critical gaps:
   - If a referenced cheapest, fastest, direct, same-carrier/SU, or Moscow-gateway control has no segment details, escalate to targeted debug instead of inventing details.
   - Do not assume `segment_results=[]` means no segment data; full outputs can keep segments under `ranked_candidates[].candidate.journeys[].segments[]`.
   - Before saying “no direct flight”, “carrier does not fly”, or relying on a surprising top rank, run targeted controls: exact-airport direct-only, city-code direct-only when applicable, relevant alternate airport, and carrier aggregate when appropriate.

6. Answer from the report:
   - Use `display.text` verbatim for flight-line output; do not reformat flight numbers, dates, layovers, aircraft, or elapsed time in prose.
   - Lead with the best viable option.
   - Show mandatory controls when present: direct/nonstop, cheapest acceptable, fastest acceptable, same-carrier/SU, Moscow/SVO, or a materially cheaper/slower trade-off.
   - For international routes from Russian origins, include a Moscow/SVO gateway control when plausible, even if a direct flight or another hub option exists.
   - Label overnight or very long layovers as explicit trade-offs for business searches.
   - State provider failures and source boundaries.
   - State that final fare, seats, baggage, protection/single PNR, and fare rules must be verified on the booking screen.

## Skill Resolution Pitfall

Hermes `skills inspect <name>` without a category prefix resolves via ClawHub registry first. Our builtin `flight-search` is at category path `productivity/flight-search`.

- `hermes skills inspect flight-search` → resolves to **ClawHub** (community, different description, different CLI)
- `hermes skills inspect productivity/flight-search` → resolves to **our builtin** (the real skill with Kupibilet/FLI CLI)
- `hermes skills list` shows our version correctly as `builtin`, `enabled`

When verifying skill availability, always use the category-qualified path. When the skill is loaded by the gateway into the system prompt, it uses our builtin version regardless of ClawHub.

## Runtime Rules

- `route live-assemble` works without `TRAVELPAYOUTS_TOKEN`.
- `--provider-policy auto` uses Kupibilet for Russia-touching segments and FLI MCP for non-Russia/global segments.
- If FLI is down or `FLIGHTS_FLI_MCP_URL` is unset, read `provider_failures`; rerun with `--provider-policy kupibilet` only when skipping FLI is a better answer path.
- If Kupibilet is down, report the outage and any partial FLI data. There is no equivalent guaranteed fallback for Russia-touching legs.
- Static catalog refresh is the only normal Travelpayouts surface and requires no Travelpayouts token.

## Retired Price Search

Cached Travelpayouts/Aviasales price-search commands, parser bridges, manual price links, and wrapper examples must stay out of the normal workflow. If a transitional stub remains for compatibility, it must fail closed before credential checks or network I/O and must not be advertised as a search/debug path.

## Error Handling

The CLI returns JSON failures on `stderr` with empty `stdout`:

```json
{"ok": false, "error": {"message": "...", "type": "..."}}
```

- `missing_credentials`: only retired fail-closed price-search stubs can require `TRAVELPAYOUTS_TOKEN`; live assembly and static catalogs do not.
- `validation_error`: bad IATA code, date format, route, flag, or a past departure/return date.
- `upstream_error`: provider HTTP failure, timeout, or unexpected response.
- `error`: generic fallback; read the message.

When testing error cases, parse `stderr` rather than `stdout`, assert `error.type`, and keep the command offline when possible. When `recommended_options` is empty, check `provider_failures` first, then `source_boundaries`, then decide whether targeted debug is needed.

## Do Not

- Do not call retired Travelpayouts/Aviasales price-search helpers before or after CLI live assembly.
- Do not treat cached `0 results`, provider empty responses, or round-trip emptiness as proof that a flight, direct route, carrier route, or through fare does not exist.
- Do not inspect raw `candidates` or `segment_results` in the normal workflow.
- Do not use `--include-candidates` unless debugging; it can create very large JSON.
- Do not present summed separate-segment prices as airline/GDS through-fares.
- Do not hide `priority_options` just because they rank below the cheapest or fastest option.
- Do not surface three-or-more-connection itineraries as recommendations, alternatives, or interesting cheap options.
- Do not use `--agent-mode` in the normal path. Use `--agent-brief`; use `--agent-mode` only for debug JSON.

## Maintenance

When changing the CLI or `agent_report` contract, read `references/cli-maintenance.md` first. Work offline by default, update schema/docs/tests together, keep stdout JSON-clean, and verify with focused tests, full suite, `doctor`, hidden Travelpayouts/Aviasales surface scan, redacted changed-file scan, and pycache cleanup.

When adding live probes, follow `references/source-boundaries.md`: keep fan-out bounded, use provider-aware cache keys, keep in-run request deduplication, and label live/cache/stale evidence.

## References

- `references/report-contract.md` — how to read and answer from `agent_report`.
- `references/source-boundaries.md` — provider limits, cached absence, through-fare boundaries.
- `references/debug-playbook.md` — targeted debug workflow.
- `references/cli-maintenance.md` — CLI maintenance and verification notes.
