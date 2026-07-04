# Tutu MCP Provider

Use this file only when maintaining or debugging the `tutu` provider. Normal route search should follow `SKILL.md` and read the assembled `agent_report`.

## Current Contract

- Endpoint: `https://mcp.tutu.ru/mcp` by default, overridden by `FLIGHTS_TUTU_MCP_URL`.
- Protocol: JSON-RPC 2.0 over Streamable HTTP with MCP protocol version header.
- Tool: `search_avia`.
- Input: Russian city names, not IATA codes. The adapter resolves IATA through `Store.city_by_code`.
- Output: shopping offers, not booking proof.

## Implementation Owners

| Concern | Owner |
| --- | --- |
| HTTP MCP call and pagination | `providers/tutu_mcp.py` |
| Tutu response normalization | `providers/tutu_mcp.py` |
| Provider-port adapter | `adapters/providers/tutu_adapter.py` |
| Provider routing and policy enum | `adapters/providers/registry.py`, `contracts/flight_search_request.v1.schema.json` |
| Pagination and normalizer tests | `tests/test_tutu_mcp.py` |
| Routing/capability tests | `tests/test_provider_capabilities.py`, `tests/test_offer_query_runner.py`, `tests/test_probe_dispatcher.py`, `tests/test_aggregate_control_runner.py` |

## Routing Policy

- `auto`: Tutu MCP first. A searched Tutu result short-circuits fallback providers for the same logical probe.
- `tutu`: Tutu-only where market and capability allow it.
- `kupibilet` / `fli`: explicit override modes.
- `both`: invalid.

Tutu supports RU-touching and global markets, segment and full-route aggregate probes, direct-only post-filtering, carrier post-filtering, carrier aggregate, round-trip input, and cache.

## Normalization Rules

- Tutu airport strings contain IATA in parentheses, for example `"Париж - Шарль-де-Голль (CDG), терм. 2F"`.
- Extract IATA from the parenthesized airport code; extract terminals from the provider terminal suffix when present.
- Tutu carrier values are display names. Resolve them through the airline catalog where possible; carrier filters apply after normalization and require every segment in the journey to match.
- `segments_count - 1` maps to connection count.
- Round-trip provider offers stay provider-returned outbound/return journeys; do not flatten them into fake one-way connections or claim single-PNR/protection.

## Pagination

Current adapter constants:

- `TUTU_PAGE_SIZE = 30`
- `TUTU_MAX_PAGES = 3`

The adapter requests `sort=departure_asc`, fetches up to the page budget, and records pagination metadata including `pages_fetched`, `has_more_after_fetch`, and `not_fetched_due_to_page_budget`. If later flights matter, inspect pagination before claiming absence.

## Known Boundaries

- Tutu `search_avia` can return no full-route offers while segment-level probes still return useful legs. Treat this as provider route-search coverage, not proof that the leg does not exist.
- Tutu searches by city name; exact-airport requests must be post-filtered against actual normalized segment endpoints.
- Missing `voyage_no` is normal; flight numbers may be absent.
- Tutu offers can still be rejected by chronology, airport-continuity, MCT, direct-mode, or user-constraint gates. If provider offers exist but the frontier is empty, inspect `decision_frontier.coverage_summary`, `offer_graph.rejected`, and provider failures before claiming absence.

## Diagnostics

Prefer the provider-port diagnostic first:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose probe \
  --provider tutu \
  --request probe.json
```

Use `diagnose tutu-search` only when you need Tutu-specific raw pagination/normalization evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose tutu-search \
  ORIGIN DEST \
  --depart-date YYYY-MM-DD
```
