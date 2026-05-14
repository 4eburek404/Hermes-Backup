# SVX↔CDG Route Patterns (discovered 2026-05-09)

## Direct

SVX↔CDG: **no direct flights** (confirmed via Kupibilet live, not cached).

## Via IST (primary hub)

SVX→IST segments (Kupibilet, 17 Aug 2026):
- **DP (Pobeda)**: SVX→VKO→IST — overnight in VKO, arrival in IST next day 12:05 — impractical for same-day connection
- **J2 (Azerbaijan Airlines)**: SVX→GYD→IST — departs SVX 01:30, arrives IST 10:35 or 21:05 — same-day arrival possible if you take the morning connection (10:35)

IST→CDG segments (FLI MCP):
- Live offers available both on 17 Aug (7 offers) and 18 Aug (8 offers)
- Turkish Airlines (TK) has multiple daily CDG frequencies

## Via Moscow + IST (the assembled route)

SVX→SVO (SU6208/FV, 05:10→05:45) → SVO→IST (SU2136/SU, 08:45→14:15) → overnight in IST → IST→CDG (TK1821, 07:15→10:00)

Return: CDG→IST (TK1822, 11:40→16:10) → IST→SVX (U6774/U6, 19:45→02:40+1)

Price: ~97-100k RUB round-trip. Risk: excellent/0.

## Without overnight (same-day SVX→IST→CDG)

Only viable via J2 (Azerbaijan Airlines) with GYD transfer:
- SVX 01:30→GYD 03:35 → GYD 08:30→IST 10:35 → IST→CDG (afternoon TK flight)
- Trade-off: very early departure from SVX (01:30), two connections, separate tickets likely

## Key lesson for future queries

When a `live-assemble` result shows an overnight layover and the user asks "can I avoid the overnight?", do not answer from the compact report alone. The assembler may not combine same-day segments from different carriers/providers. Probe raw `kb-search` and `fli-search` for the same date to find alternative routing (e.g. J2 via GYD).

The assembler's ranking profile (`business`) may prefer a route through Moscow (SU) with overnight over a same-day connection through an unfamiliar carrier/airport (J2, GYD) — this is a profile bias, not physical impossibility.
