# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the traveler. The public report is compact by design: it is the answer and decision evidence surface, not a debug trace.

## Active Contracts

- `flight_search_result.v3` is the public search envelope. It carries `data.agent_report` at the root and `data.route_result` without a nested report copy.
- `agent_report.v4` is the public agent report. Its only top-level layers are `route`, `evidence`, `frontier`, `user_answer`, and `agent_guidance`.
- `flight_search_user_answer.v7` is the canonical user-facing answer. `data.agent_report.user_answer.rendered_text` is the only final prose source.
- `flight_offer_graph.v1` remains active only as route-result diagnostic data at `data.route_result.live_search.offer_graph`.

There is no runtime adapter for previous agent-report or search-result envelopes.

## Public Report Shape

Read in this order:

1. `user_answer.rendered_text` — final traveler-facing Markdown/Telegram text.
2. `user_answer.catalog.items` — numbered user-visible options and structured itinerary blocks.
3. `frontier.decision_frontier` — selected decision layer and machine-readable frontier evidence.
4. `evidence.coverage` — compact counts, completeness, blocking evidence, and source-boundary warnings.
5. `evidence.through_fare_checks`, `evidence.provider_failures`, and `evidence.source_boundaries` — caveats and next-action evidence when they change confidence.
6. `agent_guidance` — canonical command, answer path, evidence completeness, and request patches for follow-up probes.

The public report must not duplicate full provider bodies, full coverage buckets, full graph data, display projections, or old recommendation aliases. Use `diagnose` commands or `route_result.live_search` for trace/debug work.

## Search Envelope

`search --request --json` returns:

```text
data
├── schema_version = flight_search_result.v3
├── wire_version = flight_search_result.v3
├── request
├── agent_report
└── route_result
```

The `route_result` object must not contain a report copy. Consumers should read the report only from `data.agent_report`.

## Answer Rules

`rendered_text` is derived from the structured `flight_search_user_answer.v7` object. Do not create another final-answer source or copy route diagnostics as prose.

For catalog answers:

- `catalog.items[]` numbers must be contiguous from 1.
- Each item carries `option_id`, trip coverage, ticketing model, price, outbound/return directions, baggage/protection status, caveats, and a deterministic `agent_display` block.
- Connected itineraries must show every segment and layover inside the affected direction.
- Unproven single-PNR, through-baggage, final fare, and purchase protection require purchase-screen or airline/GDS verification language.

`user_answer.answer_lines` is a split representation of the same rendered answer for validators and machine readers. It is not an alternate prose source.

## Evidence Boundaries

- Provider shopping results are evidence, not booking proof.
- Empty provider output is not proof of global route absence outside executed probes.
- Static catalog metadata cannot prove flight availability or absence.
- City-code requests describe scope; rendered itinerary endpoints must show actual airport codes when provider data has them.
- Provider aggregate one-way offers are candidates for purchase-screen verification, not protected round-trip proof.

## Debug Boundary

Full graph, search plan, gateway waves, provider payloads, and coverage buckets belong in existing debug surfaces:

- `diagnose plan`
- `diagnose probe`
- provider-specific `diagnose ...` commands
- `data.route_result.live_search`

Do not add public-report compatibility mirrors for these traces.
