---
name: flight-search
version: 0.10.11
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

Use for live flight search/comparison, direct-service checks, hub/airport choice, carrier-specific availability, baggage/ticketing/protection risk, date-window planning, or this CLI/report maintenance. Do not use for purchase actions, visa/hotel/ground research, or static fare hints unless explicitly requested as non-validated advisory data. Single-PNR/protection/baggage/fare-rule claims need purchase-screen/airline/GDS/seller/upstream proof.

## Maintenance Mode Gate

Default is traveler route search. Do not inspect source/runtime, raw candidates, `doctor`, schemas, or generated artifacts unless failure blocks search or the user asks to inspect/debug/audit/modify/sync this skill, CLI, or report contract. Use `references/cli-maintenance.md` / `references/debug-playbook.md`.

## Golden Path

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

Add `--return-date YYYY-MM-DD` for round trips. Add `--aggregate-control-carrier CARRIER` for carrier tasks; if incomplete, run narrow `kb-search ORIGIN DEST --only-carrier CARRIER` for full route and likely hub legs. For KupiBilet “туда-обратно одним билетом”, use `kb-roundtrip` first. Multi-city/open-jaw has no arbitrary live command; use separate assemblies or offline `route validate`/`route rank` and label diagnostic.

4. Read only `data.agent_report`.
5. Prefer `human_answer.text`; cross-check `recommended_options`, `priority_options`, `through_fare_checks`, `provider_failures`, and `source_boundaries`. `display`/`answer_lines` are evidence/debug inputs, not final prose. `doctor` is provenance only.

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
- Round trips: **Лучшая пара / рекомендация**, **Альтернативы туда**, **Альтернативы обратно**, **Отсекаю / fallback** if useful, **Проверить перед покупкой**.
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

## Verification Checklist

- [ ] Constraints normalized.
- [ ] Runtime `route live-assemble --agent-brief` run, or provenance failure reported before fallback.
- [ ] Answer based on `data.agent_report`, preferably `human_answer.text`.
- [ ] `recommended_options`, `priority_options`, `through_fare_checks`, `provider_failures`, and `source_boundaries` checked.
- [ ] Required direct/carrier/exact-airport/Moscow controls or narrow probes run.
- [ ] Ticketing/protection/baggage-through and terminal claims proven or explicitly unconfirmed.
- [ ] Maintenance verifies source/runtime paths, branch/HEAD/status, versions, backup, parity, tests/doctor, and generated-artifact cleanup.

## References

- Canonical active references are bounded to five logical directions:
  - `references/report-contract.md` — `agent_report` read order and final answer renderer contract.
  - `references/source-boundaries.md` — evidence classes, absence, airport/connection boundaries, ticketing, OTA/smart-route semantics.
  - `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
  - `references/debug-playbook.md` — targeted probes and route-family exception patterns.
  - `references/cli-maintenance.md` — source/runtime, schema/tests, sync, generated artifacts, and reference lifecycle.
- Do not add per-incident/audit/handoff reference files by default; distill durable rules into the five files above or into tests, and leave raw history to session search.
