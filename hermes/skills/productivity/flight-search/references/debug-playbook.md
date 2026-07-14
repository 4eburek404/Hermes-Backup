# Debug and Exception Probe Playbook

Use diagnostics only when the Golden Path report is inconsistent, degraded, or
too sparse for a decision-critical constraint. Diagnostics support
`search --request`; they do not replace its canonical answer.

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

## Diagnostic commands

Main report:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request request.json
```

Plan without provider execution:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose plan \
  --request request.json
```

Full live trace:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose trace \
  --request request.json
```

One provider probe:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose probe \
  --provider tutu \
  --request probe.json
```

Pure rendering check for an existing result:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json diagnose render \
  --input flight-search-result.json
```

Read `data.answer` for traveler-facing output. In a trace, use `data.plan`,
`data.evidence`, and `data.decision` only for diagnosis. Never expose raw probe
logs as a replacement traveler answer.

## Provider fanout and airport scope

With `provider_policy=auto`, Tutu and KupiBilet should have equivalent logical
queries for every eligible direct or broad route probe. Check:

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
- `data.plan.conditional_gateway_queries`.

If direct inventory exists for one direction, matching broad or gateway probes
for that direction should be terminal `skipped` with
`reason="direct_available"`. The other direction remains independent.

## Missing gateway chain

For an expected but absent gateway chain:

1. Confirm the gateway was present in `data.plan.gateway_discovery.candidates`.
2. Check candidate and batch bounds:
   `gateway_discovery_limit`, `gateway_probe_batch_size`, and
   `gateway_probe_max_batches`.
3. Check the probe ledger for planned, searched, skipped, failed, or unsupported
   terminal states.
4. Inspect `data.evidence.gateway_leg_results` for both legs and dates.
5. Inspect `data.decision.offer_graph` for airport continuity, chronology, and
   connection rejection.

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

For a round trip, verify outbound and return one-way candidates are ranked
independently before pair construction. The trace scorer metadata reports input
counts, pair-pool size, and retained pair count. Reordering equivalent provider
inputs must not change the selected best pair.

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
