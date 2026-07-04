# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the user. The report is the evidence layer; `frontier.offer_graph` is the primary decision graph; `user_answer.rendered_text` is canonical renderer output; `diagnostics.human_answer.text` is a mirror-only diagnostic field, not an alternative final-prose source. Raw CLI internals are debug-only.

## Active Contract Registry

Current contracts:

- `flight_search_result.v2` — public search result envelope. It carries `route_result` and the current `agent_report`.
- `agent_report.v3` — public serialized report envelope. Required top-level layers are `route`, `evidence`, `frontier`, `user_answer`, `agent_guidance`, and `diagnostics`.
- `flight_search_user_answer.v6` — canonical user-facing contract. Built by `cli/flights_cli/reporting/user_answer.py`, validated before `agent_report.user_answer` is accepted, and rendered through `user_answer.rendered_text`.

Retired/projection surfaces:

- Older user-answer schemas are rejected; there is no runtime adapter from retired answer shapes.
- `diagnostics.human_answer` is a mirror-only diagnostic projection; `diagnostics.display` and `diagnostics.answer_lines` are debug projections. They are not canonical final-prose sources and are not alternative inputs.
- In-process legacy alias views are removed; serialized JSON and internal consumers should use nested current-contract paths.

Shadow subcontracts:

- `common.v2`, `search_evidence.v2`, and `offer_frontier.v2` are not packaged active schemas. Reintroduce only with schema, builder, validator, and tests in the same change.

Retired/proposed candidates:

- Older agent-report and user-answer schema files are not packaged active schemas.
- The retired final-answer proposal / `route live-answer` is not an active runtime contract unless a schema, builder, command path, and exactness regression tests exist. Until then the active seam remains `agent_report.v3.user_answer.rendered_text`.

## Read Order

`offer_graph` — primary decision graph; in serialized `agent_report.v3` it lives at `frontier.offer_graph`.

1. `frontier.offer_graph` — primary decision graph. Read `constraints`, `collection`, `evidence`, `frontier`, `missing_evidence`, and `truth_language` before deciding whether the answer is complete enough.
2. `agent_guidance` — machine guidance for the agent: canonical command, answer path, execution/evidence completeness, blocking evidence buckets, and request patches for next actions.
3. `user_answer.rendered_text` — canonical provider-neutral Telegram/Markdown rendering of the selected frontier. Use it as renderer output, not as proof that collection was exhaustive.
4. `frontier.decision_frontier.options` — viable selected route options with segment details; cross-check decision-critical details.
5. `frontier.decision_frontier.controls` — controls that must stay visible even when they are not route options: carrier-specific, direct/nonstop, exact-airport, Moscow/SVO, fastest, cheapest, or airport-quality controls.
6. `evidence.through_fare_checks` — ticketing/protection evidence and required purchase-screen checks.
7. `evidence.provider_failures` — degraded provider evidence; mention only when it changes confidence or next action.
8. `evidence.source_boundaries` — source/proof limits; print only decision-useful caveats.
9. `diagnostics.human_answer.text` — mirror-only diagnostic field; while present it must mirror `user_answer.rendered_text`, and must not have independent rendering logic.
10. `diagnostics.display` — deterministic itinerary fragments for evidence, not final prose.
11. `diagnostics.answer_lines` — compact internal summary/warnings; do not copy diagnostic labels into final answers.
12. `diagnostics.hub_viability`, `diagnostics.coverage_diagnostics`, `diagnostics.rejected_pair_warnings`, `diagnostics.stop_policy_diagnostics` — diagnostics for missing/demoted routes, not normal user output.

If a report exposes old top-level `recommended_options`, `priority_options`, `offer_graph`, `answer_lines`, `display`, `human_answer`, `coverage_diagnostics`, `provider_failures`, or `source_boundaries`, treat it as internal flat builder input or stale output. Public serialized reports must use current nested paths.

## Detail Completeness

Do not present exact routing from a summary-only option. Any route option named in `frontier.decision_frontier.options[]` should carry `detail_status`; any control in `frontier.decision_frontier.controls[]` should stay evidence-only unless it contains full route details:

- `full`: segments are present; safe to summarize.
- `summary_only`: price/time may be known, but segment details are incomplete.
- `missing`: do not infer routing; rerun a targeted probe or debug the report.

`segment_results=[]` does not prove route details are absent. Full route bodies now live in `frontier.decision_frontier.options[]`; visibility checks and policy probes live in `frontier.decision_frontier.controls[]`; graph evidence lives in `evidence.offer_graph`. If the compact report clipped a cheaper, faster, direct, same-carrier, exact-airport, or control option, escalate to `references/debug-playbook.md` instead of guessing.

## Progressive Evidence and Offer Graph Discipline

Treat the first live provider response as an initial frontier, not as complete inventory. The decision loop is:

