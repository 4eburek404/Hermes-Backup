---
name: flight-search
version: 0.10.13
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

Use for live flight search/comparison, direct-service checks, hub/airport choice, carrier-specific availability, baggage/ticketing/protection risk, date-window planning, or explicit flight-search CLI/report maintenance. Also use for immediate bounded travel-mode comparisons after a flight search, such as “а поездом сколько стоит?” on the same route/dates.

Do not use for purchase actions, visa/hotel/ground research, or static fare hints unless explicitly requested as non-validated advisory data. Single-PNR/protection/baggage/fare-rule claims need purchase-screen, airline/GDS, seller, or upstream proof.

## Maintenance Mode Gate

Default is traveler route search. Do not inspect source/runtime, raw candidates, `doctor`, schemas, or generated artifacts unless failure blocks the search or the user asks to inspect/debug/audit/modify/sync this skill, CLI, or report contract. Use `references/cli-maintenance.md` and `references/debug-playbook.md` in maintenance mode.

Before adding another user-answer/final-answer/report contract, run a cleanup audit: measure `SKILL.md`/references/CLI/schema size, classify contracts as current/legacy/shadow/proposed, check generated artifacts, and prove source/runtime drift. Do not add another v1/v2/v3 layer until the ownership map is clear.

## Golden Path

0. If the user follows up with a non-flight price comparison, especially “а поездом сколько?”, keep it bounded to cost/time comparison. For Russian rail, use `references/rail-rzd-live-pricing.md`: resolve stations, query official RZD/pass.rzd both directions by exact dates, calculate round-trip minima by class, then compare against the flight total.
0a. If the user asks for **all direct/nonstop flights over a date window** (“все прямые”, “только прямые”, “на неделе”), treat it as a direct inventory task, not route recommendation. Follow `references/direct-date-window.md`: expand the date range and run bounded provider-live direct-only probes per date (`kb-search --direct-only` for RU-touching routes, `fli-search --direct-only` for non-RU/global routes, or the proposed/narrow `route direct-window` command when available). Do not split the workflow into schedule-site vs purchase-site layers and do not add airline/airport/aggregator schedule checks unless the user explicitly asks; at this stage the scenario is a CLI provider-live catalog. Do not present ordinary one-stop `route live-assemble` recommendations unless the user asks for alternatives.
1. Normalize exact dates, route scope, named airports, carrier, stops, baggage, timing, ticketing intent, and profile. Preserve named airports (`IST`, `SVO`, `DME`). Arrival deadline without departure date: search latest plausible departure first, then previous date. Default “morning” to before local noon. Treat “avoid Moscow” as soft ranking unless explicit hard filter.
2. Classify market before absence claims: RU domestic, RU-touching international, global non-RU, structurally constrained, or carrier-specific.
3. Run from runtime skill CLI:

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

- Direct-service/date-window requests: after the normal `route live-assemble` provenance check, run targeted `kb-search ORIGIN DEST --direct-only` for each exact date in the requested window when the user asks for “all direct” or a weekly schedule. Report every direct flight found and explicitly list dates with no direct offer in the live result. If a public schedule page is readily available, use it only as a corroborating cross-check for carrier/frequency/flight number, not as purchase/availability proof.
- Profiles: `business` comfort/reliability; `safe` maximum connection safety; `balanced` neutral; `cheap` only explicit price-first.
- Rank operational frontier first: direct/one-stop, practical airports, safe connections, ticketing/protection, carrier reliability, baggage; price after practicality unless requested otherwise.
- Ticketing evidence: airline/GDS/purchase-screen single booking > provider aggregate without virtual/self-transfer signal > provider aggregate with virtual/interline signal > summed separate segments. Never claim single PNR, baggage-through, or missed-connection protection without proof.
- MCT is a floor, not comfort. Add buffers for terminals, passport/security, baggage, virtual/self-transfer, low-cost terminals, and disruption risk. Very long layovers (~18h+) are fallback/stopover options unless desired.
- Terminal/gate claims require explicit dated fields for exact flights/legs. Same airport/carrier/alliance/hub/terminal-complex does not prove same terminal; if absent, say terminals are unconfirmed.
- Negative direct/carrier claims need targeted controls unless structural constraints prove unavailability. RU-origin/RU-touching international needs Moscow controls (`SVO`/`DME`/`VKO`) before “no good one-stop”.
- Carrier-specific or exact-airport tasks: answer that scope first; alternatives separately.
- Suppress artifacts with `ok=false`, `risk.reject=true`, `invalid_time_order`, or negative time. Do not invent missing flight numbers/times/terminals/segments.

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

