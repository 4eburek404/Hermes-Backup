# Business-trip London airport ranking

Use this when searching Russia/CIS ↔ London flights for Konstantin or another business-travel case where time, airport quality, and operational reliability matter more than the absolute cheapest fare.

## Lesson from 2026-05-04 SVX↔LON search

A search by city code `LON` can surface cheaper `LTN`, `STN`, or `LGW` options before Heathrow. That is acceptable for leisure/cheap profiles, but it is a bad default for командировки.

In that session the initial recommendation over-weighted:
- no-Schengen routing;
- one transfer;
- valid 120/300-minute connection buffers;
- lower cached/live price.

It under-weighted:
- London airport quality and ground logistics;
- carrier/airport fit for business travel;
- the user's expectation that Heathrow is the natural first check.

The user corrected this: do not appear to avoid Heathrow and then target `LTN`/`LGW` unless there is a clear reason.

## London application of the universal frontier rule

This is a route-specific application of the core skill's **multi-objective frontier** protocol, not a standalone London-only rule.

For London business trips, do not rank only by price once an LHR/no-Schengen baseline exists. Present at least three perspectives when the data supports them:

- **Balanced business LHR recommendation:** the first option should be the best practical balance of LHR, same-airport continuity, connection buffer, arrival time, carrier/ticketing quality, and price.
- **Earliest practical LHR arrival:** materially earlier LHR arrival, but only first if its connection buffer is not merely minimum-acceptable for the ticketing risk.
- **Safer-buffer / lower-risk LHR alternative:** longer same-airport hub connection when tickets are separate or baggage risk is unclear.
- **Cheapest acceptable LHR:** lowest practical LHR option that passes airport/connection checks, shown as a price trade-off rather than the default business recommendation.

Do not put a minimum-acceptable connection first just because it is earlier. Same-airport separate-ticket thresholds for this skill are: **90 min minimum acceptable**, **120 min business-preferred**. Label 90–119 min as “tight”; options at or above 120 min clear the business-preferred buffer, then rank by the broader balance of arrival time, carrier/ticketing quality, airport quality, and price.

Concrete London regression example from SVX→LHR via IST: a U6 early SVX→IST leg can enable TK same-day Heathrow arrivals around 15:10–16:40, while a cheaper SU+TK combination may arrive around 22:25. The earlier option must be shown as a trade-off, not suppressed by price sorting; conversely, the earliest/tightest acceptable connection must not displace the best-balanced business recommendation.

When using `flights route assemble`, keep sufficient segment depth (`--limit-per-pair 10` or higher) because any price-sorted segment source can place a frontier-relevant schedule option below the first five. This applies beyond London; the London example is just the regression that exposed the general rule.

## Business airport priority for London

Default ranking for business trips:
1. **LHR** — preferred default; best business airport, stronger long-haul/network-carrier fit, usually better ground logistics.
2. **LCY** — strong business airport when available, but often absent for Russia/CIS routings.
3. **LGW** — acceptable fallback when LHR is clearly worse by price/duration/connection safety.
4. **STN/LTN** — low-cost/leisure fallback only; use with explicit caveat and reason.

When the user says `LON`, search LHR explicitly before accepting a city-code result. Do not let aggregate order decide the recommendation.

## Required explanation when not choosing LHR

If recommending LGW/LTN/STN over LHR, state the concrete reason, for example:
- LHR option has unsafe connection (<120 same-airport or <300 cross-airport);
- LHR option requires Schengen/self-transfer risk while LGW/LTN does not;
- LHR option is materially longer or requires 2+ extra transfers;
- LHR price premium is large and the user approved cost sensitivity;
- final destination in London makes another airport materially better.

If the difference is small, prefer LHR.

## Search workflow

1. Run city-code search if useful for broad discovery: `SVX LON`, `LON SVX`.
2. Always follow with airport-specific searches for business trips:
   - `SVX LHR`, `LHR SVX`
   - optionally `SVX LGW`, `LGW SVX`, `SVX LCY`, `LCY SVX` if available
3. Compare candidates under business criteria:
   - airport priority (LHR first);
   - total duration and number of transfers;
   - connection buffer safety;
   - Schengen/visa exposure;
   - carrier/ticketing reliability;
   - baggage/through-ticket availability.
4. Present the LHR baseline first, then cheaper fallbacks.

## Reporting pattern

Use this structure:

- **Recommended for business:** LHR-first option, even if not the cheapest.
- **Acceptable fallback:** LGW/LTN/STN only with explicit trade-off.
- **Rejected:** cheap/long/low-comfort, overnight airport waits, low-cost chains, unsafe buffers, Schengen self-transfer risk.

Avoid wording that makes it look like the agent is “targeting” LTN/LGW. If those airports appear, frame them as fallbacks with a named trade-off.