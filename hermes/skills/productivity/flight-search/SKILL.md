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

Default path: normalize request → run runtime CLI `route live-assemble --agent-brief` → read `data.agent_report` → answer as traveler/dispatcher with best viable option and caveats.

Static catalogs only normalize metadata; cached fare helpers do not validate schedules/availability/connections/ticketing/provider offers. This skill never books or buys tickets.

## When to Use

Use for live flight search/comparison, direct-service checks, hub/airport choice, carrier-specific availability, baggage/ticketing/protection risk, date-window planning, or this CLI/report maintenance. Also use it for flight-search CLI/report redesign audits: decompose overloaded agent/output/evidence behavior before proposing code changes, and use `references/cli-redesign-governance.md` plus `references/agent-report-v2-migration.md` for the target architecture. Also use it for immediate *travel-mode comparison follow-ups* after a flight search, such as “а поездом сколько стоит?” on the same route/dates: keep the answer as a cost/time comparison, not a full rail-booking workflow. Do not use for purchase actions, visa/hotel/ground research, or static fare hints unless explicitly requested as non-validated advisory data. Single-PNR/protection/baggage/fare-rule claims need purchase-screen/airline/GDS/seller/upstream proof.

## Maintenance Mode Gate

Default is traveler route search. Do not inspect source/runtime, raw candidates, `doctor`, schemas, or generated artifacts unless failure blocks search or the user asks to inspect/debug/audit/modify/sync this skill, CLI, or report contract. Use `references/cli-maintenance.md` / `references/debug-playbook.md`.

## Golden Path

0. If the user follows up on a completed flight search with a non-flight price comparison (especially rail: “а поездом сколько?”), do a bounded adjacent comparison instead of rerunning the flight frontier. For Russian rail, use `references/rail-rzd-live-pricing.md` as the canonical bounded rail reference: resolve station codes, query both directions by exact dates through official RZD/pass.rzd, calculate round-trip minima by class, then compare against the already-found flight total with travel-time trade-off. Do not create or rely on an external docs file for this rail source policy.
1. Normalize exact dates, route scope, named airports, carrier, stops, baggage, timing, ticketing intent, profile. Preserve named airports (`IST`, `SVO`, `DME`). Arrival deadline without departure date: search latest plausible departure first, then previous date; default “morning” to before local noon. Treat “avoid Moscow” as soft ranking unless explicit hard filter.
2. Classify market before absence claims: RU domestic, RU-touching international, global non-RU, structurally constrained, or carrier-specific.
3. Run from runtime skill CLI:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile PROFILE \
  --agent-brief
