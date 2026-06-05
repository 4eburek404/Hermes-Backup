# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the user. The report is the evidence layer; `frontier.offer_graph` is the primary decision graph; `user_answer.rendered_text` is canonical renderer output; `diagnostics.human_answer.text` is a debug mirror, not a fallback final-prose source. Raw CLI internals are debug-only.

## Active Contract Registry

Current contracts:

- `agent_report.v2` — public serialized report envelope. Required top-level layers are `route`, `evidence`, `frontier`, `user_answer`, and `diagnostics`.
- `flight_search_user_answer.v3` — canonical user-facing contract. Built by `cli/flights_cli/reporting/final_answer_contract.py`, validated before `agent_report.user_answer` is accepted, and rendered through `user_answer.rendered_text`.

Retired/projection surfaces:

- `flight_search_user_answer.v2` is rejected; there is no v2→v3 runtime adapter.
- `diagnostics.human_answer`, `diagnostics.display`, and `diagnostics.answer_lines` are debug/mirror projections. They are not canonical final-prose sources and are not fallback inputs.
- In-process legacy alias views are removed; serialized JSON and internal consumers should use nested v2 paths.

Shadow subcontracts:

- `common.v2`, `search_evidence.v2`, and `offer_frontier.v2` are not packaged active schemas. Reintroduce only with schema, builder, validator, and tests in the same change.

Retired/proposed candidates:

- `agent_report.v1`, `flight_search_user_answer.v1`, and `flight_search_user_answer.v2` are not packaged active schemas.
- `flight_search_final_answer.v1` / `route live-answer` is not an active runtime contract unless a schema, builder, command path, and exactness regression tests exist. Until then the active seam remains `agent_report.v2.user_answer.rendered_text`.

## Read Order

`offer_graph` — primary decision graph; in serialized `agent_report.v2` it lives at `frontier.offer_graph`.

1. `frontier.offer_graph` — primary decision graph. Read `constraints`, `collection`, `evidence`, `frontier`, `missing_evidence`, and `truth_language` before deciding whether the answer is complete enough.
2. `user_answer.rendered_text` — canonical provider-neutral Telegram/Markdown rendering of the selected frontier. Use it as renderer output, not as proof that collection was exhaustive.
3. `frontier.recommended_options` — viable ranked options with segment details; cross-check decision-critical details.
4. `frontier.priority_options` — controls that must stay visible even when lower-ranked: carrier-specific, direct/nonstop, exact-airport, Moscow/SVO, fastest, cheapest, or airport-quality controls.
5. `evidence.through_fare_checks` — ticketing/protection evidence and required purchase-screen checks.
6. `evidence.provider_failures` — degraded provider evidence; mention only when it changes confidence or next action.
7. `evidence.source_boundaries` — source/proof limits; print only decision-useful caveats.
8. `diagnostics.human_answer.text` — debug mirror; while present it must mirror `user_answer.rendered_text`, but it is not fallback final prose.
9. `diagnostics.display` — deterministic itinerary fragments for evidence, not final prose.
10. `diagnostics.answer_lines` — compact internal summary/warnings; do not copy diagnostic labels into final answers.
11. `diagnostics.hub_viability`, `diagnostics.coverage_diagnostics`, `diagnostics.rejected_pair_warnings`, `diagnostics.stop_policy_diagnostics` — diagnostics for missing/demoted routes, not normal user output.

If a report exposes old top-level `recommended_options`, `priority_options`, `offer_graph`, `answer_lines`, `display`, `human_answer`, `coverage_diagnostics`, `provider_failures`, or `source_boundaries`, treat it as internal flat builder input or stale output. Public serialized reports must use v2 nested paths.

## Detail Completeness

Do not present exact routing from a summary-only option. Any option named in `answer_lines`, `recommended_options`, or `priority_options` should carry `detail_status`:

- `full`: segments are present; safe to summarize.
- `summary_only`: price/time may be known, but segment details are incomplete.
- `missing`: do not infer routing; rerun a targeted probe or debug the report.

`segment_results=[]` does not prove segment details are absent. Full route bodies can still live under `ranked_candidates[].candidate.journeys[].segments[]`. If the compact report clipped a cheaper, faster, direct, same-carrier, exact-airport, or Moscow-control option, escalate to `references/debug-playbook.md` instead of guessing.

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

Lead with `frontier.recommended_options[0]` only when it is viable, has `detail_status=full`, and no mandatory control materially changes the decision.

Always surface materially different controls:

- cheapest acceptable when materially cheaper;
- fastest acceptable when materially faster;
- direct/nonstop controls;
- same-carrier or requested-carrier controls;
- Moscow/SVO controls for Russian-origin international routes when viable;
- airport-quality controls such as `LHR` for London business travel;
- safer ticketing/protection or baggage handling when price/time is close.

Explain lower ranking with concrete trade-offs: price, elapsed time, arrival time, airport quality, connection quality, ticketing/protection, baggage, or source confidence.

Stop-policy diagnostics describe how assembly generated the candidate pool. Treat two-stop options as reportable only when fallback is explicitly active or the report marks them reportable. Do not infer fallback mode from missing compact options or aggregate controls alone.

