# Flight Search Pipeline Reference

## Production flow

```text
raw JSON
  -> search_request_from_payload -> SearchRequest v4
  -> SearchPlanBuilder
  -> SearchPlan v6 (immutable route-leg templates)
  -> SearchExecutor.execute(plan) -> immutable SearchEvidence
  -> OfferGraph -> validation -> scoring -> frontier
  -> SearchDecision
  -> result projection v10 + research_status
  -> flight_search_user_answer.v11
  -> pure renderer
  -> stdout
```

`SearchWorkflow` is the only production composition root. Defaults and
normalization are applied once at the request boundary. After `SearchPlan v6`
is built, execution reads only the plan. Planning is pure with respect to
providers. Configured priors and explicit web hypotheses become immutable
route-leg templates; live gateway signals remain discovery evidence and never
mutate the active plan.

Provider I/O belongs to execution. Direct-only primary probes run first for
each direction. Broad primary probes are eligible only for directions with no
direct result. Concrete route-leg probes are created only by the executor from
immutable templates and their actual predecessor arrival time.
`ProbeRunLedger` owns planned probes, claims, physical-query dedupe, failures,
and terminal states. Before evidence is frozen, every planned probe must be
`searched`, `failed`, `not_supported`, `skipped`, `not_executed`, or
`deduped(original_probe_id)`. Terminal states cannot reopen; cache status is
separate.

Each `ProviderAttemptPlan` has canonical `provider`, `probe_type`, `direction`,
`trigger`, and a nested provider `query`. The plan contains no
`execution_state`: merely appearing in a phase means `planned`; every runtime
state belongs to the ledger.

After evidence freeze, graph construction, candidate normalization, scoring,
round-trip/two-one-way composition, and frontier selection run once. Provider
aggregate offers enter the same candidate envelope before scoring. Result
projection and rendering may not perform provider calls or option selection.
For round trips assembled from one-way offers and a positive
`max_round_trip_pairs`, every outbound/return pair is validated and scored
before the frontier applies the limit; it never truncates raw legs or
unvalidated pair order. At zero, synthesized pairs are not created.

Business frontier selection first keeps the best available stop tier: two-stop
options are eligible only when no direct or one-stop candidate exists. Normal
answers prefer layovers of at most six hours, prune candidates dominated within
the same gateway, keep one representative per carrier chain, and reserve room
for different first-leg carriers and up to two alternative gateways. Cheapest,
fastest, and safer labels annotate the selected frontier; they never force an
otherwise low-ranked candidate into an early position.

## Provider routing

Provider routing is fixed in `SearchPlan`, per logical probe rather than per
whole search. In `auto`, every compatible provider receives a planned primary
attempt. Route-leg dispatch tries providers in policy order, continuing after
failure, unsupported, or empty, and stopping after the first positive result.
Every result enters one OfferGraph
and is deduplicated before the shared output limit, so one provider cannot hide
a cheaper or otherwise distinct itinerary from another.

- `kupibilet` is a primary peer of Tutu for direct and broad full-route search.
- `provider_policy=both` is invalid.

Provider-query identity includes provider, probe type, route/date, currency,
direct mode, airport/carrier filters, and limit. Diagnostic role, trigger, and
other metadata do not participate in the physical-call key. Candidate dedupe
is provider-independent and uses the physical itinerary; equal-trust offers with
the same price basis and currency retain the lower price while preserving every
source provider. Tutu offers are shopping evidence, may contain connected
itineraries, and are paginated through the adapter. Localized airline names are
resolved through the airline catalog into canonical carrier codes;
route-specific carrier mappings are not allowed.

## Direct-first gate

Direct-first is strict and directional. If any direct-only provider result
contains a normalized valid direct flight within the active date, airport, and
restrictive carrier filters, broad main-route alternatives for that direction
are skipped. Missing/malformed times, impossible chronology, wrong endpoints,
or an out-of-scope carrier cannot suppress fallback.
`max_connections` is only a fallback ceiling and never disables this gate.
Round-trip outbound and return directions are gated independently.

The same rule applies inside a route template per leg and date: execute the
direct leg probe first, skip its broad variant when direct inventory exists,
and permit a configured-prior broad probe only after a direct-empty result. Web
hypotheses use `exact_direct`; an explicit hypothesis is not cancelled by an
unrelated main-route direct result. A provider failure is not proof that no
direct flight exists; diagnostics record whether direct absence was confirmed
by at least one completed source.

## Route hypotheses and assembly

The active plan stores one trigger per configured-prior template; it is not a
second runtime policy:

- `disabled` plans no configured-prior route templates.
- `required_if_no_direct` applies to configured restricted-access RU markets.
  Direct evidence suppresses configured-prior templates for that direction.
- `on_primary_failure` applies to normal RU-touching and global
  markets. Conditional configured-prior probes run only when primary evidence is
  unavailable, unsupported, failed, or unusable.

`direct_only=true` is an absolute planning constraint: it creates neither broad
nor configured-prior templates.

An explicit hypothesis is an ordered 3–5 airport chain supplied by web
discovery, never invented by the CLI. Round-trip templates mirror its airport
order and retain direction in the physical probe identity. The executor starts
leg 0 on the requested date; each next leg searches only local calendar dates
reachable from a real `arrival_at` through `max_layover_min`. It stops the
chain immediately on a failed, missing, or not-executed leg. Every concrete
provider call is ledger-owned and deduplicated by physical query, including
date. The graph materializer permits only legs from the same hypothesis in its
strict declared order.

Configured priors are also templates, with `direct_then_controlled_broad`
policy. A hypothesis above the resolved StopPolicy is audited as
`not_executed/hypothesis_exceeds_stop_policy`; it never raises the limit.
Assembly needs a live price for every separate-ticket leg. Ticket protection is
reported separately from connection feasibility.

Candidate assembly requires airport continuity between every adjacent segment.
An airport mismatch is rejected before ranking; same-city airports and a longer
layover never make a cross-airport connection valid.

## Carrier filters and route shape

Carrier filters are provider-query inputs:

- `filters.only_carriers` narrows provider queries to the requested carriers
  where supported.
- Matching uses normalized carrier codes and raw provider names.

Do not reintroduce request `constraints`: route shape belongs in
`route_options`, carrier scope belongs in `filters`, and final selection belongs
in the decision frontier.
