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

`auto` provider routing is per logical probe: Tutu runs first, then a capable
fallback only when needed. The dedupe key includes provider, route, direction,
date, filters, limits, direct mode, policy, and endpoint-specific inputs.

Direct-first is evaluated from primary evidence. A viable direct direction can
suppress its planned gateway probes; if no acceptable direct candidate remains,
one preplanned fallback wave may execute. Static catalogs, cached metadata, and
provider-empty results retain their bounded evidence meaning.
