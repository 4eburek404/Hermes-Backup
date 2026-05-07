# FLI + Kupibilet Provider Strategy

Checked: 2026-05-07
Branch: `fli-flights`

## Summary

Use provider selection by segment, not only by the full user request:

- Russia domestic (`RU -> RU`): Kupibilet primary.
- Russia international (`RU -> non-RU` or `non-RU -> RU`): Kupibilet primary for the Russia-touching leg and final booking sanity. For onward non-Russia segments inside the assembled route, query FLI in parallel as an augmentation source.
- Global routes with no Russia endpoint (`non-RU -> non-RU`): FLI primary. Kupibilet can remain an optional secondary source when Russian-market booking/payment matters.

This matches the current Hermes shape: route planning already decomposes trips into direct segment searches, normalizes provider responses into `segment_result`, then assembles and ranks candidates. FLI should enter behind the same normalized segment-result contract instead of replacing ranking or validation.

## Source Notes

- FLI is published as PyPI package `flights` version `0.8.4`, released 2026-04-07. It exposes CLI, Python API, and MCP server entrypoints. The project describes itself as reverse-engineered access to Google Flights data, not as an official Google public API.
  - https://pypi.org/project/flights/
  - https://punitarani.github.io/fli/guides/quickstart/
- FLI CLI JSON is explicitly experimental, so do not treat its JSON schema as a long-term stable contract without an adapter and tests.
- Google Flights official help says some flights can be absent when sold out/unavailable or when a carrier is not added to Google Flights, and shown prices can have additional fees depending on airline or OTA.
  - https://support.google.com/travel/answer/2475306
- Kupibilet official pages position it as a Russian-market flight purchase service with smart routes, app/account workflows, support, and many airline partners.
  - https://www.kupibilet.ru/about
- Kupibilet help explicitly warns that a fare can disappear or the airline may not confirm seats at the selected fare; all advisory prices still need a final booking-screen check.
  - https://www.kupibilet.ru/help/sistemnye-uvedomleniya-v-protsesse-pokupki-bileta/art/poyavilos-uvedomlenie-otsutstvie-mest-po-tarifu

## MCP vs CLI for FLI

Prefer self-hosted FLI MCP HTTP as the target integration for Hermes agents.
Because the agent runs on the VPS, run the FLI MCP sidecar on that VPS and let
Hermes reach it through `FLIGHTS_FLI_MCP_URL`:

```text
Hermes agent / flights CLI on VPS
  -> http://127.0.0.1:8000/mcp
  -> Docker container running fli-mcp-http
  -> FLI library
  -> Google Flights-derived upstream data
```

Reasons:

- Long-running server avoids a new process per segment search.
- Tool parameters are structured around `search_flights` and `search_dates`.
- It is easier to isolate in a sidecar Docker container because FLI is reverse-engineered and has its own dependency surface.
- It fits parallel provider calls better than repeated subprocess CLI calls.

Keep FLI CLI as a smoke-test tool inside the sidecar image or for local
debugging, but not as the durable Hermes integration contract:

- `pipx install flights`
- `fli flights JFK LHR 2026-06-01 --format json`
- `fli dates JFK LHR --from 2026-06-01 --to 2026-06-30 --format json`

Do not bind core Hermes logic directly to the CLI JSON shape. Wrap MCP output in
a provider adapter and normalize into the existing `segment_result` shape.

Avoid direct Python API as the first integration path. The current Hermes `flights-cli` is intentionally standard-library-only, and importing FLI directly would pull third-party dependencies into the CLI package. A sidecar keeps that boundary clean.

## Parallel Search

Yes, global/international options can be parallelized, but with provider-level rate limits and a staged strategy for Russia-priority routing.

Parallelize safely:

- Independent provider calls for the same segment, for example Kupibilet and FLI on `IST -> LHR`.
- Independent non-Russia segments such as `IST -> LHR`, `DXB -> LHR`, `LHR -> IST`.
- Flexible-date searches when the date grid is independent.
- Different global route families when neither endpoint is in Russia.

Keep staged gates for request budget:

- The current `ru-priority` flow intentionally checks direct/IST/SVO before DXB and skips DXB when a priority route is viable.
- Running every fallback in parallel will reduce latency but increase live requests, empty-result cache churn, and rate-limit exposure.
- Recommended default: phase 1 direct + IST/SVO priority in parallel, phase 2 DXB/global fallbacks only if phase 1 has no viable assembled candidate.

Suggested caps:

- Kupibilet: small fixed concurrency, cache empty and positive results.
- FLI MCP: small fixed concurrency per server instance, backoff on upstream errors.
- Global process: one shared queue with provider-specific semaphores so a broad hub-list route cannot overwhelm either source.

## Implementation Path

1. Add a provider policy/classifier:
   - Inputs: origin airport/city country, destination airport/city country, route segment metadata.
   - Output: provider list ordered by priority, for example `["kupibilet"]`, `["fli"]`, or `["kupibilet", "fli"]`.

2. Add an FLI adapter:
   - Target: MCP HTTP sidecar on the VPS.
   - Config: `FLIGHTS_FLI_MCP_URL`, default `http://127.0.0.1:8000/mcp`.
   - Fallback: CLI `fli ... --format json` only for debugging.
   - Output: existing `segment_result` format used by `route assemble`.

3. Refactor the live assembly search loop:
   - Keep route planning, validation, assembly, carrier policy, and ranking unchanged.
   - Replace direct `cached_kupibilet_search(...)` dispatch with provider-policy dispatch.
   - Merge and dedupe offers after normalizing provider output.

4. Add tests:
   - `RU -> RU` selects Kupibilet only.
   - `RU -> non-RU` selects Kupibilet for Russia-touching segments and allows FLI for non-Russia onward segments.
   - `non-RU -> non-RU` selects FLI primary.
   - MCP/CLI adapter returns the same normalized shape.
   - Parallel dispatch respects staged `ru-priority` fallback rules.

## Decision

Use Kupibilet as the Russia-market source of truth, use FLI as the global discovery source, and integrate FLI through a provider adapter with MCP HTTP as the preferred runtime. Keep CLI support as a development fallback, not as the durable contract.
