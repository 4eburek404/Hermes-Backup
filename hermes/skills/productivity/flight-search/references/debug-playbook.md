# Debug and Exception Probe Playbook

Use this playbook only when the Golden Path report is internally inconsistent, degraded, too sparse for the user constraint, or surprising enough that a narrow diagnostic probe could change the answer. Debugging supports `search --request`; it does not replace it.

Reference map: `references/index.md`. Report reading contract: `references/report-contract.md`.

## When to debug

Start from the canonical command in `SKILL.md`. Enter debug only when one of these is true:

- `agent_guidance.answer_readiness` says more evidence is needed;
- `evidence.provider_failures`, `coverage_diagnostics.failed_controls`, or `not_executed_controls` changes confidence;
- a direct, carrier, exact-airport, Moscow/SVO, cheapest, fastest, or safer-ticketing control is missing or summary-only;
- provider output conflicts with source boundaries or route geography;
- date horizon, airport continuity, stop-policy tiering, cache state, or ranking profile could hide a viable option;
- the user asks for narrower proof than the report already contains.

Do not expose diagnostic JSON or probe logs as the traveler answer. Final prose still comes from `data.agent_report.user_answer.rendered_text` unless you are explicitly explaining a debug/RCA task.

## Runtime provenance

Before naming a provider/root cause or patching behavior, prove the runtime used for the probe:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
command -v flights || true
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --version
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import flights_cli, pathlib
print(pathlib.Path(flights_cli.__file__).resolve())
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli search --help
```

Record only decision-useful provenance:

- runtime path, imported module path, CLI version, and live help;
- source path, branch, HEAD, dirty state when source behavior is in scope;
- request normalization: route/date/currency/profile, exact-airport vs city scope, filters, provider policy, stop policy, direct-only/date-window/ticketing fields;
- whether the conclusion came from `data.agent_report`, a diagnostic probe, or external source evidence.

Temp editable checkouts can shadow the permanent skill CLI; do not generalize traces until executable/import paths are known. `maint doctor` is environment/readiness evidence, not flight availability evidence.

## JSON extraction

Read only JSON payloads for decisions. If logs surround JSON, extract the envelope first, then inspect `data.agent_report`.

Decision read order is in `report-contract.md`; compact debug order:

1. `data.agent_report.agent_guidance` — command, answer path, readiness, blocking evidence.
2. `data.agent_report.frontier.offer_graph` — constraints, collection, evidence, missing evidence, truth language.
3. `data.agent_report.user_answer.rendered_text` — canonical final rendering.
4. `frontier.recommended_options` / `priority_options` — decision-critical options and controls.
5. `evidence.*` — through-fare checks, provider failures, source boundaries, coverage diagnostics.
6. `diagnostics.*` — debug only.

If JSON parsing or schema validation fails, report the parse/contract layer and rerun with JSON-clean stdout/stderr settings before making a travel claim.

## Targeted probe commands

Run the narrowest probe that answers the remaining uncertainty. Label probe results as narrower evidence than the assembled report unless you prove the main report missed a mandatory control.

Main report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request request.json
```

Provider-port diagnostic:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose probe \
  --provider tutu \
  --request probe.json
```

Tutu raw search diagnostic:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose tutu-search \
  ORIGIN DEST \
  --depart-date YYYY-MM-DD
```

Direct/carrier controls with KupiBilet:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20

PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --limit 20
```

KupiBilet one-checkout round-trip control:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose kb-roundtrip ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --direct-only \
  --limit 20
```

