# Reference Index and Ownership Map

This file is the canonical map for `flight-search` support references. `SKILL.md` links here for anything outside the happy path. Keep this index small and keep each referenced file single-purpose.

## Operating rule

- Start with the Golden Path in `SKILL.md`: run `python3 -m flights_cli --json search --request ...` and answer from `data.agent_report.user_answer.rendered_text`.
- Load a reference only when the current task crosses its trigger below.
- Do not create incident, audit, proposal, smoke, or handoff Markdown in `references/`. Distill durable behavior into the owner file below, CLI code/schema/tests, or session history.
- When two files seem to own the same rule, update this index first, then move the rule into the listed owner and replace duplicates with cross-references.

## Canonical references

| File | Owns | Load when | Non-goals |
|---|---|---|---|
| `report-contract.md` | How to read `data.agent_report`; `agent_report.v2`; `flight_search_user_answer.v3`; canonical answer path; renderer guarantees. | You need to decide what to show the traveler, inspect report fields, or maintain report/user-answer schema/renderer behavior. | Provider dispatch, source/proof taxonomy, route-pipeline internals. |
| `source-boundaries.md` | Evidence classes, absence taxonomy, airport/city boundaries, connection/MCT policy, ticketing/protection proof, static-catalog limits, KupiBilet/sidecar boundaries. | You need to phrase confidence/absence/ticketing claims or decide whether a caveat is decision-useful. | Route planning mechanics and provider-specific airport priority. |
| `provider-aware-airport-priority.md` | Provider/airport dispatch rules for multi-airport cities: KupiBilet city-code-first, FLI exact-airport policy, Moscow/London/Dubai/IST priorities, RU-priority visibility fields. | The task involves city vs airport scope, exact-airport proof, carrier/airport controls, or provider dispatch maintenance. | General source-boundary wording and pipeline stage descriptions. |
| `pipeline-reference.md` | Current data flow from `flight_search_request.v1` to `flight_search_result.v1`; flow decision, evidence plan, segment planning, provider dispatch, direct-priority/all-direct mechanics, reporting projection, data artifacts. | You need to debug or maintain how the CLI makes route decisions, how direct/connected options are assembled, or how fields move between stages. | Targeted live-probe recipes and traveler-facing caveat wording. |
| `gateway-hardcode-map.md` | Inventory of current hardcoded gateway/hub constants, route families, segment-plan injection branches, gateway priors, and Moscow/SVO control-layer boundaries. | You need to remove, externalize, or audit hardcoded hubs without changing behavior first. | New routing design or traveler-facing answer wording. |
| `debug-playbook.md` | Bounded diagnostic workflow: runtime provenance, JSON extraction, targeted provider probes, Moscow/direct/carrier controls, diagnostic split patterns. | The Golden Path report is inconsistent, sparse, degraded, or surprising, and a narrow probe could change the answer. | Normal route search; do not expose debug output as the traveler answer. |
| `direct-date-window.md` | Direct/nonstop inventory over a bounded date range using `route_options.max_connections=0`, `tier2_max_connections=0`, and `date_window_end`. | The user asks for all direct/nonstop flights across a range of dates. | Route recommendation or connected alternatives unless the user asks. |
| `rail-rzd-live-pricing.md` | Bounded official RZD read-only train-price comparison after a flight search. | The user asks whether train tickets are cheaper or wants rail prices for the same route/date. | Full rail-booking workflow or non-official aggregator estimates. |
| `cli-maintenance.md` | Source/runtime governance, CLI JSON stdout/stderr rules, contract/schema lifecycle, provider-port maintenance, renderer tests, generated artifacts, reference lifecycle. | The task is inspect/debug/refactor/sync/version/test work on the skill or CLI. | Traveler-facing route search and provider-live evidence. |
| `provider-failover.md` | FLI-down failover to KupiBilet-only, gateway discovery mode, hub-list strategy for 1-stop, cross-day assembly limitation, large output extraction patterns. | FLI is unreachable, CLI output is truncated, 1-stop options missing despite segment offers existing, or need to parse 400KB+ JSON. | Normal route search with both providers healthy. |
| `tutu-mcp-provider.md` | Tutu MCP provider integration architecture: endpoint, response structure, IATA extraction, city-name resolution, normalization, capabilities, provider policy routing, known limitations. | Adding/maintaining the `tutu` provider, debugging Tutu search_avia normalization, or understanding the three-provider architecture. | Normal route search not involving Tutu. |
| `route-network-discovery.md` | Airport route network discovery via browser: when the CLI can't answer "where can I fly direct from X", source hierarchy (official site > Wikipedia), carousel/expandable-card extraction techniques, direct-vs-connecting classification, official-vs-Wikipedia comparison. | User asks for all direct destinations from an airport or route existence without a date — a network question, not a live-ticket-by-date question. | Live ticket search for a specific route+date (use the CLI golden path). |

## Routing examples

| Situation | Read |
|---|---|
| Report answer/read order, final answer source, renderer/schema change | `report-contract.md` |
| Single PNR, baggage-through, refund/exchange/fare-rule proof | `source-boundaries.md` |
| Empty provider output, absence language, structural vs provider/horizon uncertainty | `source-boundaries.md` |
| Exact airport vs city scope, KupiBilet `MOW`, FLI exact airport, London/Dubai/IST defaults | `provider-aware-airport-priority.md` |
| Global non-RU must not inherit RU/Moscow controls; market/intent/evidence classification | `pipeline-reference.md` |
| Current and historical gateway hardcode inventory | `gateway-hardcode-map.md` |
| Short/missing direct set, direct suppresses connected, `all_direct_inventory`, output caps | `pipeline-reference.md` first; `debug-playbook.md` only if a narrow live control is needed |
| Direct/nonstop options across several dates | `direct-date-window.md` |
| Provider failure, suspected horizon/coverage gap, targeted carrier/direct probe | `debug-playbook.md` |
| User specifies exact routing (via X→Y→Z), CLI doesn't assemble it | `provider-failover.md` → "Manual leg-by-leg assembly via `diagnose kb-search`" |
| Train-vs-flight price/time comparison | `rail-rzd-live-pricing.md` |
| Source/runtime parity, branch/publish/sync, generated artifacts, schema/test updates | `cli-maintenance.md` |

## Reference lifecycle

A reference remains canonical only if it owns a stable function in the table above. Historical fixes such as direct-priority incidents, flow-decision design notes, route examples, or provider bug reports should live in the owner file as compact rules/tests, not as separate active Markdown.
