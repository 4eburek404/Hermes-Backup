# Flight Search Pipeline Reference

## Production flow

```text
raw JSON
  -> search_request_from_payload -> SearchRequest v3
  -> SearchPlanBuilder
  -> SearchPlan v5
  -> SearchExecutor.execute(plan) -> immutable SearchEvidence
  -> OfferGraph -> validation -> scoring -> frontier
  -> SearchDecision
  -> result projection v9
  -> flight_search_user_answer.v11
  -> pure renderer
  -> stdout
```

`SearchWorkflow` is the only production composition root. Defaults and
normalization are applied once at the request boundary. After `SearchPlan v5`
is built, execution reads only the plan. Planning is pure with respect to
providers. Gateway priors may schedule probes; gateways observed live are
evidence and never mutate the active plan.

Provider I/O belongs to execution. Direct-only primary probes run first for
each direction. Broad primary and gateway probes are eligible only for
directions with no direct result. At most one bounded broad phase may run.
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
attempt. Primary fanout executes all compatible providers; gateway fanout tries
providers in plan order, continuing after failure, unsupported, or empty, and
stopping after the first positive result. Every result enters one OfferGraph
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
restrictive carrier filters, broad and gateway alternatives for that direction
are skipped. Missing/malformed times, impossible chronology, wrong endpoints,
or an out-of-scope carrier cannot suppress fallback.
`max_connections` is only a fallback ceiling and never disables this gate.
Round-trip outbound and return directions are gated independently.

The same rule applies inside gateway assembly per leg and date: execute the
direct leg probe first, skip its broad variant when direct inventory exists,
and permit intermediate hubs only after a direct-empty result. A provider
failure is not proof that no direct flight exists; diagnostics record whether
direct absence was confirmed by at least one completed source.

After direct evidence is collected, the executor partitions planned
`conditional_gateway_queries` by direction. Queries for a direction with
direct evidence are recorded in `probe_ledger.skipped_probes` with
`reason="direct_available"`; only directions without direct evidence enter the
gateway batch executor. This executor partition is the production policy. The
unused `assess_fallback()` helper is not a second policy source.

## Gateway discovery and assembly

The active plan stores one of three gateway triggers; it is not a second
runtime policy:

- `disabled` plans no gateway attempts.
- `required_if_no_direct` applies to configured restricted-access RU markets. Gateway
  fallback is mandatory when no direct flight exists, but direct evidence still
  suppresses gateway probes for that direction.
- `on_primary_failure` applies to normal RU-touching and global
  markets. Conditional gateway probes run only when primary evidence is
  unavailable, unsupported, failed, or unusable.

`direct_only=true` is an absolute planning constraint: it creates neither broad
nor gateway attempts.

Gateway candidates come from configured priors and live provider signals; no
route-specific hub belongs in agent logic. Continuation is not limited to a
direct second leg: the planner searches the requested day and next day and may
accept provider-returned intermediate hubs such as
`GATEWAY -> HUB -> DESTINATION`. Valid overnight candidates remain eligible.

The gateway executor owns continuation through `gateway_discovery_limit`,
`gateway_probe_batch_size`, and `gateway_probe_max_batches`. It evaluates each
completed batch and stops when a viable gateway is found or the batch budget is
exhausted. Strict direct-only planning creates zero gateway probes; stop limits
otherwise constrain reportable candidates and do not create a parallel gateway
policy.

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
