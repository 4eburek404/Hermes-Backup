---
name: flight-search-routing
description: "Business-travel flight search with live CLI routing: prioritize preferred airports (IST≠SAW, DXB≠DWC, LHR≠LTN), safe connections, and grounded live artifacts before cached price APIs."
version: 2.4.3
author: hermes
license: MIT
metadata:
  hermes:
    tags: [Flights, Travel, Aviasales, Travelpayouts]
    prerequisites: [flights CLI, fli CLI, travelpayouts_flight_search tool]
---

# Flight Search with Multi-Segment Routing

## Overview

Use this skill for flight searches where business convenience, airport quality, connection safety, live grounding, or multi-segment assembly matter. Default profile for Konstantin-style flight work is **business travel routing**, not cheapest-ticket hunting: rank operational viability, preferred airports, safe buffers, practical ticketing, and schedule quality before raw price unless the user explicitly asks for cheapest/any-airport/low-cost routing.

For any non-trivial business flight search, load the normative reference first:

```text
references/business-flight-routing.schema.json
```

That file is a **skill reference JSON Schema contract** for agent behavior. It is not a provider/model structured-output mode and must not be used as a reason to rely on constrained decoding.

## When to Use

- The user asks for flights where convenience, timing, reliable airports, or connection quality matter.
- The route may require a connection, same-airport assembly, or separate tickets.
- The source may return city-level results that hide wrong-airport or low-quality options.
- The user asks for business-trip recommendations, not just a quick cache-only price check.
- The answer could affect money, non-refundable purchases, missed connections, visa/border exposure, or baggage/self-transfer risk.

## Dispatcher Protocol

1. **Load the contract.** For non-trivial searches, read `references/business-flight-routing.schema.json` before ranking or recommending. Use it as the generic policy source for `preferred_airports`, `airport_compatibility`, `source_policy`, `ranking_policy`, `answer_contract`, and validation gates.
2. **Use live-first evidence.** Prefer `flights` CLI/live aggregate, airline calendars, `fli` for suitable non-Russian segments, browser/source pages, and saved artifacts. Demote Travelpayouts/Aviasales-style cached APIs to the **last sanity/price-link layer**; never use cached absence/`0 results` as negative evidence that a route, direct flight, or round-trip does not exist.
3. **Preserve artifacts.** For multi-step/high-stakes recommendations, save or identify reproducible artifacts under a deterministic folder such as `~/flight_search_artifacts/<route>_<dates>_<source>/` and mention source type in the final answer.
4. **Validate airports before price.** Compare actual segment airports, not only city labels. Reject or explicitly demote incompatible airport changes unless the user accepted the transfer and the risk is named.
5. **Assemble enough depth.** Do not let a price-sorted source truncate away the safest, fastest, preferred-airport, carrier-relevant, or schedule-best option. Keep frontier representatives when they materially change the decision.
6. **Audit segment frontier before final ranking.** For exact-airport or carrier-sensitive questions, inspect `data.segment_results` in addition to `data.ranked`, preserve actual-airport carrier representatives (for example actual-`IST` TK/BA flights to LHR), and manually assemble any viable options that source ordering hid below the first page.
7. **Promote verified nonstops even outside assembled rank.** `route kb-assemble` is strongest for one-stop/separate-ticket assemblies; a direct flight can appear in live aggregate or carrier-filtered search but be absent from `data.ranked`. For exact-airport business routes, inspect aggregate/direct/carrier-filtered results before finalizing. If a nonstop exact-airport option dominates on connection risk and total trip quality, recommend it first and explicitly attribute it to live aggregate/carrier-filtered evidence rather than pretending it was `data.ranked[0]`.
8. **Rank by business value.** Operational viability → same-airport compatibility → connection safety → elapsed time → preferred-airport quality → schedule quality → practical ticketing → carrier/source reliability → visa/baggage exposure → price. The main recommendation must be the best-balanced business option, not merely the earliest or cheapest acceptable option. Same-airport separate-ticket thresholds: **90 min minimum acceptable**, **120 min business-preferred**; label 90–119 min as tight, while ≥120 min clears the preferred buffer and should then be ranked by the broader business balance.
9. **Answer in the contract order.** Brief status first; verified sources next; main recommendation before price discussion; then alternatives/rejections and purchase recheck caveats.
10. **When corrected, switch to the correct procedure.** If the user challenges a miss, formulate the reusable correct workflow and the skill guardrail first; keep error narrative secondary and concise.

## Critical Airport Compatibility Rules

Inline catastrophic checks to keep visible even before loading detailed references:

- **IST ≠ SAW** — separate Istanbul airports; do not silently substitute secondary-airport options for business routing.
- **DXB ≠ DWC ≠ SHJ** — Dubai/nearby airport systems are not interchangeable.
- **SVO ≠ DME ≠ VKO** — Moscow airports require same-airport continuity or explicit ground-transfer handling.
- **LHR ≠ LGW ≠ STN ≠ LTN** — London airport quality matters; for business trips, rank preferred airports before raw price unless the user overrides.

