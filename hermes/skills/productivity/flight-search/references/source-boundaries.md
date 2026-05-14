# Source Boundaries

Use this before explaining why sources disagree, why a route is uncertain, or why purchase-screen verification is needed.

## Provider Boundaries

- Kupibilet live aggregate is live shopping data, not the airline or a GDS.
- Segment assembly prices compatible direct legs and assumes separate/self-transfer unless protection is proven.
- FLI MCP is useful for non-Russian/global segments; it is a self-hosted wrapper, not an official Google Flights public API.
- FLI/Google-style checks are weak or empty for Russia-origin legs; prefer Kupibilet or airline-public sources for RU-touching searches.
- Travelpayouts/Aviasales cached price data is a legacy late sanity layer only.

Cached absence or `0 results` is never proof that a route, direct flight, round trip, carrier route, or through fare does not exist. One-way probes can reveal options that round-trip queries miss; treat round-trip emptiness as a source/query limitation.

## Airport Boundaries

Use airport codes, not city labels, when continuity matters.

- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For separate tickets, same-airport continuity is required by default. Cross-airport options must be rejected or explicitly labeled as ground-transfer risk.

Connection thresholds for business routing:

- same airport, separate tickets: 90 min minimum acceptable;
- same airport, separate tickets: 120 min business-preferred;
- same-airport 90-119 min: label tight;
- cross-airport or airport mismatch: 300 min default;
- same airport, protected ticket: 60 min can be acceptable only when protection is proven.

## City Scope Rules

London: prefer `LHR` for business when practical. `LGW`, `STN`, and `LTN` can be acceptable fallbacks, but label the trade-off. Use exact airports for same-day transfers.

Dubai: default scope is `DXB` first and `DWC` second when operationally relevant. Do not include `SHJ` by default. Include Sharjah only when the user asks for Sharjah, Air Arabia/G9, cheapest UAE-wide options, or a provider returns SHJ and it must be labeled explicitly as Sharjah.

Moscow: when using Moscow as a gateway, keep airport continuity explicit. `SVO`, `DME`, and `VKO` are not interchangeable without a labeled ground transfer.

## Through-Fare Boundary

The CLI can assemble `SVX -> SVO + SVO -> DEL`, but it does not construct Aeroflot/GDS fare rules or guarantee one PNR. A same-carrier route can be cheaper as a through fare, more expensive as a through fare, protected with baggage through-check, or unavailable as a protected ticket even when segments exist separately.

When `through_fare_checks` is present, tell the user what to verify:

- airline website;
- GDS/Sirena/Amadeus-capable seller;
- booking-screen fare rules;
- baggage and ticket protection;
- refund/change conditions.

For Aeroflot, filter by marketing or operating carrier `SU`. SU-marketed Rossiya/FV-operated flights can be valid Aeroflot-sold options. Do not reintroduce legacy cached `su-flights` behavior.

## Cache And Rate Boundaries

Expanded coverage controls can multiply live calls: direct-only probes, city-code probes, alternate airports, carrier controls, outbound/return segment assembly, and full-route aggregate checks. Prefer a small frontier of high-value controls over exhaustive cartesian expansion.

When adding live probes, require provider-aware TTL keys, in-run request de-duplication, bounded per-provider concurrency, backoff on 429/timeouts, and visible live/cache/stale labels. Cached positive fare data is a useful hint, not final purchase availability; cached absence remains non-evidence.

## Price Boundary

Every price is advisory until the booking screen confirms final fare, availability, baggage, protection/single PNR, and fare rules.