```

Add `--return-date YYYY-MM-DD` for round trips. Add `--aggregate-control-carrier CARRIER` for carrier tasks; if incomplete, run narrow `kb-search ORIGIN DEST --only-carrier CARRIER` for full route and likely hub legs. For KupiBilet “туда-обратно одним билетом”, use `kb-roundtrip` first. For simple domestic round trips where a direct candidate is decision-leading, run `kb-roundtrip --direct-only` as a targeted control to verify live round-trip bundles, baggage/hand-luggage packages, seats, and alternative direct return times; this often gives cleaner purchase-screen candidates than summed one-way segment prices. Multi-city/open-jaw has no arbitrary live command; use separate assemblies or offline `route validate`/`route rank` and label diagnostic.

4. Read only `data.agent_report`.
5. Read `frontier.offer_graph` first: use `constraints` to preserve scope, `collection`/`evidence`/`missing_evidence` to decide whether evidence is complete enough, and `frontier.offer_graph.frontier` to keep mandatory alternatives visible. Treat first provider output as progressive evidence: run targeted/polling probes when missing direct/carrier/exact-airport/through-fare evidence can change the recommendation; stop only on completeness limit, source exhaustion, unchanged decision frontier, or explicit time budget.
6. Use `user_answer.rendered_text` as the canonical renderer output when present; `human_answer.text` is only a legacy projection/fallback and must mirror `user_answer.rendered_text` during migration. Cross-check `frontier.recommended_options`, `frontier.priority_options`, `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` when `frontier.offer_graph` shows degraded or missing evidence. `diagnostics.display`/`diagnostics.answer_lines` are evidence/debug inputs, not final prose. `doctor` is provenance only.

## Decision Rules

- Profiles: `business` comfort/reliability; `safe` maximum connection safety; `balanced` neutral; `cheap` only explicit price-first.
- Rank operational frontier first: direct/one-stop, practical airports, safe connections, ticketing/protection, carrier reliability, baggage; price after practicality unless requested otherwise.
- Ticketing evidence: airline/GDS/purchase-screen single booking > provider aggregate without virtual/self-transfer signal > provider aggregate with virtual/interline signal > summed separate segments. Never claim single PNR, baggage-through, or missed-connection protection without proof.
- MCT is a floor, not comfort. Add buffers for terminals, passport/security, baggage, virtual/self-transfer, low-cost terminals, and disruption risk. Very long layovers (~18h+) are fallback/stopover options unless desired.
- Terminal/gate claims require explicit dated fields for exact flights/legs. Same airport/carrier/alliance/hub/terminal-complex does not prove same terminal; if absent, say terminals are unconfirmed.
- Negative direct/carrier claims need targeted controls unless structural constraints prove unavailability. RU-origin/RU-touching international needs Moscow controls (SVO/DME/VKO) before “no good one-stop”.
- Carrier-specific or exact-airport tasks: answer that scope first; alternatives separately.
- Suppress artifacts with `ok=false`, `risk.reject=true`, `invalid_time_order`, or negative time. Do not invent missing flight numbers/times/terminals/segments.

## User Answer Style

- Start with `нашёл`, `не нашёл`, or `evidence неполное`; then recommendation and why.
- Use traveler/dispatcher bullets; no pipe tables; avoid internal labels unless diagnostics are requested.
- Round trips: **Лучшая пара / рекомендация**, **Альтернативы туда**, **Альтернативы обратно**, **Отсекаю / fallback** if useful, **Проверить перед покупкой**. If a targeted `kb-roundtrip` control materially changes price or baggage packages versus `human_answer.text`, prefer the live round-trip bundle in the recommendation and state baggage/hand-luggage explicitly.
- Itinerary lines show each segment’s times, differing dates, layover, elapsed time, price, and labels like `ночная`, `прилёт +1`, `длинная стыковка`, `fallback` when relevant.
- Carrier-specific tasks keep carrier scope first; if “ищите ещё”, continue same carrier before broadening.
- Caveats only when decision-relevant: unproven single-PNR/protection/baggage/fare rules, unconfirmed terminals, degraded provider evidence, or narrow probe needed.

## Absence and Error Handling

- Empty provider output is not proof of absence. Classify provider/horizon uncertainty, coverage gap, constraint mismatch, runtime/provider failure, structural unavailability, ticketing/protection uncertainty.
- If CLI/JSON fails, report concrete layer and run safe provenance checks. If terminal capture truncates JSON, rerun the same read-only command to `mktemp` under `/tmp`, parse tolerant JSON, read `data.agent_report`, then remove the temp file.
- If a decision-critical option is clipped/missing, run the relevant narrow probe instead of inventing details. Route-family exception patterns (including RU→China avoid-Moscow arrival deadlines) live in `references/debug-playbook.md`.

## Common Pitfalls

1. Cached fare helpers as route search.
2. Static catalogs/`doctor` as availability evidence.
3. Overclaiming single PNR, baggage-through, disruption protection, or same terminal.
4. Silently widening named airports to city scope.
5. Pasting raw `display`, diagnostics, JSON, or provider boilerplate as final answer.
6. Hiding `priority_options` or carrier/provider aggregates behind generic cheapest/fastest output.
7. Mixing source, runtime, and temporary checkouts without naming evidence layer.
8. Replacing overloaded `--agent-*` behavior with a larger public flag matrix (`none/user/agent/debug/human/json`, `--format`, `--report`, `--evidence`) instead of keeping a thin legacy wrapper and moving semantics into internal request/probe/user-answer contracts.
9. Letting temporary in-process `agent_report.v2` legacy aliases mask public JSON contract regressions; serialized reports must use nested `evidence`/`frontier`/`user_answer`/`diagnostics` paths.
10. Reintroducing provider execution shortcuts in `execution/*`: segment and aggregate probes should go through `adapters.providers.registry` → concrete `FlightProviderPort` adapters → `ProviderProbeResult`. Do not add backward provider→registry wrappers in provider modules; they create provider↔adapter import cycles caught by architecture tests.
11. Building `planned_controls` / `not_executed_controls` in reporting from static `plan["coverage_controls"]` after live execution. For agent-path coverage, plan runtime `ProbeIntent`s and project terminal state from the unified `ProbeExecutionLedger`; reporting may only normalize an existing runtime ledger. Include first-class `not_supported_controls` in schema, semantic validation, report-budget trimming, and tests when provider capability boundaries are represented.
12. Closing coverage buckets only at schema/validator level but forgetting downstream semantics. `not_executed_controls` and `failed_controls` are missing/degraded evidence; `not_supported_controls` is a terminal provider/source capability boundary. Offer graph and user-answer/human renderers should surface capability boundaries as bounded source limits when decision-relevant, but must not count them as missing evidence or make coverage incomplete by themselves.
13. Treating `--agent-brief` as permission to narrow evidence scope. It may trim the output envelope and imply report attachment, but it must not override explicit route/evidence/search controls such as `--stop-policy debug-all`; only `--agent-mode` may preserve legacy compact/evidence-budget defaults.

## Verification Checklist

- [ ] Constraints normalized.
- [ ] Runtime `route live-assemble --agent-brief` run, or provenance failure reported before fallback.
- [ ] Answer based on `data.agent_report`; prefer `user_answer.rendered_text`; use `human_answer.text` only as a legacy fallback/projection.
- [ ] `frontier.recommended_options`, `frontier.priority_options`, `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` checked.
- [ ] When changing provider execution, follow `references/provider-port-pattern.md`: execution modules call `FlightProviderPort` adapters; provider-specific fetch/cache/normalization/summary logic stays under `adapters/providers/`.
- [ ] When changing coverage diagnostics, verify runtime `ProbeIntent` → `ProbeExecutionLedger` → report projection end-to-end: segment, aggregate, and city-pair controls appear in one ledger; terminal buckets include searched/skipped/failed/not_supported/not_executed/deduped; `planned_controls` and `not_executed_controls` are not synthesized post-hoc by reporting when `live.probe_ledger` exists.
- [ ] When adding or changing terminal coverage buckets, verify all downstream consumers: serialized schema, semantic validator, report-budget trimming, `offer_graph.evidence`/`missing_evidence`, `user_answer.evidence_status`, and human renderer wording. Specifically, `not_supported` should be surfaced as a provider/source capability boundary, not as `missing_evidence`, `provider_failure`, or incomplete coverage by itself.
- [ ] When auditing `--agent-*` flags, include explicit tests that `--agent-report` and `--agent-brief` do not change search/evidence controls; `--agent-brief` may trim output only and must preserve explicit controls like `--stop-policy debug-all`.
- [ ] Required direct/carrier/exact-airport/Moscow controls or narrow probes run.
- [ ] Ticketing/protection/baggage-through and terminal claims proven or explicitly unconfirmed.
- [ ] Maintenance verifies source/runtime paths, branch/HEAD/status, versions, backup, parity, tests/doctor, and generated-artifact cleanup.

## References

- Canonical active references are bounded to five core flight-search directions, plus bounded adjacent-mode notes when a flight session expands into direct travel-mode comparison:
  - `references/report-contract.md` — `agent_report` read order and final answer renderer contract.
  - `references/source-boundaries.md` — evidence classes, absence, airport/connection boundaries, ticketing, OTA/smart-route semantics.
  - `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
  - `references/debug-playbook.md` — targeted probes and route-family exception patterns.
  - `references/cli-maintenance.md` — source/runtime, schema/tests, sync, generated artifacts, and reference lifecycle.
  - `references/cli-redesign-governance.md` — target architecture for CLI/report redesign: agent/output/evidence decomposition, schema cutover, canonical user answer, provider ports, aggregate controls, and stop-policy contract.
  - `references/agent-report-v2-migration.md` — practical migration pattern for splitting flat `agent_report.v1` into `agent_report.v2` evidence/frontier/user-answer/diagnostics layers while keeping only temporary internal legacy aliases.
  - `references/rail-rzd-live-pricing.md` — RZD public endpoint/RID workflow for bounded train-price comparisons after a flight search.
- Do not add per-incident/audit/handoff reference files by default; distill durable rules into the files above or into tests, and leave raw history to session search.
