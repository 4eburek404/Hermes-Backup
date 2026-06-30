---
name: flight-search
version: 0.8.8
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find, compare, or diagnose live flights via the bundled CLI. One adult, economy. Never books.

## Run

1. Normalize route/date/scope: exact airports vs city, carrier, direct-only, return date, ticketing intent, profile (`business` default).
2. Write a `flight_search_request.v1` (template below; full schema in `cli/`).
3. Run the canonical path — do not provider-probe first:

Write the request JSON to an **absolute path** under the user home directory (e.g. `C:\Users\<user>\flight-search-request.json` on Windows, `~/flight-search-request.json` on Linux). Do NOT use `/tmp/` — on Windows, `write_file` resolves `/tmp/` to `C:\tmp\` while bash MSYS resolves it to `C:\Users\<user>\AppData\Local\Temp\`, causing path mismatches.

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request "$HOME/flight-search-request.json"
```

On Windows hosts `python3` is often missing; use `py -3 -m flights_cli` or `python -m flights_cli` there after confirming it is Python 3.11+.

4. Answer from `data.route_result.agent_report.user_answer.rendered_text` (or `data.agent_report.user_answer.rendered_text` in flat mode). Read order, fields, renderer contract: `references/report-contract.md`.

**Pitfall:** `rendered_text` can say "Не нашёл пригодных вариантов" even when `primary_offer_results[0].top_offers` has 10+ priced offers. This happens when the stop-policy tier doesn't promote offers to `ranked_candidates`. Always cross-check `top_offers` via `execute_code`/`subprocess` before reporting absence. See `references/provider-failover.md` → "Pitfall — rendered_text false negative".

**When the user specifies an exact routing** (e.g. "через CDG→IST"), use `diagnose kb-search` per leg and manually assemble. See `references/provider-failover.md` → "Manual leg-by-leg assembly via `diagnose kb-search`".

```json
{"schema_version":"flight_search_request.v1","origin":"ORIGIN","destination":"DEST","depart_date":"YYYY-MM-DD","profile":"business"}
```

Direct-only: add `"route_options":{"max_connections":0}`. Date window: add request-only `"route_options":{"max_connections":0,"tier2_max_connections":0,"date_window_end":"YYYY-MM-DD"}` and omit `return_date`; there is no `--date-window-end` flag. Carrier scope: `"filters":{"only_carriers":[...]}`. Return: `"return_date":"YYYY-MM-DD"`. Currency, ticketing, provider_policy, and agent_brief default in the CLI.

### Provider failover (FLI down)

When FLI MCP is unreachable (`WinError 10061` / connection refused), add `"provider_policy":"kupibilet"` to force all searches through KupiBilet only. This bypasses FLI-dependent segment probes. For routes where the hardcoded IST hub legs go to FLI by default, also add `"route_options":{"use_gateway_discovery_for_fallback_hubs":true}` to disable the IST→FLI imperative and let gateway discovery source bridge gateways from data instead.

**Key: `provider_policy: "kupibilet"` alone is NOT enough for `ru-priority` strategy.** In `ru-priority`, IST-ноги are hardcoded to FLI via `PRIORITY_PRIMARY_HUB = "IST"`. The `provider_policy` field controls the aggregate search, not segment probes. To fully bypass FLI:
- Use `"route_options":{"use_gateway_discovery_for_fallback_hubs":true}` (disables IST hardcode, enables data-driven gateway discovery), OR
- Use `"route_options":{"routing_strategy":"hub-list","hubs":["IST","SVO"]}` (explicit hub-list bypasses the IST→FLI imperative; KupiBilet handles all legs)

### Tutu MCP provider (`provider_policy: "tutu"`)

Tutu MCP (`https://mcp.tutu.ru/mcp`) is a remote aggregate source that returns connected flights (1-2 stops) for routes where KupiBilet/FLI may have no inventory. It is **opt-in only** — not used in `auto` or `both` modes. Use it when KupiBilet returns 0 offers for a date:

```json
{"schema_version":"flight_search_request.v1","origin":"TLS","destination":"SVX","depart_date":"2026-07-10","profile":"business","provider_policy":"tutu"}
```

Tutu accepts city names (Russian), not IATA codes — the CLI resolves IATA→city via `Store.city_by_code` before calling `search_avia`. Carrier names in Tutu responses are resolved to IATA codes via the airline catalog. `voyage_no` (flight number) is often `null`. See `references/tutu-mcp-provider.md` for architecture details.

