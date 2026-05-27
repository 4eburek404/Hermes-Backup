# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the user. Raw CLI internals are debug-only.

## Read Order

1. `human_answer.text` - deterministic provider-neutral traveler-facing answer. Use it as the default final Telegram answer when present.
2. `recommended_options` - viable ranked options with segment details; cross-check decision-critical details before sending.
3. `priority_options` - controls that must stay visible even when lower-ranked, especially carrier-specific and Moscow/SVO controls.
4. `through_fare_checks` - routes that need airline/GDS/single-PNR verification.
5. `provider_failures` - unavailable provider evidence; name only when it affects the decision or evidence quality.
6. `source_boundaries` - caveats about source type and proof limits; print only decision-useful caveats.
7. `display` - deterministic itinerary fragments. Use as source material, not as the final Telegram answer shape.
8. `answer_lines` - internal compact summary and critical warnings; do not copy diagnostic/internal labels verbatim into the final user answer.
9. `hub_viability` / `rejected_pair_warnings` - explain missing or demoted routes only when useful.

## Detail Completeness

Do not present exact routing from a summary-only option. Any option named in `answer_lines`, `recommended_options`, or `priority_options` should carry `detail_status`:

- `full`: segments are present; safe to summarize.
- `summary_only`: price/time may be known, but segment details are incomplete.
- `missing`: do not infer the routing; rerun targeted debug.

`segment_results=[]` does not prove segment details are absent. Full route bodies can still live under `ranked_candidates[].candidate.journeys[].segments[]`. If the compact report clipped a cheaper, faster, direct, same-carrier, or Moscow-control option, escalate to debug instead of guessing.

## Recommendation Rules

Lead with `recommended_options[0]` only when it is viable, has `detail_status=full`, and no mandatory control materially changes the decision.

`agent_report.stop_policy_diagnostics.candidate_generation_mode` and `fallback_used` describe how assembly generated the candidate pool. Treat two-stop options as reportable only when fallback is explicitly active. Do not infer fallback mode from missing compact options or from aggregate controls alone.

Always surface materially different controls:

- cheapest acceptable when much cheaper;
- fastest acceptable when much faster;
- direct/nonstop controls;
- same-carrier or requested-carrier controls;
- Moscow/SVO controls for international routes from Russian origins when viable;
- airport-quality controls such as `LHR` for London business travel.

Explain lower ranking with concrete trade-offs: price, elapsed time, arrival time, airport quality, connection quality, ticketing/protection, or baggage.

## Route-Specific Decision Rules

Moscow/SVO is a first-class control for Russian-origin international routes, not a fallback. Show a viable via-SVO option even when a direct, IST/DXB, or other primary-hub option ranks better. The control must be a coherent same-airport route such as `origin -> SVO + SVO -> destination`; rejected `SVO vs IST` splices are invalid and should be explained as airport mismatches, not as viable itineraries.

Provider-aware airport priority is part of the report contract; see `references/provider-aware-airport-priority.md`. In particular, city codes describe request scope, while normalized offers and user-facing display must expose actual airport codes. For Moscow city-code results, validate actual airports against `SVO`/`DME`/`VKO`; for London, treat `LHR` as the default business-priority airport and `LGW` as fallback. `IST` is not `SAW` unless the user explicitly requested `SAW`.

`direct_destination_control` is a search branch, not a nonstop claim. RU-priority control visibility remains structural: validate linked `priority_options` fields (`control_family`, `control_branch`, `visibility_role`, and `priority_option_id`) instead of relying on `answer_lines` text.

For domestic Russian routes, do not let the `business` profile bury objectively better direct flights. If both airports are in Russia and direct domestic offers exist, lead with the cheapest/fastest direct option even when preferred-carrier scoring ranks an IST/SVO hub route higher. State that the business profile ranked the hub route higher because of carrier weighting, but the direct domestic route is cheaper/faster.

For SU-only or Aeroflot-only requests, use provider-assembled aggregate controls filtered by `SU` (`--aggregate-control-carrier SU`). Segment assembly can miss same-carrier through-PNR opportunities; aggregate controls may be the better evidence surface, but still require through-fare verification.

For a carrier-specific existence question, answer the carrier-route question first, then show alternatives. Run targeted direct/carrier controls before saying a carrier does not fly a route; `live-assemble` alone is not negative proof.

## Connection Trade-Offs

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons. Show them plainly as comfort/operations trade-offs. Keep real risk separate: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Answer Shape

For the final Telegram answer, prefer `human_answer.text` when present. It follows `SKILL.md` → `## User Answer Style` and is built from the report fields rather than copied from raw report/debug text.

Default order for round trips:

1. **Лучшая пара / рекомендация** — outbound line, return line, total price, ticketing/protection caveat.
2. **Альтернативы туда** — viable one-way outbound options, one compact line each.
3. **Альтернативы обратно** — viable one-way return options, one compact line each.
4. **Отсекаю / fallback** — only if useful: long waits, unprotected/self-transfer, multi-stop, or non-matching carriers.
5. **Проверить перед покупкой** — single PNR/protection, baggage-through, fare rules, terminals if connection risk matters.

Use `display.options[].lines`, `recommended_options`, and `priority_options` as evidence for those compact lines. Do not expose internal labels such as `rank`, `probe_id`, `coverage_diagnostics`, `provider_aggregate_candidate`, or `agent report:` in the final answer unless the user asks for diagnostics.

Never present summed separate-segment prices as confirmed airline/GDS through fares.
Never present `candidate_pool_limit` changes as a normal answer-quality strategy; missing preferred options are a CLI generation bug, not a reason to ask the user for a larger pool.

## Final Caveat Discipline

- Caveats must be decision-useful.
- Do not automatically print `source_boundaries`.
- Use provider-boundary caveats only when they change the user's decision or explain degraded evidence.
- For structural absence, say direct service is not available in normal booking channels, then move to connecting options.
- For ordinary provider/horizon uncertainty, say what targeted probe would reduce uncertainty.
- Do not answer with tool diagnosis when the user needs an itinerary recommendation.
