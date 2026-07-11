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

Provider I/O belongs to execution. Primary probes run first, fallback is
assessed from partial evidence without a graph, at most one bounded fallback
wave may run, preplanned aggregate/evidence probes run once, then the ledger is finalized
and frozen. Ledger terminal states cannot reopen; cache status is separate.

After evidence freeze, graph construction, candidate normalization, scoring,
round-trip/two-one-way composition, and frontier selection run once. Provider
aggregate offers enter the same candidate envelope before scoring. Result
projection and rendering may not perform provider calls or option selection.

## Provider routing

Provider routing is per logical probe, not per whole search. `tutu` is the
default primary provider. In `auto`, a successful Tutu MCP probe stops fallback
execution for the same logical probe.

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

Direct-first is evaluated from primary evidence. A viable direct direction can
suppress its planned gateway probes; if no acceptable direct candidate remains,
one preplanned fallback wave may execute. Static catalogs, cached metadata, and
provider-empty results retain their bounded evidence meaning.

## Gateway discovery and assembly

`gateway_discovery_mode` is an internal route-access decision, not a request
field:

- `required` applies to configured restricted-access RU markets. Gateway
  coverage is planned independently of provider failure, although viable direct
  evidence may still stop unnecessary gateway probes.
- `optional_after_provider_failure` applies to normal RU-touching and global
  markets. Conditional gateway probes run only when primary evidence is
  unavailable, unsupported, failed, or unusable.

Gateway candidates come from configured priors and live provider signals; no
route-specific hub belongs in agent logic. Continuation is not limited to a
direct second leg: the planner searches the requested day and next day and may
accept provider-returned intermediate hubs such as
`GATEWAY -> HUB -> DESTINATION`. Valid overnight candidates remain eligible.

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