1. Build the unified offer graph from all available offers/controls.
2. Read request constraints as hard/soft scope: directness, carrier, exact airport, baggage, timing, ticketing/protection, price sensitivity, and operational profile.
3. Compare the current frontier against mandatory controls. Missing direct, carrier-specific, exact-airport, through-fare, or materially cheaper/faster evidence is `missing_evidence`, not a final absence claim.
4. Run bounded progressive collection when it can change the answer: polling/additional provider probes, targeted carrier/direct/exact-airport controls, hub-leg probes, or purchase-screen/through-fare checks.
5. Stop only when the completeness limit is reached, the source is exhausted, further probes would not change the recommendation/frontier, or an explicit time budget is exhausted.
6. Phrase truth claims at the evidence boundary: “нашёл все прямые, которые вернул live-поставщик” / “provider evidence неполное”, not “все возможные рейсы” unless the source actually proves exhaustiveness.

The user-facing frontier should include every option needed for the decision, not every raw offer: best viable recommendation, materially different direct/nonstop controls, requested-carrier/exact-airport controls, safer ticketing/protection, and meaningful cheapest/fastest alternatives. Hide dominated duplicates unless the user asks for raw inventory.

## Recommendation Rules

Lead with the first viable `frontier.decision_frontier.options[]` entry only when it has `detail_status=full` and no mandatory control materially changes the decision.

Always surface materially different controls:

- cheapest acceptable when materially cheaper;
- fastest acceptable when materially faster;
- direct/nonstop controls;
- same-carrier or requested-carrier controls;
- Moscow/SVO controls for Russian-origin international routes when viable;
- airport-quality controls such as `LHR` for London business travel;
- safer ticketing/protection or baggage handling when price/time is close.

Explain lower ranking with concrete trade-offs: price, elapsed time, arrival time, airport quality, connection quality, ticketing/protection, baggage, or source confidence.

Stop-policy diagnostics describe how assembly generated the candidate pool. Treat two-stop options as reportable only when the two-stop tier is explicitly active or the report marks them reportable. Do not infer two-stop tier mode from missing compact options or aggregate controls alone.

## Route-Specific Controls

Moscow/SVO controls, domestic-RU direct visibility, and carrier-specific existence questions are report contract concerns only when they affect `frontier.decision_frontier.controls[]`, `control_family`, `control_branch`, `visibility_role`, `priority_option_id`, or absence language. Detailed provider/airport dispatch policy lives in `references/provider-aware-airport-priority.md`; detailed debug probes live in `references/debug-playbook.md`.

Provider-aware airport priority is part of the report contract: city codes describe request scope, while normalized offers and user-facing display must expose actual airport codes. `direct_destination_control` is a search branch, not a nonstop claim. Validate structured fields instead of relying on `answer_lines` text.

## User Answer Renderer Contract

The provider-neutral seam is:

```text
data.agent_report
  -> user_answer (flight_search_user_answer.v6)
  -> user_answer.rendered_text
  -> final Telegram/Markdown answer
```

`rendered_text` is a deterministic projection from the v3 object. Do not make it an independent blob. `diagnostics.human_answer.text` is diagnostics-only and must mirror `user_answer.rendered_text` while both exist.

Implementation ownership:

- `cli/flights_cli/reporting/user_answer.py` builds/validates the v5 user answer and deterministic rendered text.
- `cli/flights_cli/reporting/projections/human_answer_mirror.py` and `cli/flights_cli/output.py` may only mirror or select `user_answer.rendered_text`.
- Agents must not copy `display.text`, `answer_lines`, provider client objects, booking URLs, cache semantics, or plugin-specific wording as final prose.

Negative guarantees for `user_answer.rendered_text`, legacy `human_answer.text`, and final answers:

- no `agent report:`;
- no `Best CLI-ranked option`;
- no `Coverage diagnostics`;
- no `provider_aggregate_candidate` or `provider-aggregate:`;
- no raw `probe_id`, ranks, coverage structs, or pipe tables;
- no collapsed multi-leg journey that hides each segment's departure and arrival time.

Connected itineraries must show every segment as its own line and put the layover line between adjacent segments in the same direction:

```text
1. SU1401 23.07 Екатеринбург - Шереметьево(B) 13:10 13:50 A320 в пути 2:40
    пересадка 3:25,
    MU2076 23.07 Шереметьево(C) - Пекин 17:15 05:30 (24.07) A333 в пути 7:15
    46 909 рублей
```

Do not collapse that into only first departure and final arrival for a multi-leg journey. If a later segment arrives on a different date, show that date inline after the arrival time. Endpoints in a multi-airport city must show the actual airport name and terminal when provider data includes one, even when they are the initial origin or final destination.

## User Answer Contract v5

