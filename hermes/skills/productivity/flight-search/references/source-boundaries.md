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
- Runtime/provider failure: provider, sidecar, network, parser, JSON, or dependency errors reduced evidence quality.
- Structural unavailability: regular service is unavailable in normal booking channels.
- Ticketing/protection uncertainty: segments may exist, but single PNR, through-fare, baggage-through, recheck, or disruption protection is unproven.

When a market is structurally constrained, do not phrase the answer as “the provider did not prove absence.” State the practical booking-channel conclusion, then show viable connecting options and purchase checks.

## Airport and City Boundaries

Use airport codes, not city labels, when continuity matters. These airports are not interchangeable:

- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For separate tickets, same-airport continuity is required by default. Cross-airport options must be rejected or explicitly labeled as ground-transfer risk.

City-scope defaults:

- Dubai: `DXB` primary; `DWC` secondary when relevant; include `SHJ` only when the user asks for Sharjah, a Sharjah-based carrier, cheapest UAE-wide options, or a provider returns it and it is labeled.
- Moscow: `SVO`, `DME`, and `VKO` are not interchangeable. Keep continuity explicit and label any ground transfer.
- London: prefer `LHR` for business travel when practical. `LGW`, `STN`, and `LTN` can be fallbacks, but label airport-quality and transfer trade-offs.

Provider-specific airport priority and dispatch semantics live in `references/provider-aware-airport-priority.md`.

## Connection Thresholds

Use exact Minimum Connection Time evidence before generic buffers when the connection is decision-critical. Practical lookup order:

1. airline/GDS/IATA MCT data when available;
2. airport-specific public MCT references such as `https://minimumconnectiontime.com/airport/IATA`;
3. the conservative generic thresholds below when exact data is unavailable or uncertain.

MCT is a technical/legal floor for a sellable connection and baggage transfer, not the recommended business buffer. A connection can be legal but still unattractive because of terminal size, passport/security, baggage, low-cost/remote gates, delays, or seller-side virtual/self-transfer construction.

Generic fallback thresholds:

- Same airport, protected/single-ticket international connection: MCT or at least 60 min, whichever is higher; label 60-89 min as tight unless airport evidence supports it.
- Same airport, separate/virtual/self-transfer without baggage: 120 min minimum acceptable.
- Same airport, separate/virtual/self-transfer with checked baggage: 180 min minimum acceptable; prefer 3-5h for high-friction airports.
- Cross-airport or airport mismatch: 300 min default and label as ground-transfer risk.
- Same-airport 90-119 min: label tight when ticketing/protection is not proven.
- Ordinary overnight waits can be acceptable only if they support a deliberate airport-hotel pattern; label hotel/visa/landside-baggage implications.
- Very long waits (~18h+) are forced stopover/fallback choices unless the user explicitly wants a stopover or every shorter option has materially worse ticketing/safety risk.

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons. Keep comfort trade-offs separate from real risk: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Ticketing Evidence Hierarchy

A combined itinerary in the report does not automatically prove a single ticket or single PNR. Use `through_fare_checks` for the current evidence level.

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

Distinguish:

- one KupiBilet order/checkout;
- airline-responsible single PNR / through-fare;
- baggage-through;
- missed-connection responsibility;
- refund/exchange rules per ticket or per order.

Smart routes can be cheaper but may require new check-in, baggage reclaim/recheck, passport/visa formalities, and independent fare rules. Present smart routes as risk-bearing, not as protected connections, unless purchase-screen terms prove the protection.

Decision-critical public terms from the last researched help-page snapshot:

- Trip Guarantee: can cover cancellation, 5h+ delay for a ticket with one booking reference, and broken smart-route connection due to delay; passenger must contact KupiBilet quickly and no later than 2h after original departure time.
- KupiBilet refund add-on: may return 90% when cancelled at least 48h before departure; exact terms/eligible payout form require checkout/help-page verification.
- Baggage after purchase, online check-in, priority support, meals, refunds, exchanges, and bonuses are add-ons/terms to verify on current checkout before quoting as firm.

For business travel, use KupiBilet to discover candidates and price signals, then verify booking-screen/GDS/airline evidence for PNR, baggage, protection, terminals, and fare rules.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, country/region scope, airline labels, alliance labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

## Live Provider Policy and Sidecar Boundary

The live provider policy chooses the current source mix for each segment. Read policy, failures, coverage diagnostics, and source limits from `data.agent_report` instead of assuming a provider path.

The sidecar is a discovery boundary. It can expand live discovery when available, but the core CLI must still report provider failures and source limits clearly when the sidecar is unavailable or degraded.
