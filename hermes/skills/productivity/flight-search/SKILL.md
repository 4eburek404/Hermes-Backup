---
name: flight-search
version: 0.10.15
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

## Overview

Default path: normalize request → run runtime CLI `route live-assemble --agent-brief` → read `data.agent_report` → answer from the deterministic user-answer renderer.

The active public contracts are `agent_report.v2` and `flight_search_user_answer.v3`. `user_answer.rendered_text` is the canonical user-facing renderer output; `diagnostics.human_answer`, `diagnostics.display`, and `diagnostics.answer_lines` are debug/mirror projections, not fallback final-prose sources. Static catalogs only normalize metadata; cached fare helpers do not validate schedules, availability, connections, ticketing, or provider offers. This skill never books or buys tickets.

## When to Use

Use for live flight search/comparison, direct-service checks, hub/airport choice, carrier-specific availability, baggage/ticketing/protection risk, date-window planning, or explicit flight-search CLI/report maintenance. Also use for immediate bounded travel-mode comparisons after a flight search, such as "а поездом сколько стоит?" on the same route/dates.

Do not use for purchase actions, visa/hotel/ground research, or static fare hints unless explicitly requested as non-validated advisory data. Single-PNR/protection/baggage/fare-rule claims need purchase-screen, airline/GDS, seller, or upstream proof.

## Scenario Decision Map

The CLI has a rich internal surface (17 commands), but agent-facing workflow is a **flow-decision gate plus two-level Golden Path**. Do not start by choosing among commands. First classify the request by intent, market, and evidence requirement; then run one primary command and only targeted follow-up probes. Provider dispatch is automatic inside `route live-assemble` under `--provider-policy auto`: RU-touching segments → KupiBilet, non-RU segments → FLI. The agent does not choose providers unless the user/debug task requires an override.

Mandatory first-pass classes:

- Intent: `route_recommendation`, `direct_inventory`, `ticketing_proof`, `carrier_or_airport_scope`, `adjacent_mode`, or `maintenance`.
- Market: `ru_domestic`, `ru_touching_international`, `global_non_ru`, or `structurally_constrained`.
- Evidence: `shopping_advisory`, `ticketing_required`, `absence_claim`, or `diagnostic_only`.

Important limitation: global non-RU routes must not silently inherit Russia-priority/Moscow controls. If a fully non-RU route plans as `ru-priority`, treat that as a routing limitation and use explicit constraints or label the result advisory/limited. See `references/flow-decision-router.md`.

### Level 1 — Primary Command (after flow decision)

```bash
route live-assemble ORIGIN DEST --depart-date YYYY-MM-DD --profile PROFILE --agent-brief
```

Add `--return-date YYYY-MM-DD` for round trips. Read `data.agent_report` → copy `user_answer.rendered_text` as answer.

### Level 2 — Triggered Follow-ups

| User intent / Trigger | Follow-up command | Notes |
|---|---|---|
| RF internal round trip, need live direct-return confirmation | `kb-roundtrip ORIGIN DEST --depart-date … --return-date … --direct-only` | Single-checkout round-trip evidence for direct return |
| Carrier-specific round trip (e.g. "Аэрофлот туда-обратно") | `kb-roundtrip ORIGIN DEST --depart-date … --return-date … --only-carrier SU` | One-order carrier bundle evidence |
| "Только прямые на неделе XX–YY" | `kb-search --direct-only` (RU) or `fli-search --direct-only` (non-RU) per date | See `references/direct-date-window.md` |
| Carrier exists on route? | `kb-search --only-carrier XX` (RU) or targeted coverage control | Answer carrier scope first, then alternatives |
| Exact-airport direct control (e.g. IST→LHR only) | `fli-search --direct-only` or `--coverage-control exact_airport_direct` | Confirm or deny specific airport |
| "А поездом?" on same route/dates | RZD probe per `references/rail-rzd-live-pricing.md` | Bounded comparison only |
| --agent-brief hides evidence/failed providers, need debug | Re-run with `--agent-report` (keeps full output) | `--agent-brief` trims to `agent_report` only; `--agent-report` keeps `evidence`, `frontier`, `diagnostics` |

### Profile Quick Reference