`flight_search_user_answer.v6` is the enforceable user-facing contract for CLI reports. It lives in `cli/flights_cli/contracts/flight_search_user_answer.v6.schema.json`, is built by `cli/flights_cli/reporting/user_answer.py`, and is semantically validated before `agent_report.user_answer` is accepted.

Required v5 fields:

- `schema_version="flight_search_user_answer.v6"`.
- `answer_mode`: `recommendation`, `catalog`, or `no_viable_options`. The builder infers mode from route/frontier; do not add public “catalog mode” flags.
- `catalog.presentation`: deterministic compact numbered Russian output metadata with `style="numbered_inline_itinerary_v1"`.
- `catalog.items[]`: one item per user-visible frontier option. Numbers must be contiguous from 1. Each item carries `option_id`, `covers_requested_trip`, `journey_scope`, `ticketing_model`, `total_price`, `directions.outbound/return`, `baggage`, `protection`, `badges`, `caveats`, `agent_display`, and `render_line`.
- User-visible catalog order is deterministic: viable non-rejected full-trip options first, then lower `max_connections_per_journey` (nonstop/direct before one-stop), then price, itinerary elapsed time, and source rank. `ok=false` or `risk.reject=true` options are diagnostics only and must not appear in `catalog.items[]`.
- `catalog.items[*].agent_display`: schema-backed agent output block with `style="inline_number_itinerary_with_aircraft_duration_v1"`, `lines[]`, and `text`. For full-detail options, the block is:
  `N. FLIGHT DD.MM Origin city - Destination city HH:MM HH:MM (arrival DD.MM when different) AIRCRAFT в пути H:MM`
  `    пересадка H:MM,`
  `    FLIGHT DD.MM Origin city - Destination city HH:MM HH:MM (arrival DD.MM when different) AIRCRAFT в пути H:MM`
  `    price рублей`
  The layover line appears only between adjacent segments inside the same outbound or return direction; it is not printed after the direction or between outbound and return directions. Connection endpoints and any endpoint in a multi-airport city must use actual airport labels, not only city labels; append the provider terminal as `(B)`, `(C)`, `(2)`, etc. when present.
- Derived summary fields remain present for validation and machine readers: `primary_recommendation`, `alternatives`, `evidence_status`, `required_caveats`, `stop_policy_status`, `rendered_text`, `answer_lines`.

Semantic validation must reject: empty catalog mode, non-contiguous numbering, rendered text that loses numbered catalog items, `agent_display`/`render_line` drift, standalone number lines, segment lines without aircraft/duration, missing indentation on continuation/price lines, round-trip catalog items without outbound+return directions, unproven ticketing models that do not require purchase-screen verification.

Mutation guardrails for renderer/user-answer changes:

- False single-PNR, through-fare, baggage-through, protected-connection, terminal, or final-price claims must fail unless supported by structured evidence.
- Required caveats in `required_caveats`, ticketing model, missing evidence, or source boundaries must remain visible in `rendered_text` when they change the decision.
- `catalog.items[*].render_line` must mirror `catalog.items[*].agent_display.text`; both must stay derived from structured route, price, risk, direction, baggage, and protection fields. Mutate-and-validate tests should catch contradictory rendered dates, prices, segments, or mode/catalog state.
- Diagnostic summary projections may mirror the rendered text for debugging, but must not become a separate source for final prose.

MCP `outputSchema` is only a transport description for `structuredContent`. It does not replace the domain schema, builder, semantic validator, or renderer.

## Answer Shape

For ordinary one-way tasks, start with `нашёл`, `не нашёл`, or `evidence неполное`, then give the recommendation and decision-critical alternatives/caveats.

For round trips and multi-option frontiers, use v5 catalog shape:

1. Compact numbered options from `catalog.items[].agent_display`; each block starts with `N. FLIGHT ...`, continuation segment lines and the price line are indented by four spaces.
2. Keep safer ticketing/protection/baggage options visible even when they are not cheapest.
3. Keep one-way/provider aggregates visible only as directional alternatives; do not present them as covering a round trip.
4. End with `Проверить перед покупкой`: single PNR/protection, baggage-through, fare rules, terminals when connection risk matters.

Use `diagnostics.display.options[].lines`, `frontier.decision_frontier.options[]`, and `frontier.decision_frontier.controls[]` only as evidence to build the v5 object. Never present summed separate-segment prices as confirmed airline/GDS through fares.

## Final Caveat Discipline

- Caveats must be decision-useful.
- Do not automatically print `source_boundaries`.
- Use provider-boundary caveats only when they change the user's decision or explain degraded evidence.
- For structural absence, answer the direct/carrier question first, then move to connecting options.
- For provider/horizon uncertainty, say what targeted probe would reduce uncertainty.
- Do not answer with tool diagnosis when the user needs an itinerary recommendation.
