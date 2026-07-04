# Tutu MCP Provider Integration

Architecture and normalization map for the `tutu` provider in the flight-search CLI.

## Tutu MCP endpoint

- URL: `https://mcp.tutu.ru/mcp` (config: `TUTU_MCP_DEFAULT_URL`)
- Protocol: JSON-RPC 2.0 over Streamable HTTP (MCP `2025-06-18`); requests include `MCP-Protocol-Version`
- No auth required
- Tool: `search_avia` — accepts city names (Russian), not IATA codes

## Key differences from KupiBilet/FLI

| Aspect | KupiBilet | FLI | Tutu |
|--------|-----------|-----|------|
| Input | IATA codes | IATA codes | City names (Russian) |
| Auth | None | None | None |
| Scope | RU-touching + global | Global only | Global (RU + international) |
| Aggregate | Yes (full route) | No (segment only) | Yes (full route, connections included) |
| URL | REST API | Local MCP | Remote MCP |

## CLI architecture: adding a provider

The CLI uses a ports-and-adapters pattern. To add a provider:

1. **`ports/providers.py`** — Add to `ProviderName = Literal[...]`
2. **`config.py`** — Add `TUTU_MCP_DEFAULT_URL` constant
3. **`providers/tutu_mcp.py`** — HTTP MCP client + response normalizer:
   - `call_tutu_mcp_tool(tool_name, arguments, mcp_url, timeout)` — JSON-RPC initialize → tools/call
   - `parse_tutu_avia_search(raw, origin, destination, depart_date, currency, limit, ...)` — normalize Tutu response to internal offer format and apply CLI post-filters
   - `cached_tutu_avia_search(...)` — cache wrapper (same pattern as `cached_kupibilet_search`)
   - `tutu_result_to_segment_result(...)` — delegate to `provider_result_to_segment_result`
   - `tutu_segment_search_summary(...)` — summary dict
4. **`adapters/providers/tutu_adapter.py`** — `TutuProviderAdapter` implementing `FlightProviderPort`:
   - `TUTU_CAPABILITIES = ProviderCapabilities(supports_ru_touching=True, supports_global=True, supports_full_route_aggregate=True, ...)`
   - `search_segment(query)` — calls `cached_tutu_avia_search`, returns `ProviderProbeResult`
   - `search_aggregate(query)` — same as segment (Tutu returns full routes)
5. **`adapters/providers/registry.py`** — Register in `PROVIDER_REGISTRY`, update `_normalize_provider_policy`, update policy candidate functions
6. **`contracts/flight_search_request.v1.schema.json`** — Add `"tutu"` to `provider_policy` enum

## Tutu search_avia response structure

```
offers[].price.amount          # float, RUB
offers[].price.currency         # "RUB"
offers[].duration_min           # int, total trip duration
offers[].segments_count          # int
offers[].departure_at            # ISO datetime with tz
offers[].arrival_at              # ISO datetime with tz
offers[].carriers                # list of carrier name strings
offers[].legs[].segments[]       # per-leg segments
  .from                          # "Тулуза — Тулуза-Бланьяк (TLS)" — IATA in parens
  .to                            # "Париж — Шарль-де-Голль (CDG), терм. 2F"
  .carrier                       # "Air France" (name, not IATA code)
  .departure_at / .arrival_at    # ISO datetime with tz
  .duration_min                  # int
offers[].variants[]              # fare families
  .price.amount
  .conditions.baggage / .cabin_baggage / .refundable / .changeable
  .service_class                  # ECONOMIC / BUSINESS
offers[].checkout_ref            # pass verbatim to create_checkout_link
```

## IATA extraction from airport strings

Tutu airport strings follow the pattern `"City — Airport Name (IATA)"` or `"City — Airport Name (IATA), терм. X"`.

Extract IATA with: `re.search(r'\(([A-Z]{3})\)', airport_string)`

## City name resolution (IATA → Russian city name)

Tutu `search_avia` accepts city names like `"Тулуза"`, `"Екатеринбург"`. The CLI's `Store.city_by_code` maps IATA → city dict with `.name` (Russian nominative). Use `store.city_by_code["TLS"].name` → `"Тулуза"`.

## Normalization to internal offer format

Each Tutu offer maps to the internal offer dict shape used by `provider_offer_to_segment_offer`:

```python
{
    "id": offer_id,
    "price": price_amount,           # float
    "currency": "RUB",
    "number_of_changes": segments_count - 1,
    "duration": duration_min,
    "departure_at": first_segment_departure,
    "arrival_at": last_segment_arrival,
    "origin": first_segment_origin_iata,
    "destination": last_segment_destination_iata,
    "flight_numbers": [...],         # may be None — Tutu doesn't always return voyage_no
    "marketing_carriers": [...],     # IATA codes resolved via Store.airlines name→code lookup
    "operating_carriers": [...],
    "segments": [{flight_number, marketing_carrier, operating_carrier, origin, destination, departure_at, arrival_at, duration}],
}
```

## Capabilities

```python
TUTU_CAPABILITIES = ProviderCapabilities(
    supports_ru_touching=True,
    supports_global=True,
    supports_city_code=False,    # CLI resolves IATA→city name before calling Tutu
	    supports_direct_only=True,   # CLI post-filter; search_avia has no upstream direct-only arg
	    supports_carrier_filter=True, # CLI post-filter; search_avia has no upstream carrier arg
	    supports_full_route_aggregate=True,
	    supports_round_trip=True,    # stored as outbound/return journeys, not two protected one-ways
    supports_cache=True,
    probe_types=frozenset({"segment_direct", "segment_hub_leg", "full_route_aggregate", "city_pair_direct"}),
)
```

