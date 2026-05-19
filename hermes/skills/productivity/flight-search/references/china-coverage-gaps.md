# China Coverage Gaps

## Observed: 2026-05-10 (session, SVX → SHE on 2025-09-17)

### Provider results

| Route | Kupibilet | Travelpayouts | FLI MCP |
|-------|-----------|---------------|---------|
| SVX → SHE direct | 0 | 0 | — |
| SVX → SVO/DME/OVB → SHE (hub legs) | 0 | 0 | — |
| SVO → SHE | 0 | 0 | N/A |
| DME → SHE | 0 | 0 | N/A |
| LED → SHE | 0 | 0 | N/A |
| IST → SHE | N/A | N/A | `Invalid parameter value` |
| DXB → SHE | N/A | N/A | `Invalid parameter value` |
| PEK → SHE | 0 | 0 | N/A |
| PVG → SHE | 0 | 0 | N/A |
| CAN → SHE | 0 | 0 | N/A |
| SVX → PEK | 0 | 0 | N/A |

### Diagnosis

- Kupibilet returns HTTP 200 with `offer_count: 0` and `raw_variant_count: 0` for all China-bound segments checked. This is a coverage gap, not a temporary outage.
- Historical Travelpayouts cached-price probes also returned empty data, but that surface is retired and must not be used as current evidence.
- FLI MCP returns `Invalid parameter value` on IST→SHE and DXB→SHE hub-to-destination legs. The sidecar cannot handle SHE as a destination.
- Dates 2025-09-15 through 2025-09-20 were checked; all returned 0.

### Practical routing for SVX → SHE (Shenyang, China)

- **SVX → PEK direct** (Ural Airlines / China Eastern seasonal) + PEK → SHE (domestic China, ~30+ daily flights, ~1.5h)
- **SVX → SVO → PEK/PVG → SHE** via Moscow and a China hub
- **SVX → SVO → SHE** if Aeroflot or China Southern has a Moscow–Shenyang route (seasonal, check directly)

### Horizon discovery (SVX → SHE, 2026-05-10 session)

All aggregator queries for September **2025** returned 0. This was not a coverage gap — it was a **horizon issue**. Historical cached TP horizon checks suggested data started May 2026 (approximately 10-12 months ahead). Kupibilet `kb-search` for September **2026** returned 10+ offers for the same route, proving the route is aggregator-covered but date-out-of-range.

Key finding: cached-price emptiness is not proof that the route is dead. The normal path now uses live assembly and Kupibilet/FLI controls; retired TP cached-price probes are not a current diagnostic step.

Technique for out-of-horizon dates:
1. Run `kb-search ORIGIN DEST --depart-date <in-horizon-date>` (1-11 months out) with the same weekday or month to get actual flight numbers, carriers, and routing patterns.
2. Present these as **seasonal analogues** with a clear note: "Prices and schedule for the equivalent month next year; verify on the booking screen for the exact date."
3. This avoids presenting empty results and then asking the user what to do.

Sample analogue data for SVX → SHE (September 2026, for reference):

| Date | Route | Price (RUB) | Duration | Carriers |
|------|-------|-------------|----------|----------|
| Sep 14 | SVX→SVO→PVG→SHE | ~41 100 | ~14h | DP+MU+FM |
| Sep 15 | SVX→TAS→CAN→SHE | ~40 900 | ~12-24h | HY+CZ |
| Sep 16 | SVX→SVO→PVG→SHE | ~42 000 | ~14h | DP+MU+FM |
| Sep 17 | SVX→SVO→PEK→SHE | ~69 400 | ~10h | U6+CZ+KE (3-stop) |
| Sep 18 | SVX→SVO→PEK→SHE | ~42 500 | ~14h | DP+MU |

### Agent guidance

When Kupibilet returns 0 on a route and FLI MCP fails with `Invalid parameter value`:

**First**, determine whether the route is aggregator-blind or just out-of-horizon:
1. Try `kb-search` with a date 1-11 months from now on the same route.
2. If live data appears for in-horizon dates → it is a **horizon issue**, not a coverage gap. Present seasonal analogue data and advise checking exact dates on the booking screen.

**If the route is truly aggregator-blind** (no data even within horizon):
1. State clearly that both aggregators have no coverage for the destination.
2. Do not claim «no flights exist».
3. Suggest checking airline websites or booking aggregators directly.
4. Provide the known routing pattern (hub + domestic China leg) if the user needs a concrete path.

**Never** present empty results and then ask the user what to do. The user wants options, not a diagnosis of why the tool returned nothing. Probe first, then present what you found.