## Common Pitfalls

1. Using cached fare helpers as route search.
2. Treating static catalogs or `doctor` as availability evidence.
3. Overclaiming single PNR, baggage-through, disruption protection, or same terminal.
4. Silently widening named airports to city scope.
5. Pasting raw `display`, diagnostics, JSON, provider boilerplate, or `answer_lines` as final answer.
6. Hiding `priority_options` or carrier/provider aggregates behind generic cheapest/fastest output.
7. Finalizing RU-touching international round trips from `route live-assemble` alone when baggage/PNR/through-fare evidence is weak; targeted `kb-roundtrip` and carrier-specific aggregate controls can materially change the practical recommendation.
8. Mixing source, runtime, and temporary checkouts without naming the evidence layer.
9. Calling a refactor “complete” or “nothing lost” while source/runtime parity still has semantic diffs.
10. Letting overloaded `--agent-*` flags become a bigger public flag matrix instead of separating search/evidence, decision, and output concerns internally.
11. Letting temporary legacy aliases (`human_answer`, `display`, `answer_lines`, old top-level v1 fields) mask regressions in serialized `agent_report.v2` nested paths.
12. Treating MCP `outputSchema`, prompt text, or `human_answer.text` as the domain contract. The enforceable layer is `flight_search_user_answer.v3` schema + builder + semantic validator + deterministic renderer.
13. Reintroducing provider execution shortcuts: segment and aggregate probes should go through provider adapters/ports, not direct provider-specific branches in `execution/*`.
14. Treating `--agent-brief` as permission to narrow evidence scope. It may trim output only; explicit evidence/search controls must still be honored.
15. Assuming the visible Telegram answer changed just because CLI emitted `user_answer.rendered_text`. If the model rewrites it, user-visible behavior remains old.
16. During CLI maintenance, treating `Protocol` ellipsis methods as dead runtime stubs or treating duplicate local helper names as deletion orders. Classify interface declarations separately, extract only shared behavior, use layer-specific names for different responsibilities, and run focused import/contract tests after each mechanical rename.

## Verification Checklist

- [ ] Constraints normalized and route scope preserved.
- [ ] Runtime `route live-assemble --agent-brief` run, or provenance failure reported before fallback.
- [ ] Answer based on `data.agent_report`; `user_answer.rendered_text` copied when present; `human_answer.text` used only as legacy fallback.
- [ ] `frontier.offer_graph`, `frontier.recommended_options`, `frontier.priority_options`, `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` checked when decision-relevant.
- [ ] Required direct/carrier/exact-airport/Moscow controls or narrow probes run.
- [ ] Ticketing/protection/baggage-through and terminal claims proven or explicitly unconfirmed.
- [ ] Maintenance work verifies source/runtime paths, branch/HEAD/status, versions, backup, parity, tests/doctor, generated artifacts, and reference lifecycle.
- [ ] No per-incident migration/proposal/reference file added when a durable rule belongs in an existing reference or test.

## References

Canonical active references are bounded to five core flight-search directions plus one bounded adjacent-mode note:

- `references/report-contract.md` — `agent_report.v2` read order, contract registry, and user-answer renderer contract.
- `references/source-boundaries.md` — evidence classes, absence, airport/connection boundaries, ticketing, OTA/smart-route semantics.
- `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
- `references/debug-playbook.md` — targeted probes and route-family exception patterns.
- `references/direct-date-window.md` — direct/nonstop inventory across a bounded date range, including per-date probes and compact output shape.
- `references/cli-maintenance.md` — source/runtime sync, schema/tests, provider ports, CLI-surface simplification, dead-code/duplicate cleanup, generated artifacts, and reference lifecycle.
- `references/rail-rzd-live-pricing.md` — RZD public endpoint/RID workflow for bounded train-price comparisons after a flight search.

Do not add standalone migration, incident, audit, handoff, smoke, or proposal references by default. Distill durable rules into the files above or into tests; leave raw history to session search.