General rule: every user-facing itinerary must verify actual departure/arrival airport per segment. If `arrival_airport != next_departure_airport`, reject by default for separate-ticket business routing or label cross-airport transfer risk explicitly.

## Cached API Boundary

- Travelpayouts/Aviasales-style cached data is approximate and incomplete.
- Put Travelpayouts/Aviasales-style cached lookups **after** live/direct/carrier/airline checks, not before them, unless the user explicitly asks for cache-only reconnaissance.
- Cached absence or `0 results` is **not negative evidence**: it cannot support “no flights”, “no direct flight”, “no round-trip”, or “not available” claims.
- Cached price is not a final purchase price.
- Cached API output must not be the sole basis for a business recommendation, airport-substitution acceptance, or “no viable options” conclusion.
- If the user explicitly asks for a quick cache-only lookup, label it as cache-only reconnaissance and include the recheck-before-purchase caveat.

## Source and Reference Loading

Default reference for non-trivial searches:

- `references/business-flight-routing.schema.json` — generic route-independent policy contract.

Load linked topical references only when the request needs them:

- direct-offer promotion when `route kb-assemble` omits a nonstop that appears in live aggregate/carrier-filtered search (`references/direct-offer-promotion-2026-05-05.md`);
- layover rules / airport-system minute defaults;
- CLI command/source selection details;
- LHR-first frontier example for `SVX→LHR 2026-08-16` when calibrating London/TK/BA same-day vs overnight trade-offs (`references/svx-lhr-frontier-2026-08-16.md`);
- site compatibility and browser workflows;
- airline-specific or aggregator-specific quirks;
- London airport ranking when the destination is London or the user questions airport priority;
- one-way assembly/ranking workflow when round-trip search is empty or sparse;
- `references/aeroflot-live-kupibilet-frontend-search.md`;
- flights CLI refactor/cache-contract review notes when auditing or troubleshooting `route plan`, `route kb-assemble`, catalog refresh, or offline-first test failures (`references/flights-cli-refactor-cache-contract-2026-05-06.md`).]

For exact CLI syntax, call `flights <cmd> --help` or `fli --help`; do not copy stale help text into this skill.

## Minimal Verifier Gate

Before recommending or shortlisting a materially important itinerary, verify and state:

- actual origin/destination airport for every segment;
- connection minutes and whether same-airport/cross-airport rules pass;
- local dates, local times, timezone/overnight shifts;
- marketing/operating carrier when available;
- source type and artifact/source path when workflow is multi-step;
- price/availability caveat and recheck-before-purchase caveat;
- visa, border, baggage reclaim, and self-transfer exposure when applicable.

Use a two-round researcher → verifier/critic/fact-checker only for high-stakes or conflicting cases. Round 2 must receive the researcher summary, artifact paths, and facts-to-verify list; a blind critic is not enough.

## Common Pitfalls

1. **Answering from cache alone or treating cache absence as evidence.** Cache can miss carriers, schedules, fare classes, direct flights, round trips, and airport substitutions. Use live/direct/carrier/airline sources first; Travelpayouts/Aviasales-style cache is a late sanity/price-link layer and `0 results` is never proof of absence.
2. **Treating city code as airport equality.** Always compare airport codes between adjacent segments.
3. **Ranking price before airport viability.** A cheaper wrong-airport, unsafe-buffer, or overnight self-transfer option can be worse for business travel.
4. **Truncating before frontier extraction.** Keep representatives for safest, fastest, preferred-airport, carrier-relevant, schedule-best, and materially cheaper acceptable options when they change the recommendation.
5. **Explaining a miss as an error narrative instead of a corrected procedure.** When the user challenges a route omission, answer with the reusable correct workflow first: what to inspect, what to preserve, what to rank, and what skill guardrail changed. Keep apologies/root-cause narrative short unless explicitly requested.
6. **Reporting rejected options as clutter.** Show rejected/tight options only when they prevent a plausible bad purchase or explain an important trade-off.
7. **Skipping practical ticketing economics.** For foreign hub segments, same-carrier round trips can be cheaper and cleaner than stitched one-ways.
8. **Promoting regression examples into generic facts.** Route-specific golden examples calibrate tone/order only; generic behavior comes from the schema contract and current live evidence.
9. **Confusing the schema with model enforcement.** The JSON Schema reference governs the skill workflow; it is not a guarantee that the active model/provider will produce valid structured output.

## Verification Checklist

- [ ] `references/business-flight-routing.schema.json` was loaded for a non-trivial business search.
- [ ] Live/source artifacts or explicit cache-only caveat ground all schedule, airport, carrier, price, and availability claims.
- [ ] Actual airport codes pass compatibility checks or the transfer risk is named.
- [ ] Connection buffers meet current defaults or a source/user override is stated.
- [ ] Ranking follows business value before price unless the user requested price-first.
- [ ] Frontier-relevant alternatives were preserved before presenting a shortlist.
- [ ] Final answer starts with brief status, then verified facts/sources, then main recommendation.
- [ ] Cached/API prices are marked approximate, cached absence was not used as negative evidence, and final fare/availability requires recheck before purchase.
- [ ] Route-specific references are not used as generic source of truth.