| Profile | Rank order | Key differences |
|---|---|---|
| `balanced` | reject → risk → price → elapsed | Default. 180–420 min ideal connection. No airport penalties. |
| `business` | reject → risk → elapsed → price | Shorter window (180–360). Penalizes LTN/STN/LGW/SAW. Higher low-cost penalty. |
| `safe` | reject → risk → elapsed → price | Widest connection (210–480). Penalizes SAW. Highest visa/night penalties. |
| `cheap` | reject → price → risk → elapsed | Longest window (150–540). No airport penalties. Lowest all penalties. |

## Maintenance Mode Gate

Default is traveler route search. Do not inspect source/runtime, raw candidates, `doctor`, schemas, or generated artifacts unless failure blocks the search or the user asks to inspect/debug/audit/modify/sync this skill, CLI, or report contract. Use `references/cli-maintenance.md` and `references/debug-playbook.md` in maintenance mode.

Before adding another user-answer/final-answer/report contract, run a cleanup audit: measure `SKILL.md`/references/CLI/schema size, classify contracts as current/legacy/shadow/proposed, check generated artifacts, and prove source/runtime drift. Do not add another v1/v2/v3 layer until the ownership map is clear.

For CLI/report refactor planning, first untangle the current structure before searching for hypothetical future failures: identify the canonical user-visible path, misleading `final_answer`/`human_answer`/`display`/`answer_lines` names, what should be merged vs split, and the exact rename/command taxonomy. Only after that add adversarial weak points, and label them as observed seams or refactor hazards rather than current bugs unless code evidence proves a bug.

## Golden Path