## Route-Specific Controls

Moscow/SVO controls, domestic-RU direct visibility, and carrier-specific existence questions are report contract concerns only when they affect `frontier.priority_options`, `control_family`, `control_branch`, `visibility_role`, `priority_option_id`, or absence language. Detailed provider/airport dispatch policy lives in `references/provider-aware-airport-priority.md`; detailed debug probes live in `references/debug-playbook.md`.

Provider-aware airport priority is part of the report contract: city codes describe request scope, while normalized offers and user-facing display must expose actual airport codes. `direct_destination_control` is a search branch, not a nonstop claim. Validate structured fields instead of relying on `answer_lines` text.

## User Answer Renderer Contract

The provider-neutral seam is:

```text
data.agent_report
  -> user_answer (flight_search_user_answer.v3)
  -> user_answer.rendered_text
  -> final Telegram/Markdown answer
```

`rendered_text` is a deterministic projection from the v3 object. Do not make it an independent blob. `diagnostics.human_answer.text` is legacy and must mirror `user_answer.rendered_text` while both exist.

Implementation ownership:

- `cli/flights_cli/reporting/final_answer_contract.py` builds/validates the v3 user answer and deterministic rendered text.
- `cli/flights_cli/reporting/human_answer_renderer.py` and `cli/flights_cli/output.py` are compatibility/rendering seams; they must prefer `user_answer.rendered_text`.
- Agents must not copy `display.text`, `answer_lines`, provider client objects, booking URLs, cache semantics, or plugin-specific wording as final prose.

Negative guarantees for `user_answer.rendered_text`, legacy `human_answer.text`, and final answers:

- no `agent report:`;
- no `Best CLI-ranked option`;
- no `Coverage diagnostics`;
- no `provider_aggregate_candidate` or `provider-aggregate:`;
- no raw `probe_id`, ranks, coverage structs, or pipe tables;
- no collapsed multi-leg journey that hides each segment's departure and arrival time.

Connected itineraries should show per-segment times, for example:

`SU1437 18:10–18:55 -> SU1844 20:35–21:55 | 01 авг | SVO 1ч40 | всего 5ч45`

Do not collapse that into only first departure and final arrival for a multi-leg journey. If a later segment departs on a different date, show that date inline.

## User Answer Contract v3

`flight_search_user_answer.v3` is the enforceable user-facing contract for CLI reports. It lives in `cli/flights_cli/contracts/flight_search_user_answer.v3.schema.json`, is built by `cli/flights_cli/reporting/final_answer_contract.py`, and is semantically validated before `agent_report.user_answer` is accepted.

Required v3 fields:

- `schema_version="flight_search_user_answer.v3"`.
- `answer_mode`: `recommendation`, `catalog`, or `no_viable_options`. The builder infers mode from route/frontier; do not add public “catalog mode” flags.
- `catalog.presentation`: deterministic compact numbered Russian output metadata.
- `catalog.items[]`: one item per user-visible frontier option. Numbers must be contiguous from 1. Each item carries `option_id`, `covers_requested_trip`, `journey_scope`, `ticketing_model`, `total_price`, `directions.outbound/return`, `baggage`, `protection`, `badges`, `caveats`, and `render_line`.
- Legacy-compatible fields remain present for readers during migration: `primary_recommendation`, `alternatives`, `evidence_status`, `required_caveats`, `stop_policy_status`, `rendered_text`, `answer_lines`.

Semantic validation must reject: empty catalog mode, non-contiguous numbering, rendered text that loses numbered catalog items, round-trip catalog items without outbound+return directions, unproven ticketing models that do not require purchase-screen verification.

MCP `outputSchema` is only a transport description for `structuredContent`. It does not replace the domain schema, builder, semantic validator, or renderer.

## Answer Shape

For ordinary one-way tasks, start with `нашёл`, `не нашёл`, or `evidence неполное`, then give the recommendation and decision-critical alternatives/caveats.

For round trips and multi-option frontiers, use v3 catalog shape:

1. Numbered compact options from `catalog.items[]`; each line must include price, outbound/return detail when available, and decision-critical risk badges/caveats.
2. Keep safer ticketing/protection/baggage options visible even when they are not cheapest.
3. Keep one-way/provider aggregates visible only as directional alternatives; do not present them as covering a round trip.
4. End with `Проверить перед покупкой`: single PNR/protection, baggage-through, fare rules, terminals when connection risk matters.

Use `diagnostics.display.options[].lines`, `frontier.recommended_options`, and `frontier.priority_options` only as evidence to build the v3 object. Never present summed separate-segment prices as confirmed airline/GDS through fares.

## Final Caveat Discipline

- Caveats must be decision-useful.
- Do not automatically print `source_boundaries`.
- Use provider-boundary caveats only when they change the user's decision or explain degraded evidence.
- For structural absence, answer the direct/carrier question first, then move to connecting options.
- For provider/horizon uncertainty, say what targeted probe would reduce uncertainty.
- Do not answer with tool diagnosis when the user needs an itinerary recommendation.
