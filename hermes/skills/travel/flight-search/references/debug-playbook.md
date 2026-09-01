# Debug and Exception Probe Playbook

Use this playbook when the Golden Path report is inconsistent, degraded, or
too sparse for a decision-critical constraint. Everything below reads the
`search --request` answer and its evidence; there is no separate diagnostic
command surface.

## Runtime provenance

Resolve `cli/` relative to the active skill root and verify the imported code
before attributing behavior to a provider:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --version
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import flights_cli, pathlib
print(pathlib.Path(flights_cli.__file__).resolve())
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli search --help
```

Record the request route, dates, exact-airport versus city scope, carrier
filter, provider policy, direct-only setting, cache setting, source path,
branch, and commit. `maint doctor` proves local readiness, not live inventory.

## Reading one run

Main report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request request.json
```

Read `data.answer` for traveler-facing output. `data.evidence` and
`data.plan` in the same envelope carry the diagnosis. Never expose raw probe
logs as a replacement traveler answer.

## Provider fanout and airport scope

With `provider_policy=auto`, Tutu and KupiBilet should have equivalent logical
queries for every eligible direct or broad route probe. Check:

- `option_id` and `total_price.source` identify the provider that returned an
  offer, not every provider queried; use the plan and probe ledger for fanout;

- both providers appear in `data.evidence.primary_offer_results` and the probe
  ledger unless a capability or market boundary explains otherwise;
- `origin_airports` and `destination_airports` are normalized, preserved in
  both provider queries, and reversed for the return direction;
- every accepted path starts and ends inside the corresponding exact-airport
  scope;
- equal physical itineraries are deduplicated in the OfferGraph before shared
  ranking and output limiting.

A provider failure is not proof of route absence. A successful zero-offer
probe is bounded provider evidence, not structural unavailability.

## Direct-first gate

Direct-first is directional. Inspect together:

- `data.evidence.direct_mode`;
- `data.evidence.direct_presence_gate`;
- `data.evidence.probe_ledger.searched_probes`;
- `data.evidence.probe_ledger.skipped_probes`;
- `data.plan.phases.gateway`.

If direct inventory exists for one direction, matching broad or gateway probes
for that direction should be terminal `skipped` with
`reason="direct_available"`. The other direction remains independent.

## Missing gateway chain

For an expected but absent gateway chain:

1. Confirm the gateway was present in
   `data.plan.gateway_policy.discovery.candidates`.
2. Check candidate and batch bounds:
   `gateway_discovery_limit`, `gateway_probe_batch_size`, and
   `gateway_probe_max_batches`.
3. For round trips, confirm `data.plan.phases.gateway` contains both directions:
   outbound `ORIGIN -> GATEWAY -> DESTINATION` and return
   `DESTINATION -> GATEWAY -> ORIGIN`, using their respective dates.
4. Check the probe ledger for planned, searched, skipped, failed, or unsupported
   terminal states.
5. Inspect `data.evidence.gateway_leg_results` for both legs, dates, and
   directions.
6. Inspect `data.decision.offer_graph` for airport continuity, chronology,
   direction, and connection rejection.

Do not infer a partial route from the final airport of an incomplete offer.
Provider full-route offers and gateway legs are separate explicit inputs.

## Short or missing direct set

Confirm exact-airport versus city scope, date, direction, carrier filter, and
direct-only setting. Then compare provider result counts with OfferGraph edges,
frontier options, and `data.answer.catalog.items`. If a provider returned a
priced direct offer that disappeared later, the defect is in normalization,
dedupe, ranking, or projection—not provider availability.

Use a nearby in-horizon comparison date only to distinguish search horizon from
route coverage. Label it as a comparison, not as evidence for the requested
date.

## Round-trip ordering

For a round trip with `max_round_trip_pairs > 0`, verify every outbound/return
one-way combination enters the single validation and scoring pass before the
limit is applied. At `max_round_trip_pairs = 0`, synthesized pairs are not
created.
The frontier limits only valid, globally ranked synthesized pairs; provider
round-trip offers remain atomic and do not consume that limit. The trace scorer
metadata reports input counts, full pair-pool size, valid, eligible, and selected
pair counts. Reordering equivalent provider inputs must not change the ranked
or selected pair order.

## KupiBilet API versus website

If the KupiBilet website and CLI disagree, first run a narrow KupiBilet probe
with the same route, date, direct flag, carrier filter, and airport scope.
Inspect normalized first/last segment airports and the raw provider flight
number/timestamps. If the raw API itself differs from the website, report
provider-side data drift rather than blaming the parser.

## Connection and ticketing boundaries

Airport continuity is mandatory between adjacent segments. Same-city airports
are not interchangeable, and a longer layover does not repair an airport
mismatch. Check terminals when inter-terminal transfer matters.

Provider offers are shopping evidence. Single PNR, through baggage, fare rules,
refund/exchange terms, disruption protection, and final fare require explicit
booking-screen, airline, seller, or GDS proof. See `source-boundaries.md`.

## Reference lifecycle

Do not create route-specific incident documents under `references/`. Distill a
durable behavior into this playbook, the owning reference, code, or tests; keep
raw incident history in the task record.
