# Flight Search Pipeline Reference

## Production flow

```text
raw JSON
  -> SearchRequest.from_payload
  -> SearchPlanBuilder
  -> SearchExecutor.execute(plan)
  -> immutable SearchEvidence
  -> OfferGraph + candidate envelope
  -> DecisionScorer + DecisionFrontier
  -> result projection
  -> flight_search_user_answer.v9
  -> pure renderer
  -> stdout
```

Defaults are applied once by `SearchRequest`. Planning is pure with respect to
providers. Gateway priors may schedule probes; gateways observed live are
evidence and do not mutate the plan.

Provider I/O belongs to execution. Direct-only primary probes run first for
each direction. Broad primary and gateway probes are eligible only for
directions with no direct result. At most one bounded fallback wave may run,
preplanned aggregate/evidence probes run once, then the ledger is finalized and
frozen. Ledger terminal states cannot reopen; cache status is separate.

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

Provider routing is per logical probe, not per whole search. `tutu` is the
default primary provider. In `auto`, a successful Tutu MCP broad probe stops
provider fallback for the same logical probe. Direct-only inventory is the
exception: Tutu and KupiBilet are both queried so one provider's bounded result
cannot hide direct flights exposed by the other.

- `kupibilet` is fallback only when Tutu is unavailable, fails, or does not
  support the probe and KupiBilet capability and market fit it.
- `fli` is fallback only for non-RU probes when Tutu is unavailable, fails, or
  does not support the probe.
- `provider_policy=both` is invalid.

The dedupe key includes provider, route, direction, date, filters, limits,
direct mode, policy, and endpoint-specific inputs. Tutu offers are shopping
evidence, may contain connected itineraries, and are paginated through the
adapter. Localized airline names are resolved through the airline catalog into
canonical carrier codes; route-specific carrier mappings are not allowed.

## Direct-first gate

Direct-first is strict and directional. If any direct-only provider result
contains a direct flight within the active date, airport, and restrictive
carrier filters, broad and gateway alternatives for that direction are skipped.
`max_connections` is only a fallback ceiling and never disables this gate.
`prefer_carriers` does not narrow direct detection. Round-trip outbound and
return directions are gated independently.

The same rule applies inside gateway assembly per leg and date: execute the
direct leg probe first, skip its broad variant when direct inventory exists,
and permit intermediate hubs only after a direct-empty result. A provider
failure is not proof that no direct flight exists; diagnostics record whether
direct absence was confirmed by at least one completed source.

After wave-0 direct evidence is collected, the executor partitions planned
`conditional_gateway_queries` by direction. Queries for a direction with
direct evidence are recorded in `probe_ledger.skipped_controls` with
`reason="direct_available"`; only directions without direct evidence enter the
gateway wave planner. This executor partition is the production policy. The
unused `assess_fallback()` helper is not a second policy source.

## Gateway discovery and assembly

`gateway_discovery_mode` is an internal route-access decision, not a request
field:

- `required` applies to configured restricted-access RU markets. Gateway
  fallback is mandatory when no direct flight exists, but direct evidence still
  suppresses gateway probes for that direction.
- `optional_after_provider_failure` applies to normal RU-touching and global
  markets. Conditional gateway probes run only when primary evidence is
  unavailable, unsupported, failed, or unusable.

Gateway candidates come from configured priors and live provider signals; no
route-specific hub belongs in agent logic. Continuation is not limited to a
direct second leg: the planner searches the requested day and next day and may
accept provider-returned intermediate hubs such as
`GATEWAY -> HUB -> DESTINATION`. Valid overnight candidates remain eligible.

The current production `SearchExecutor` instantiates `SearchWavePlannerOptions`
with `max_waves=1`. A larger `execution_limits.search_wave_max_waves` value in
the plan is therefore not proof that multiple waves executed; the authoritative
runtime evidence is `gateway_leg_results.wave_diagnostics`. Also, strict
`max_connections=0` plus `tier2_max_connections=0` constrains reportable
candidates but does not by itself prove that route-access gateway probes were
never planned or executed.

Candidate assembly requires airport continuity between every adjacent segment.
An airport mismatch is rejected before ranking; same-city airports and a longer
layover never make a cross-airport connection valid.

## Carrier filters and route shape

Carrier filters are provider-query inputs:

- `filters.only_carriers` narrows provider queries to the requested carriers
  where supported.
- `filters.prefer_carriers` is a provider preference and RU-priority seed, not
  a hidden scorer gate.
- Matching uses normalized carrier codes and raw provider names.

Do not reintroduce request `constraints`: route shape belongs in
`route_options`, carrier scope belongs in `filters`, and final selection belongs
in the decision frontier.
