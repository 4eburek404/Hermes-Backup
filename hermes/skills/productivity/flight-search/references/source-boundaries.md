# Source Boundaries and Ticketing Evidence

Use this reference to classify what the live report can prove. Source boundaries are reasoning inputs; print only the caveats that change the traveler's decision.

## Evidence Classes

- Live provider report: current shopping/discovery evidence for the requested route/date, subject to provider coverage, runtime failures, cache state, and booking-screen changes.
- Targeted live control: a narrow probe for a direct flight, exact airport, city code, carrier, alternate airport, round-trip checkout, or in-horizon control date.
- Static catalog metadata: city, airport, country/region, airline, alliance, and aircraft labels used for normalization and scope only.
- Structural route constraint: stable route-level or market-level facts that make a service practically unavailable in normal booking channels.
- Purchase proof: booking-screen, airline, GDS, or seller evidence for final fare, seat, baggage, single PNR, missed-connection protection, refund, exchange, and fare rules.

Empty provider output is not proof of absence by itself. Use it to choose probes and confidence language; do not turn it into a generic caveat when a stronger route-level conclusion is available.

## Absence Taxonomy

- Provider/horizon uncertainty: date is too far out, too near, or outside a searchable window.
- Provider coverage gap: the source can search the date but has weak coverage for the route, airport, carrier, or market.
- Constraint mismatch: direct-only, carrier-only, cabin, timing, baggage, airport, or stop-policy filters removed otherwise viable options.
- Runtime/provider failure: provider, network, parser, JSON, or dependency errors reduced evidence quality.
- Structural unavailability: regular service is unavailable in normal booking channels.
- Ticketing/protection uncertainty: segments may exist, but single PNR, through-fare, baggage-through, recheck, or disruption protection is unproven.

When a market is structurally constrained, do not phrase the answer as “the provider did not prove absence.” State the practical booking-channel conclusion, then show viable connecting options and purchase checks.

## Airport and City Boundaries

Use airport codes, not city labels, when continuity matters. Airports within the same city are not interchangeable for itinerary continuity; dispatch policy and priority tiers live in `references/pipeline-reference.md`.

Same-airport continuity is required for every adjacent itinerary segment.
Reject cross-airport candidates; a longer layover or risk label cannot make an
airport mismatch valid.

City-scope boundary:

- Exact airport requests stay exact unless the user allows city scope.
- City-code requests must still display the actual airport codes returned by normalized offers.
- City scope may expand search endpoints, but it must not bridge adjacent
  segments through different airports.

Provider-specific airport priority, city-code expansion, and dispatch semantics live in `references/pipeline-reference.md`; keep this file focused on confidence and caveat wording.

## Connection Thresholds

Use exact Minimum Connection Time evidence before generic buffers when the connection is decision-critical. Practical lookup order:

1. airline/GDS/IATA MCT data when available;
2. airport-specific public MCT references such as `https://minimumconnectiontime.com/airport/IATA`;
3. the conservative generic thresholds below when exact data is unavailable or uncertain.

These thresholds are fallback feasibility inputs, not a mapping from layover
duration to `risk.grade`. Never assign `high` risk from one universal threshold
such as four hours.

MCT is a technical/legal floor for a sellable connection and baggage transfer, not the recommended business buffer. A connection can be legal but still unattractive because of terminal size, passport/security, baggage, low-cost/remote gates, delays, or seller-side virtual/self-transfer construction.

Generic connection time thresholds:

- Same airport, protected/single-ticket international connection: MCT or at least 60 min, whichever is higher; label 60-89 min as tight unless airport evidence supports it.
- Same airport, separate/virtual/self-transfer without baggage: 120 min minimum acceptable.
- Same airport, separate/virtual/self-transfer with checked baggage: 180 min minimum acceptable; prefer 3-5h for high-friction airports.
- Cross-airport or airport mismatch: invalid; reject before ranking regardless
  of layover duration.
- Same-airport 90-119 min: label tight when ticketing/protection is not proven.
- Overnight waits remain eligible when timestamps and airport continuity are
  valid; expose hotel, visa, landside, and baggage implications when relevant.
- Very long waits remain visible and may be demoted by the active business stop
  policy, but duration alone is not a hard rejection reason.

## Feasibility, Comfort, and Risk

- Separate tickets, self-transfer, or an unproven single PNR require a clear
  warning, but do not automatically make an otherwise feasible connection
  `high risk`.
- `risk.grade=unknown` means that available evidence does not support a numeric
  grade; it does not mean `high`.
- `long_wait` and `overnight_wait` are comfort and visibility labels, not
  automatic rejection reasons.
- Keep feasibility, comfort, and ticket protection separate. Use timestamps,
  terminals, baggage and visa friction, ticketing evidence, and exact MCT when
  available; do not infer risk from layover duration alone.

## Ticketing Evidence Hierarchy

A combined itinerary in the report does not automatically prove a single ticket
or single PNR. Use explicit booking-screen, fare-rule, seller, airline, or GDS
evidence for that claim.

Hierarchy:

1. Booking screen / airline-GDS fare / fare rules showing one protected purchase.
2. Explicit provider raw ticketing fields proving single-PNR/through-fare behavior.
3. Provider aggregate offer with one checkout price and one offer/variant id, but no protection proof yet.
4. Provider aggregate with virtual/smart-route signal: seller-side construction; protection depends on stated terms.
5. Two separate one-way offers or CLI-summed segments.

Before presenting a ticketing claim as firm, verify it on the purchase screen or state exactly which tier the report supports. Baggage, recheck, refund, and disruption protection depend on ticketing proof, not only segment timing.

Carrier-specific round trips need extra care:

- Direct one-way offers in both directions do **not** prove a round-trip ticket exists on that carrier.
- If the user asks for one ticket / single PNR, require booking-screen-level proof before saying “да”.
- If only one-way offers are visible, answer that the carrier has separate options and the protected round trip is unproven.

Useful wording:

- `U6 есть на обе стороны, но one-ticket round-trip не подтверждён.`
- `single PNR/багаж не доказаны — проверить на booking screen.`

## KupiBilet Operational Semantics

KupiBilet is useful as OTA discovery, price/checkout evidence, and smart-route discovery. It is not final airline/GDS proof by itself.

### API vs website mismatch

KupiBilet API evidence and KupiBilet website evidence can diverge on schedule times or whole offers. Treat this as a provider/source-boundary issue until proven otherwise, not as an immediate parser bug.

When the user reports a website-visible flight that the CLI did not find or time-shifted:
1. Reproduce with the narrow KupiBilet diagnostic or raw API check from `references/debug-playbook.md`.
2. If the API returns the same value the CLI normalized, report provider-side data drift or provider coverage gap.
3. If website evidence is more current for planning, use it as user-observed evidence and label the discrepancy.

For non-RU or foreign-carrier routes, KupiBilet API gaps are a known source limitation. Empty KupiBilet output alone does not prove absence; prefer the assembled `search result`, Tutu-first provider evidence, and targeted provider comparisons before making a negative route claim.

### Live provider alternatives

Provider dispatch and fallback ownership live in
`references/pipeline-reference.md`. This file only classifies the evidentiary
limits of the resulting provider offers.

### Terminal data availability

The raw KupiBilet API can return `arrival_terminal` and `departure_terminal` per flight. The CLI normalizes these into `segments[].departure_terminal` / `segments[].arrival_terminal`. When evaluating connection feasibility at major hubs, check terminal fields and do not assume same-terminal transfers.

Distinguish:

- one KupiBilet order/checkout;
- airline-responsible single PNR / through-fare;
- baggage-through;
- missed-connection responsibility;
- refund/exchange rules per ticket or per order.

Smart routes can be cheaper but may require new check-in, baggage reclaim/recheck, passport/visa formalities, and independent fare rules. State those specific caveats without automatically assigning `high risk`, and never present the route as protected unless purchase-screen terms prove the protection.

Decision-critical public help-page facts must be treated as current-source evidence, not durable guarantees. The currently verified smart-route help page says smart routes are split tickets in one KupiBilet order; if a flight is cancelled or delayed due to the airline and the passenger contacts KupiBilet instead of self-buying/exchanging elsewhere, KupiBilet may cover the missed part of the route. It also says passengers may need to re-check in, reclaim/recheck baggage, hold transit documents/visas, and accept separate refund/exchange conditions per ticket.

Do not quote exact delay thresholds, refund percentages, deadlines, add-on terms, or payout rules from memory. Verify current checkout/help-page wording before presenting those as firm.

For business travel, use KupiBilet to discover candidates and price signals, then verify booking-screen/GDS/airline evidence for PNR, baggage, protection, terminals, and fare rules.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, country/region scope, airline labels, alliance labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

Catalog-dependent CLI commands refresh missing or older-than-2-weeks static metadata before planning unless disabled. This is runtime readiness, not live availability evidence.

## Live Provider Policy

The live provider policy chooses the current source mix for each segment. Read policy, failures, coverage diagnostics, and source limits from `data` instead of assuming a provider path.

## Adjacent Source Boundaries

### Route network without a date

When the user asks where an airport flies direct, or whether a route exists without a travel date, this is a route-network question, not live-ticket search. The flight-search CLI searches live inventory for a specific route/date and cannot prove a full airport route map.

Source order for route-network answers:

1. official airport website or airline route map, preferably pages that distinguish direct vs connecting service;
2. Wikipedia "Airlines and destinations" as structured but possibly stale support;
3. Google Flights Explore or departure boards only as fallback.

Official airport/airline sources win over Wikipedia when they disagree. Cite source and verification date, and keep undated route existence separate from dated live availability.

### Train-vs-flight comparison

Use rail evidence only as a bounded adjacent comparison after a flight search, when the user asks whether train tickets are cheaper or wants rail prices on the same route/date. For Russian rail availability and prices, use official RZD/pass.rzd data as the source of truth. Do not replace official-source failure with aggregator estimates unless the user explicitly asks for non-official advisory context.

RZD/pass.rzd output is read-only availability and tariff evidence, not purchase proof. Final fare, exact seat/car, fees, refund rules, meals/service details, and purchase eligibility require the official RZD booking screen.