0. If the user follows up with a non-flight price comparison, especially “а поездом сколько?”, keep it bounded to cost/time comparison. For Russian rail, use `references/rail-rzd-live-pricing.md`: resolve stations, query official RZD/pass.rzd both directions by exact dates, calculate round-trip minima by class, then compare against the flight total.
0a. If the user asks for **all direct/nonstop flights over a date window** (“все прямые”, “только прямые”, “на неделе”), treat it as direct inventory, not route recommendation. Follow `references/direct-date-window.md`: expand the range, run bounded provider-live direct-only probes per date, and do not present connected `route live-assemble` alternatives unless the user asks.
1. Normalize exact dates, route scope, named airports, carrier, stops, baggage, timing, ticketing intent, and profile. Preserve named airports (`IST`, `SVO`, `DME`). Arrival deadline without departure date: search latest plausible departure first, then previous date. Default “morning” to before local noon. Treat “avoid Moscow” as soft ranking unless explicit hard filter.
2. Classify flow before command/provider reasoning: intent (`route_recommendation`, `direct_inventory`, `ticketing_proof`, `carrier_or_airport_scope`, `adjacent_mode`, `maintenance`), market (`ru_domestic`, `ru_touching_international`, `global_non_ru`, `structurally_constrained`), and evidence requirement (`shopping_advisory`, `ticketing_required`, `absence_claim`, `diagnostic_only`). Use `references/flow-decision-router.md` when in doubt.
3. Select routing from that flow: `ru_domestic` → `domestic-ru`; `ru_touching_international` → `ru-priority` may be appropriate; `global_non_ru` must not silently use Russia-priority/Moscow controls. If the current CLI plan does so, report the limitation or pass explicit routing/hub constraints instead of presenting it as a neutral global search.
4. Run from runtime skill CLI:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST   --depart-date YYYY-MM-DD   --profile PROFILE   --agent-brief
```

Add `--return-date YYYY-MM-DD` for round trips. Add `--aggregate-control-carrier CARRIER` for carrier tasks. For KupiBilet “туда-обратно одним билетом”, use `kb-roundtrip` first. For simple domestic round trips where a direct candidate is decision-leading, run `kb-roundtrip --direct-only` as a targeted control for live bundles, baggage/hand-luggage packages, seats, and alternative direct return times. Multi-city/open-jaw has no arbitrary live command; use separate assemblies or offline `route validate`/`route rank` and label diagnostic.

4. Read only `data.agent_report`.
5. Read `frontier.offer_graph` first: use `constraints`, `collection`, `evidence`, `missing_evidence`, and `frontier` to decide whether evidence is complete enough. Treat first provider output as progressive evidence; run targeted/polling probes when missing direct/carrier/exact-airport/through-fare evidence can change the recommendation. Stop only on completeness limit, source exhaustion, unchanged decision frontier, or explicit time budget.
6. If `user_answer.rendered_text` is present and valid, copy it as the final answer body without hand-rewriting, re-ranking, summarizing, or “improving” it. Cross-check `frontier.recommended_options`, `frontier.priority_options`, `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` when evidence is degraded or missing. Do not use `diagnostics.human_answer`, `diagnostics.display`, or `diagnostics.answer_lines` as fallback final prose.

## Decision Rules

- Direct-service/date-window requests: follow `references/direct-date-window.md`; answer from provider-live direct inventory by date, list dates with no provider-live direct offer, and do not add external schedule checks unless explicitly requested.
- Profiles: `business` comfort/reliability (heavy airport/cost penalties, ranks risk > elapsed > price); `safe` maximum connection safety (wider buffers, ranks risk > elapsed > price); `balanced` neutral (moderate penalties, default); `cheap` only explicit price-first (no airport penalties, ranks price > risk > elapsed).
- Rank operational frontier first: direct/one-stop, practical airports, safe connections, ticketing/protection, carrier reliability, baggage; price after practicality unless requested otherwise.
- Ticketing evidence: airline/GDS/purchase-screen single booking > provider aggregate without virtual/self-transfer signal > provider aggregate with virtual/interline signal > summed separate segments. Never claim single PNR, baggage-through, or missed-connection protection without proof.
- MCT is a floor, not comfort. Add buffers for terminals, passport/security, baggage, virtual/self-transfer, low-cost terminals, and disruption risk. Very long layovers (~18h+) are fallback/stopover options unless desired.
- Terminal/gate claims require explicit dated fields for exact flights/legs. Same airport/carrier/alliance/hub/terminal-complex does not prove same terminal; if absent, say terminals are unconfirmed.
- Negative direct/carrier claims need targeted controls unless structural constraints prove unavailability. RU-origin/RU-touching international needs Moscow controls (`SVO`/`DME`/`VKO`) before “no good one-stop”. Fully global non-RU routes should not get Moscow/SVO controls by default; if they do, call out the routing limitation instead of normalizing it.
- Carrier-specific or exact-airport tasks: answer that scope first; alternatives separately.
- Suppress artifacts with `ok=false`, `risk.reject=true`, `invalid_time_order`, or negative time. Do not invent missing flight numbers/times/terminals/segments.
- When auditing `user_answer` / renderer contracts, do mutation testing of the final user-visible text, not just schema/happy paths. See `references/user-answer-contract-mutation-audit.md` for concrete mutations: false single-PNR/through-baggage claims, missing caveats, divergent `answer_lines`, contradictory rendered prices/dates, and mode/catalog inconsistencies.

## User Answer Style

- Start with `нашёл`, `не нашёл`, or `evidence неполное`; then recommendation and why.
- Use traveler/dispatcher bullets; no pipe tables; avoid internal labels unless diagnostics are requested.
- Prefer `user_answer.rendered_text` from `flight_search_user_answer.v3`; it is the deterministic renderer projection.
- Round trips / multi-option frontiers use v3 catalog semantics: numbered compact `catalog.items[]`, contiguous numbers, price + outbound/return details, ticketing/protection/baggage risk badges/caveats, and purchase-screen verification when single PNR/baggage-through is unproven.
- Itinerary lines show each segment’s times, differing dates, layover, elapsed time, price, and labels like `ночная`, `прилёт +1`, `длинная стыковка`, `fallback` when relevant.
- Carrier-specific tasks keep carrier scope first; if “ищите ещё”, continue same carrier before broadening.
- Caveats only when decision-relevant: unproven single-PNR/protection/baggage/fare rules, unconfirmed terminals, degraded provider evidence, or narrow probe needed.

## Absence and Error Handling

- Empty provider output is not proof of absence. Classify provider/horizon uncertainty, coverage gap, constraint mismatch, runtime/provider failure, structural unavailability, or ticketing/protection uncertainty.
- If CLI/JSON fails, report the concrete layer and run safe provenance checks. If terminal capture truncates JSON, rerun the same read-only command to `mktemp` under `/tmp`, parse tolerant JSON, read `data.agent_report`, then remove the temp file.
- If a decision-critical option is clipped/missing, run the relevant narrow probe instead of inventing details. Route-family exception patterns live in `references/debug-playbook.md`.

## Cache Freshness and Output Trim Rules

- Default cache TTL = 30 min for provider-live results (`--cache-ttl-seconds`/`--live-cache-ttl-seconds`).
- Use `--no-cache` when: (1) previous search was >60 min ago; (2) user doubts price accuracy; (3) departure date is ≤48h away (dynamic pricing).
- `--agent-brief` trims JSON output to `agent_report` only — `route`, `evidence`, `frontier`, `diagnostics` are dropped. For full output with evidence/frontier, use `--agent-report`. For segment-level detail, add `--include-segment-results N`.

## Common Pitfalls

1. Using cached fare helpers as route search.
2. Treating static catalogs or `doctor` as availability evidence.
3. Overclaiming single PNR, baggage-through, disruption protection, or same terminal.
4. Silently widening named airports to city scope.
5. Pasting raw `display`, diagnostics, JSON, provider boilerplate, or `answer_lines` as final answer.
6. Hiding `priority_options` or carrier/provider aggregates behind generic cheapest/fastest output.
7. Finalizing RU-touching international round trips from `route live-assemble` alone when baggage/PNR/through-fare evidence is weak; targeted `kb-roundtrip` and carrier-specific aggregate controls can materially change the practical recommendation.
8. Calling provider-specific probe commands (`kb-search`, `fli-search`) as the primary search — always start with flow classification, then `route live-assemble`; use probes only as Level 2 follow-ups per the Scenario Decision Map.
9. Treating “international” as one bucket: distinguish RU-touching international from global non-RU before accepting `ru-priority`, SVO/Moscow controls, or Russian provider assumptions.
10. Using `--agent-mode` (legacy) — use `--agent-brief` or `--agent-report` instead.
11. Calling proposed/nonexistent commands from `references/direct-date-window.md` — `route direct-window` is not implemented; use per-date `kb-search --direct-only`/`fli-search --direct-only` instead.
12. Maintenance/refactor pitfalls live in `references/cli-maintenance.md`; ordinary route search should stay traveler-facing.

## Verification Checklist

- [ ] Constraints normalized and route scope preserved.
- [ ] Flow decision made before command/provider reasoning: intent, market, evidence need, and routing strategy are explicit.
- [ ] Runtime `route live-assemble --agent-brief` run, or provenance failure reported before fallback.
- [ ] Answer based on `data.agent_report`; `user_answer.rendered_text` copied when present and valid; `diagnostics.human_answer`, `diagnostics.display`, and `diagnostics.answer_lines` never used as final-prose fallback.
- [ ] `frontier.offer_graph`, `frontier.recommended_options`, `frontier.priority_options`, `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` checked when decision-relevant.
- [ ] Required direct/carrier/exact-airport/Moscow controls or narrow probes run.
- [ ] Ticketing/protection/baggage-through and terminal claims proven or explicitly unconfirmed.
- [ ] Maintenance work verifies source/runtime paths, branch/HEAD/status, versions, backup, parity, tests/doctor, generated artifacts, and reference lifecycle.
- [ ] No per-incident migration/proposal/reference file added when a durable rule belongs in an existing reference or test.

## References

Canonical active references are bounded to six core flight-search directions plus one bounded adjacent-mode note:

- `references/report-contract.md` — `agent_report.v2` read order, contract registry, and user-answer renderer contract.
- `references/source-boundaries.md` — evidence classes, absence, airport/connection boundaries, ticketing, OTA/smart-route semantics.
- `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy. **SSOT for all airport-priority rules** (IST/SAW, London tiers, Moscow MOW/SVO/DME/VBK, Dubai); do not duplicate these rules in other files.
- `references/debug-playbook.md` — targeted probes and route-family exception patterns.
- `references/direct-date-window.md` — direct/nonstop inventory across a bounded date range, including per-date probes and compact output shape. Note: `route direct-window` command is not implemented; use per-date `kb-search --direct-only`/`fli-search --direct-only` instead.
- `references/cli-maintenance.md` — source/runtime sync, schema/tests, provider ports, CLI-surface simplification, dead-code/duplicate cleanup, generated artifacts, and reference lifecycle.
- `references/rail-rzd-live-pricing.md` — RZD public endpoint/RID workflow for bounded train-price comparisons after a flight search.
- `references/flow-decision-router.md` — first-pass intent/market/evidence router for deciding the data flow before choosing commands; includes global non-RU vs RU-touching boundaries and audit signals.
- `references/weakness-audit-2025-06.md` — structural weaknesses found during deep audit: command surface bloat, missing scenario map, dedup gaps, test coverage holes, and recommended fixes.

Do not add standalone migration, incident, audit, handoff, smoke, or proposal references by default. Distill durable rules into the files above or into tests; leave raw history to session search.