## Provider policy routing

- `"tutu"` — Tutu-only (all segments and aggregate probes)
- `"both"` — kupibilet + fli only (tutu excluded)
- `"auto"` — Tutu is NOT used by default; only when explicitly requested via `provider_policy: "tutu"`

## Test fixtures

Tests that assert `set(PROVIDER_REGISTRY) == {"kupibilet", "fli"}` need updating to include `"tutu"`. See `tests/test_provider_capabilities.py`.

## Known limitations

- Tutu `search_avia` may return 0 offers for long-haul one-way routes on far-future dates. The upstream suggests retrying with `return_date` — some routes are sold only as round-trip packages.
- Carrier names in Tutu responses are display names (e.g. "Air France", "Уральские авиалинии"), not IATA codes. The normalizer resolves carrier names through the airline catalog where possible; carrier filtering is applied after normalization and requires every segment in every journey to match.
- `voyage_no` (flight number) is often `null` in Tutu responses.
- **Pagination: `page_size=10` by default (max 30).** Without explicit `page_size=30`, later departures (afternoon/evening) are invisible — they land on page 2+ behind cheaper morning flights. The CLI provider (`tutu_mcp.py`) sends `page_size=30` with `sort=departure_asc` and auto-paginates up to 3 pages (90 offers) before applying display `limit`. Diagnostics keep `pagination.has_more_after_fetch` and `pagination.not_fetched_due_to_page_budget`. When calling `mcp_tutu_search_avia` directly, always pass `page_size=30` and check `meta.has_more`.
- **Airport scope is post-filtered.** Tutu searches by city name, so an exact-airport request like `LHR` can return another London airport. The CLI accepts only offers whose actual first/last airports match the requested airport scope; city requests such as `LON` may accept multiple London airports.
- **Round-trip offers stay single provider-returned packages.** The normalizer stores outbound and return as separate `journeys`; it does not flatten two journeys into a fake one-way connection and does not claim single-PNR/protection.
- **Full-route search ≠ segment search coverage.** A `search_avia` call for NTE→SVX may NOT return all viable 1-stop connecting flights through a hub (e.g. KLM NTE→AMS→IST at 17:20). The aggregate search filters by its own routing logic and may exclude valid hub connections. A direct city-pair search (NTE→IST) reveals flights the full-route search missed. When the user reports a flight from tutu.ru not in your results, search the individual leg directly.
- **Tutu offers can still be rejected by the frontier gate.** Cross-airport or impossible chronology paths stay in diagnostics/rejections, not in traveler options. When provider results have offers but the frontier is empty, inspect `decision_frontier.coverage_summary`, `offer_graph.rejected`, and provider failures before claiming absence.
- **Tutu full-route aggregate may return 0 offers** for the complete route (e.g. TLS→SVX one-way), but segment-level probes (TLS→IST, IST→SVX separately) DO return offers. The CLI's pipeline handles this by probing segments individually when `provider_policy: "tutu"` is set. This is expected — Tutu's `search_avia` is a route-level search that may not find complex multi-stop itineraries, but the CLI's segment-by-segment approach finds them.

## Direct segment search via MCP tool

When DecisionFrontier is empty but Tutu provider evidence shows relevant offers, or when you need to inspect one specific leg (e.g. NTE→IST or AMS→SVX), call the Tutu MCP `search_avia` tool **directly** (via `mcp_tutu_search_avia`) for individual legs.

### When to use

- CLI `provider_policy: "tutu"` search returned 0 ranked candidates, but `segment_searches[].offer_count > 0` — the pipeline rejected the pairs, not the provider.
- User asks for a specific routing through a hub that the CLI doesn't probe (e.g. "through Amsterdam" when CLI only tried IST/SVO).
- User filters by departure time (e.g. "after 15:00") and no CLI results qualify — Tutu MCP may have additional flights on later pages.

### How

1. Call `mcp_tutu_search_avia` with `origin` and `destination` as **Russian city names** (not IATA codes). Example: `origin="Нант"`, `destination="Амстердам"`.
2. Check `meta.has_more` — Tutu paginates, and morning flights often dominate page 1 while later departures are on page 2+.
3. For connecting flights, search each leg separately (origin→hub, hub→destination). Use the date that matches the user's constraint.
4. **Cross-day connections**: if leg 1 arrives in the evening, search leg 2 on the next day (`departure_date` = next day).
5. Extract: `offers[].departure_at`, `offers[].arrival_at`, `offers[].price.amount`, `offers[].legs[].segments[].carrier`, `offers[].legs[].segments[].from`/`.to` (airport strings with IATA in parens).
6. **Check airport codes** in segment `from`/`to` strings — IST and SAW are different airports in Istanbul. A connection IST→SAW requires ground transfer.

### Example: NTE→AMS→IST→SVX (09-10.07.2026)

- Leg 1: `mcp_tutu_search_avia(origin="Нант", destination="Амстердам", departure_date="2026-07-09")` — found KLM via CDG, 22 065 ₽
- Leg 2: `mcp_tutu_search_avia(origin="Амстердам", destination="Екатеринбург", departure_date="2026-07-10")` — found Turkish Airlines + U6 via IST, 55 114 ₽
- Total: ~77 179 ₽, overnight in Amsterdam

### Tutu airport string parsing

Tutu airport strings: `"Тулуза — Тулуза-Бланьяк (TLS)"` or `"Париж — Шарль-де-Голль (CDG), терм. 2F"`.

Extract IATA: `re.search(r'\(([A-Z]{3})\)', airport_string)`
Extract terminal: `re.search(r'терм\.\s*(\S+)', airport_string)`