FLI exact-airport direct control:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20
```

Probe shapes:

- exact-airport direct-only;
- city-code direct-only when city scope is intended and the provider supports it;
- alternate airport only when city-wide search is allowed;
- carrier-specific direct or aggregate control for carrier questions;
- round-trip provider aggregate when the user asks for one order/single checkout;
- nearby in-horizon control date to split horizon uncertainty from route coverage.

## Short or missing direct set

When the report shows fewer direct flights than expected:

1. Confirm the request scope: exact airport vs city, direct-only vs default recommendation, one-way vs return.
2. Start with the canonical report and Tutu/provider-port diagnostics because `auto` is Tutu-first. Use `diagnose kb-search ... --direct-only` or `diagnose fli-search ... --direct-only` only for explicit provider comparison or source-boundary checks.
3. If the provider probe returns all direct offers with prices, the provider is not the root cause; inspect display/report truncation.
4. Inspect counts:
   - `data.route_result.live_search.decision_frontier.options`;
   - `data.route_result.live_search.offer_graph.edges`;
   - `data.route_result.live_search.primary_offer_results`;
   - `data.agent_report.frontier.decision_frontier.options`;
   - `data.agent_report.status` / `agent_guidance` if exposed.
5. Current pipeline computes the direct-first gate from wave-0 offer evidence and projects active directions into `report["status"]["direct_mode"]` before budgeting/user-answer construction. If direct offers vanish after that point, debug report projection/budget, not provider availability.

Do not claim “provider did not return prices” when a narrow direct probe shows priced direct offers.

## Moscow controls for RU-touching international

Negative direct/carrier/one-stop claims on Russian-origin international routes need Moscow controls unless structural constraints already prove unavailability.

For `ru-priority`, current runtime plans these controls itself. Read terminal states from `evidence.coverage_diagnostics` and RU-priority fields before assuming anything is missing:

- `direct_destination_control`;
- `ist_primary_hub_control`;
- `moscow_gateway_control` with `gateway_to_destination` and mirrored return legs;
- secondary controls when the priority route is not viable.

Manual leg probes are for degraded/legacy reports only. If a compact or old report lists Moscow/carrier controls as `not_executed`, first rerun canonical `search --request`; then use narrow direct leg controls only if needed:

- outbound date: `SVO|DME|VKO -> DEST --direct-only`;
- return date: `DEST -> SVO|DME|VKO --direct-only`;
- origin↔Moscow legs when the main report lacks them and they are decision-critical.

If a wide live assembly fails validation, do not answer from the failed report. Use narrow controls and label them as control evidence, not full itinerary assembly.

## Russia-origin routes with avoid-Moscow preference and arrival deadline

Use this route-family pattern when the user asks for Russia-origin international flights, has an arrival-by deadline, and phrases Moscow avoidance as a preference rather than a hard constraint.

Rules:

1. Normalize named destination airports separately; do not collapse nearby destination airports unless the user allowed city/region scope.
2. If departure date is absent, state the working assumption. Default “morning” to destination-local arrival before 12:00.
3. Search latest plausible departure first, then previous date if needed.
4. Run Golden Path for each serious airport/date pair.
5. If non-Moscow is decision-critical, run narrow direct/carrier/leg controls and post-filter normalized segments.

Post-filter:

- reject Moscow airports (`SVO`, `DME`, `VKO`, `ZIA`, and `MOW` when present) only when the user’s preference is a hard filter or while comparing non-Moscow alternatives;
- outbound must arrive before the destination-local cutoff;
- separate one-stop from two-stop options; two-stop return is last resort for business travel unless no one-stop non-Moscow option exists;
- elapsed time comes from ISO timestamps already in normalized offers.

Wording:

- “Желательно без Москвы” is a preference, not a hard filter unless the user says so.
- Present the best viable non-Moscow option first, then a Moscow backup if materially cleaner.
- Do not call separate outbound/return provider offers a protected round trip. Say “ориентир за пару one-way предложений” unless booking-screen/GDS/airline fare proves one protected round-trip order.

### API vs website mismatch

When the user reports a flight on the KupiBilet website that the CLI didn't find, or the CLI shows a different departure time than the website:

1. First run the narrow KupiBilet diagnostic command for the same route/date/filter. If a raw adapter-level reproduction is still needed, call `api-rs-lb.kupibilet.ru/frontend_search` with the same route/date/filter and the CLI headers from `config.py::KUPIBILET_HEADERS`.
2. Inspect the raw `flights` map: look for the flight by `number` field. The API uses `number` / `transport_number`; the CLI synthesizes the carrier-prefixed display identifier.
3. Check `departure_datetime` in the raw response. If the API itself differs from website evidence, report provider-side data drift or coverage gap instead of blaming the parser.
4. For itinerary planning, use the user's website-observed times if more reliable, but label the discrepancy.

### Connection feasibility at major hubs

When evaluating assembled connections, check terminal fields in the normalized offer segments. The CLI preserves `departure_terminal` and `arrival_terminal` from raw provider data when available. At airports where inter-terminal transfers are significant, a nominally adequate connection can still be impractical if terminals differ. Do not present a connection as feasible without checking terminals when the user has raised terminal concerns or the hub is known for inter-terminal friction.

## Diagnostic splits

### Horizon vs coverage

If a date has no useful result, test whether the date is outside the provider’s searchable horizon before calling it a route gap. A nearby in-horizon control date can prove whether the route shape is discoverable.

### Coverage vs source boundary

`not_executed`/`failed` controls are missing or degraded evidence. `not_supported` is a terminal provider/source capability boundary. Do not mark evidence incomplete solely because a provider cannot support a probe type, but do mention it if it changes the decision.

### Ranking vs physical possibility

The production `business` ranking can demote late-night, cross-airport, low-confidence, baggage-risk, or long-wait options. When the user asks whether something is possible, distinguish physical possibility from operational recommendation and name the ranking field that caused demotion.

### Overnight / long-wait avoidance

If the recommended option has an overnight or very long wait, test whether same-day options were filtered by connection windows, airport continuity, provider failures, or ranking. Do not say the overnight is physically required unless targeted evidence supports it.

### Ticketing proof vs shopping evidence

A route option from the DecisionFrontier is shopping evidence. Single PNR, baggage-through, fare rules, refund/exchange, disruption protection, terminal certainty, and final fare require purchase-screen/airline/GDS/seller proof; see `source-boundaries.md`.

## Internal fields for diagnosis

Use these fields to diagnose, not to overrule the canonical rendered answer:

- `agent_guidance`: readiness, blocking evidence, next-action request patches;
- `coverage_diagnostics`: planned/searched/skipped/failed/not-supported/not-executed controls;
- `segment_searches`: per-segment provider evidence and failures;
- `hub_viability`: connection feasibility by hub;
- `rejected_pair_warnings`: airport mismatch and connection filters;
- `stop_policy` / `stop_policy_diagnostics`: preferred vs secondary tier behavior;
- `omitted_counts`: truncation after budgeting;
- `direct_route_intelligence`: route-index availability and skip reasons.

If preferred options are missing while segment evidence exists, inspect generation diagnostics. Do not compensate by blindly increasing `candidate_pool_limit` in normal flow; reproduce the specific generation/report contract issue.

## Reference lifecycle

Route-specific debug notes should not become new active references. After a case is understood, distill the durable rule into this playbook, `report-contract.md`, `source-boundaries.md`, `pipeline-reference.md`, `cli-maintenance.md`, or tests; leave raw incident history to session search.
