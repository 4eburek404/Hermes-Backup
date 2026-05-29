# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the user. The report is the evidence layer; `human_answer.text` is the deterministic traveler-facing layer. Raw CLI internals are debug-only.

## Read Order

1. `human_answer.text` — provider-neutral Telegram/Markdown answer. Default final answer source when present.
2. `recommended_options` — viable ranked options with segment details; cross-check decision-critical details.
3. `priority_options` — controls that must stay visible even when lower-ranked: carrier-specific, direct/nonstop, exact-airport, Moscow/SVO, fastest, cheapest, or airport-quality controls.
4. `through_fare_checks` — ticketing/protection evidence and required purchase-screen checks.
5. `provider_failures` — degraded provider evidence; mention only when it changes confidence or next action.
6. `source_boundaries` — source/proof limits; print only decision-useful caveats.
7. `display` — deterministic itinerary fragments for evidence, not final prose.
8. `answer_lines` — compact internal summary/warnings; do not copy diagnostic labels into final answers.
9. `hub_viability`, `coverage_diagnostics`, `rejected_pair_warnings`, `stop_policy_diagnostics` — diagnostics for missing/demoted routes, not normal user output.

## Detail Completeness

Do not present exact routing from a summary-only option. Any option named in `answer_lines`, `recommended_options`, or `priority_options` should carry `detail_status`:

- `full`: segments are present; safe to summarize.
- `summary_only`: price/time may be known, but segment details are incomplete.
- `missing`: do not infer routing; rerun a targeted probe or debug the report.

`segment_results=[]` does not prove segment details are absent. Full route bodies can still live under `ranked_candidates[].candidate.journeys[].segments[]`. If the compact report clipped a cheaper, faster, direct, same-carrier, exact-airport, or Moscow-control option, escalate to `references/debug-playbook.md` instead of guessing.

## Recommendation Rules

Lead with `recommended_options[0]` only when it is viable, has `detail_status=full`, and no mandatory control materially changes the decision.

Always surface materially different controls:

- cheapest acceptable when materially cheaper;
- fastest acceptable when materially faster;
- direct/nonstop controls;
- same-carrier or requested-carrier controls;
- Moscow/SVO controls for Russian-origin international routes when viable;
- airport-quality controls such as `LHR` for London business travel;
- safer ticketing/protection or baggage handling when price/time is close.

Explain lower ranking with concrete trade-offs: price, elapsed time, arrival time, airport quality, connection quality, ticketing/protection, baggage, or source confidence.

`agent_report.stop_policy_diagnostics.candidate_generation_mode` and `fallback_used` describe how assembly generated the candidate pool. Treat two-stop options as reportable only when fallback is explicitly active or the report marks them reportable. Do not infer fallback mode from missing compact options or aggregate controls alone.

## Route-Specific Controls

Moscow/SVO is a first-class control for Russian-origin international routes, not fallback-only behavior. Show a viable via-SVO option even when a direct, IST/DXB, or other primary-hub option ranks better. The control must be a coherent same-airport route such as `origin -> SVO + SVO -> destination`; rejected `SVO vs IST` splices are invalid and should be explained as airport mismatches, not as viable itineraries.

Provider-aware airport priority is part of the report contract; see `references/provider-aware-airport-priority.md`. City codes describe request scope, while normalized offers and user-facing display must expose actual airport codes. For Moscow city-code results, validate actual airports against `SVO`/`DME`/`VKO`; for London, treat `LHR` as the default business-priority airport and `LGW` as fallback. `IST` is not `SAW` unless the user explicitly requested `SAW`.

`direct_destination_control` is a search branch, not a nonstop claim. RU-priority control visibility remains structural: validate linked `priority_options` fields (`control_family`, `control_branch`, `visibility_role`, and `priority_option_id`) instead of relying on `answer_lines` text.

For domestic Russian routes, do not let the `business` profile bury objectively better direct flights. If both airports are in Russia and direct domestic offers exist, lead with the cheapest/fastest direct option even when preferred-carrier scoring ranks a hub route higher. State that the profile ranked the hub route higher because of carrier weighting, but the direct domestic route is cheaper/faster.

For carrier-specific existence questions, answer the carrier-route question first, then show alternatives. Run targeted direct/carrier controls before saying a carrier does not fly a route; `live-assemble` alone is not negative proof.

## Human Answer Renderer Contract

The provider-neutral seam is:

`data.agent_report` -> `human_answer` -> final Telegram/Markdown answer.

Implement final-output behavior in `cli/flights_cli/reporting/human_answer_renderer.py`. Do not make agents copy `display.text`, `answer_lines`, provider client objects, booking URLs, cache semantics, or plugin-specific wording.

Negative guarantees for `human_answer.text` and final answers:

- no `agent report:`;
- no `Best CLI-ranked option`;
- no `Coverage diagnostics`;
- no `provider_aggregate_candidate` or `provider-aggregate:`;
- no raw `probe_id`, ranks, coverage structs, or pipe tables;
- no collapsed multi-leg journey that hides each segment's departure and arrival time.

Connected itineraries should show per-segment times, for example:

`SU1437 18:10–18:55 -> SU1844 20:35–21:55 | 01 авг | SVO 1ч40 | всего 5ч45`

Do not collapse that into only first departure and final arrival for a multi-leg journey. If a later segment departs on a different date, show that date inline.

## Answer Shape

For ordinary one-way tasks, start with `нашёл`, `не нашёл`, or `evidence неполное`, then give the recommendation and decision-critical alternatives/caveats.

For round trips:

1. **Лучшая пара / рекомендация** — outbound line, return line, total price, ticketing/protection caveat.
2. **Альтернативы туда** — viable one-way outbound options, compact line each.
3. **Альтернативы обратно** — viable one-way return options, compact line each.
4. **Отсекаю / fallback** — only if useful: long waits, unprotected/self-transfer, multi-stop, or non-matching carriers.
5. **Проверить перед покупкой** — single PNR/protection, baggage-through, fare rules, terminals when connection risk matters.

Use `display.options[].lines`, `recommended_options`, and `priority_options` as evidence for compact lines. Never present summed separate-segment prices as confirmed airline/GDS through fares.

## Final Caveat Discipline

- Caveats must be decision-useful.
- Do not automatically print `source_boundaries`.
- Use provider-boundary caveats only when they change the user's decision or explain degraded evidence.
- For structural absence, answer the direct/carrier question first, then move to connecting options.
- For provider/horizon uncertainty, say what targeted probe would reduce uncertainty.
- Do not answer with tool diagnosis when the user needs an itinerary recommendation.
