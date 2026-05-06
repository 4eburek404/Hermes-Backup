# SVX ↔ London, 19–23 July 2026 — cache and browser notes

Session context: user asked for Екатеринбург → Лондон 19.07.2026 and Лондон → Екатеринбург 23.07.2026, then asked whether browser search would be better.

## What worked

Travelpayouts/Aviasales cache returned no direct round-trip results for:
- SVX → LHR/LGW/STN/LTN with return 23.07.2026

Segment-by-segment cache search produced viable route families:

### Antalya (AYT) family — cheapest/likely live aggregator favorite
- Outbound candidate: SVX → AYT Aeroflot SU792 01:45 → 04:50 (~28,181 RUB), then AYT → LGW SunExpress XQ590 07:55 → 10:35 (~5,789 RUB). Connection ~3h05.
- Return candidate: LGW → AYT SunExpress XQ591 11:55 → 18:15 (~20,031 RUB), then AYT → SVX Southwind 2S225 20:55 → 03:25+1 (~20,033 RUB). Connection ~2h40.
- Approx total from cache: ~74,034 RUB.
- Risk: likely separate tickets; 2h40–3h05 is marginal with checked baggage/re-check.

### Istanbul/LHR family — more business-like but pricier
- Outbound: SVX → IST Aeroflot SU630 10:30 → 13:55 (~24,766 RUB), then IST → LHR Turkish TK1987 20:25 → 22:25 (~11,037 RUB). Connection ~6h30.
- Return cache option: LHR → WAW → IST LOT 06:30 → 16:40 (~26,678 RUB), then IST → SVX Ural U6774 19:45 → 02:25+1 (~30,336 RUB). Connection ~3h05.
- Approx total from cache: ~92,817 RUB.
- Risk: EU/WAW transit and separate-ticket protection must be checked.

## Browser attempt outcome

A delegated browser search against Kupibilet timed out after 600 seconds. A second smoke-test subagent reported no browser/web navigation tools available in that child session. Therefore no live browser result was obtained.

Future handling:
- Do not imply live browser verification unless the results page was actually reached.
- If browser tools are available, use a short Kupibilet smoke-test first: homepage → fill Russian city names (Екатеринбург, Лондон) → exact dates → results visible.
- If the smoke-test fails or times out, report the exact blocker and keep cache-derived route suggestions labeled as advisory only.

## Presentation lesson

For this route, present airport compatibility and ticket-protection risks before recommending a "cheap" option:
- AYT is one airport but leisure/self-transfer risk remains.
- IST and SAW must not be mixed without explicit ground-transfer warning.
- London airport differences (LHR/LGW/STN/LTN) matter for user logistics but are acceptable if the user stays in London between outbound and return.