**Pitfall — Tutu pagination misses later departures.** Tutu `search_avia` defaults to `page_size=10`. If a route has >10 offers, later departures (e.g. 17:20) land on page 2+ and are invisible. The CLI provider (`tutu_mcp.py`) now sends `page_size=30` and auto-paginates up to 3 pages, but when calling `mcp_tutu_search_avia` directly, always pass `page_size=30` and check `meta.has_more` — fetch page 2 if needed. This is critical for "after 15:00" queries where morning flights dominate page 1.

**Pitfall — full-route search ≠ segment search coverage.** A full-route `search_avia` call (e.g. NTE→SVX) may NOT return all viable connecting flights through a hub. A direct city-pair search (NTE→IST) can reveal flights (e.g. KLM 17:20 NTE→AMS→IST) that the aggregate NTE→SVX search missed entirely. When the CLI pipeline returns 0 ranked_candidates but segment probes show offers, or when the user reports a flight from the tutu.ru website not in your results, search the individual leg (origin→hub) directly via `mcp_tutu_search_avia`.

### Parallel multi-provider search

When the user asks for multiple providers in one query (e.g. "kupibilet ru-touching + tutu mcp non ru"), write two request JSON files and run both CLI searches in parallel. Then merge results:

1. Write `flight-search-kb.json` with `"provider_policy":"kupibilet"` and appropriate `"route_options"`.
2. Write `flight-search-tutu.json` with `"provider_policy":"tutu"`.
3. Run both CLI searches (two `terminal` calls in the same turn — they execute concurrently).
4. Parse both result files with `execute_code`, extract `top_offers` from each, merge and sort by price.

### Tutu MCP tool for direct segment search

When the CLI pipeline returns 0 `ranked_candidates` but Tutu segment probes show offers, or when you need to find flights on a specific leg (e.g. NTE→AMS or AMS→SVX) that the CLI's assembly logic rejects, call the Tutu MCP `search_avia` tool **directly** (via `mcp_tutu_search_avia`) for individual legs:

- Search origin→hub and hub→destination separately.
- Use Russian city names (Тулуза, Амстердам, Екатеринбург, Стамбул).
- Check `has_more` in `meta` — Tutu paginates, early morning flights may be on page 2+.
- Merge leg offers manually: sum prices, check connection times, verify same-airport at hub.

This is the Tutu equivalent of `diagnose kb-search` for KupiBilet. See `references/tutu-mcp-provider.md` → "Direct segment search via MCP tool".

### Hub selection for 1-stop search

Only specify hubs that have direct flights **to Russia/from Russia**. Waste of budget: CDG, MUC, MXP — they have flights from TLS but no direct to SVX. Good hubs for TLS→SVX: IST (Turkish), SVO/MOW (Aeroflot). For EU→RU routes generally: IST, SVO, and sometimes AYT/EVN/TBS/GYD (low-cost carriers). Do NOT list 10+ hubs — each empty probe burns `max_segment_searches` budget and can cause `not_executed_controls`.

### Cross-day 1-stop assembly

The CLI has `DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS = [0, 1]` — by default it searches second legs on day 0 and day+1. `route_plan_builder._build_outbound_hub_list` correctly generates probes for both days.

**Limitation:** `GatewayLegProbeExecutor` (which assembles leg pairs into candidates) does NOT apply day offsets — it only pairs same-date legs. So if the first leg arrives 23:25 and the second leg departs next day 19:45, both are found in `segment_searches` but NOT assembled into a ranked 1-stop candidate.

**Workaround:** When `ranked_candidates` is empty but segment searches show offers on both legs, run a separate direct search for the second leg on the next day:
```json
{"schema_version":"flight_search_request.v1","origin":"IST","destination":"SVX","depart_date":"2026-07-11","profile":"business","provider_policy":"kupibilet","route_options":{"max_connections":0}}
```
Then manually report both legs and sum prices from `rejected_pairs[].first_offer.price` + second leg search price.

## Large output extraction

CLI JSON output is 400–600KB. Terminal truncates at ~4KB visible and ~450KB total. **Never present truncated raw JSON to the user.** Instead, extract offers programmatically.

**Key JSON paths** (current `route_result` structure):

| Path | Content |
|------|---------|
| `data.route_result.live_search.primary_offer_results[0].top_offers` | Ranked offers: price (int), segments, carriers, times, stop_tier |
| `data.route_result.live_search.segment_searches` | Per-leg results: origin, destination, date, offer_count, status, provider |
| `data.route_result.live_search.offer_candidates` | Dict with `candidates` (list), `coverage`, `rejected` |
| `data.route_result.candidates` / `.ranked_candidates` | Assembled candidates (may be empty even when offers exist) |
| `data.route_result.rejected_pairs` | Pairs tried but rejected — shows why assembly failed |
| `data.route_result.live_search.decision_frontier.options` | All candidates including gateway-assembled |
| `data.route_result.live_search.gateway_leg_results` | Per-gateway leg probe results |
| `data.route_result.live_search.probe_ledger` | Provider probe audit trail |

**Fallback paths** (older flat structure, may still appear):
- `data.agent_report.evidence.primary_offer_results[0].top_offers`
- `data.agent_report.evidence.segment_searches`

**Rendered text** is at `data.route_result.agent_report.user_answer.rendered_text` (or `data.agent_report.user_answer.rendered_text` in flat mode). The rendered text may say "Не нашёл" even when `top_offers` has results — always cross-check `top_offers` before reporting absence.

Use `execute_code` with `subprocess.run` to capture full JSON, or run the CLI in `terminal(background=true)` redirecting to a file, then parse with `read_file` / `search_files` for specific fields. See `references/provider-failover.md` for extraction patterns.

## Invariants

Apply to every reply. Full evidence/absence taxonomy: `references/source-boundaries.md`.

1. Provider output is shopping evidence, not booking proof. Single PNR, through-baggage, protection, fare rules, refund/exchange, and terminal certainty are **unproven** unless purchase-screen / airline-GDS / seller / explicit upstream proof says otherwise.
2. Empty provider output is not "no flights" unless targeted controls or structural route evidence support it.
3. Metadata never proves availability — static catalogs, cached fare helpers, maintenance diagnostics, and `data.catalog_auto_refresh` describe metadata only.
4. Named airports are not city scope. If you broaden ORIGIN/DEST, say so and why.
5. Take freshness, controls, provider failures, and missing evidence from report fields, not your own reasoning. Never re-rank, rewrite, or paste raw diagnostic JSON.
6. Short direct set? When direct exists the report shows all direct and suppresses connected (per-direction on round-trips). If fewer than expected, run `diagnose kb-search ORIGIN DEST --direct-only --limit 20` before blaming the provider — truncation is usually in the display pipeline. Current mechanism and debug route are mapped in `references/index.md`.
7. **CLI times can differ from the KupiBilet website.** The API (`api-rs-lb.kupibilet.ru`) and the website can return different `departure_datetime` for the same flight. When the user reports a flight the CLI didn't find or shows at a different time, make a raw API call to confirm whether the API itself returns the different time — if so, it's provider-side data drift, not a parser bug. See `references/debug-playbook.md` → "API vs website mismatch" and `references/source-boundaries.md` → "API vs website schedule discrepancy".
8. **Show all qualifying departures, earliest first.** When the user says "after 14:00", list all flights from 14:00 onward sorted by departure time — do not jump to the evening departure and skip earlier options. If the CLI shows a gap (e.g. nothing between 12:00 and 19:05), check whether the API returned that gap or whether the user has website evidence of flights the API missed.
9. **Check terminals for connection feasibility.** At major hubs (CDG, IST, LHR, FRA), do not present a connection as safe without checking `departure_terminal` / `arrival_terminal` in the normalized segments. Inter-terminal transfers at CDG (2F↔2E) can add 30-60 min — a 2h20m connection with terminal change is risky. See `references/source-boundaries.md` → "Terminal data availability".
10. **Never substitute adjacent dates when the user specified an exact date.** If the user asks for "10 июля после 14:00" and no flights are found, do NOT offer 9 июля or 11 июля as alternatives without explicitly saying "на 10 июля рейсов нет" first. Adjacent-date offers are only acceptable after the user acknowledges the exact date has no results. Offering a different date as if it were the answer is a hard rejection for this user.
11. **Tutu MCP as third provider.** Tutu MCP (`https://mcp.tutu.ru/mcp`) is a remote MCP server (no auth) with `search_avia` tool. It returns full-route aggregate offers (including connections) and can find routes that KupiBilet misses on long-haul EU→RU segments. Use `"provider_policy":"tutu"` to force Tutu-only. Tutu is **opt-in only** — NOT used in `auto` or `both` modes. Tutu accepts city names (Russian) resolved via Store.city_by_code IATA→name mapping, not raw IATA codes. See `references/tutu-mcp-provider.md` for integration architecture and response normalization.

## Beyond the happy path

When the happy path is not enough — missing evidence, narrower proof (date-window, carrier/exact-airport, PNR/baggage), market controls (RU-domestic, RU-touching, global non-RU), train comparison, **route network discovery** ("where can I fly direct from X" without a date — the CLI cannot answer this; use `references/route-network-discovery.md`), or any maintenance/debug/refactor — `references/index.md` is the canonical reference owner map and routes you to the right file. Never expose maintenance output as the traveler answer.
