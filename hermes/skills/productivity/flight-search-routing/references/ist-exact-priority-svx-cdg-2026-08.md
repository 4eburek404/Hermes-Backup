# IST-exact priority pattern — SVX↔CDG 2026-08-15/20

**Scope:** route-specific regression/golden example only. The reusable, route-independent business-flight policy contract lives in `references/business-flight-routing.schema.json`. Do not bind generic routing to SVX↔CDG/dates, and do not require the user to restate `IST exactly` before applying business/preferred-airport defaults.

Session signal: user corrected ranking from cheapest to **convenient/fast**, with **IST exactly** as preferred hub and airlines **SU/U6/TK** prioritized. This is a class-level lesson for Russia↔Europe business-style routing: price-first aggregate results can be wrong even when cheap.

## User-stated priority

- Do **not** optimize primarily for cheapest fare.
- Optimize for: convenient, fast, operationally clean.
- Hub priority: `IST` exactly; exclude `SAW` unless user explicitly accepts airport change.
- Airline priority: `SU`, `U6`, `TK`.

## Workflow used

1. Search exact direct segments, not only city-pair aggregates:

```bash
flights --json kb-search SVX IST --depart-date 2026-08-15 --direct-only --limit 30 --timeout 60
flights --json kb-search IST CDG --depart-date 2026-08-15 --direct-only --limit 30 --timeout 60
flights --json kb-search CDG IST --depart-date 2026-08-20 --direct-only --limit 30 --timeout 60
flights --json kb-search IST SVX --depart-date 2026-08-20 --direct-only --limit 30 --timeout 60
```

2. Carrier-filter where possible:

```bash
flights --json kb-search SVX IST --depart-date 2026-08-15 --direct-only --only-carrier U6
flights --json kb-search IST CDG --depart-date 2026-08-15 --direct-only --only-carrier TK
flights --json kb-search CDG IST --depart-date 2026-08-20 --direct-only --only-carrier TK
flights --json kb-search IST SVX --depart-date 2026-08-20 --direct-only --only-carrier U6
```

3. Cross-check non-Russian TK segments with `fli` / Google Flights:

```bash
fli flights IST CDG 2026-08-15 --airlines TK --currency RUB
fli flights CDG IST 2026-08-20 --airlines TK --currency RUB
fli flights IST CDG 2026-08-15 --return 2026-08-20 --airlines TK --stops 0 --currency RUB --format json
```

4. Cross-check U6 calendar using current CLI syntax:

```bash
flights --json u6-prices SVX IST --from-date 2026-08-15 --date 2026-08-15 --limit 10
flights --json u6-prices IST SVX --from-date 2026-08-20 --date 2026-08-20 --limit 10
```

5. Assemble manually with exact airport equality:

- accept `arrival_airport == departure_airport == IST` only;
- reject or separately flag `IST→SAW` / `SAW→IST` even if the city label is Istanbul;
- require at least 90 min same-airport buffer on separate tickets; treat 90–119 min as tight and ≥120 min as business-preferred; add more buffer only when concrete baggage/border/source risk justifies it.

## Findings for the session route

Exact-IST outbound practical options:

- `U6773 SVX 15.08 07:20+05 → IST 10:50+03` + `TK1833 IST 14:10+03 → CDG 17:00+02`; layover 3h20; elapsed ~12h40; best speed/safety balance.
- `U6773` + `TK1827 IST 15:30+03 → CDG 18:05+02`; layover 4h40; elapsed ~13h45; safer buffer, 1h05 later arrival.
- `U6773` + `TK1825 IST 12:25+03 → CDG 15:05+02`; layover 1h35; fastest-ish but too tight for separate U6/TK with baggage; demote/reject unless protected ticket.

Exact-IST return practical options:

- `TK1822 CDG 20.08 11:40+02 → IST 16:10+03` + `U6774 IST 19:45+03 → SVX 21.08 02:25+05`; layover 3h35; elapsed ~11h45; best safety/speed balance.
- `TK1832 CDG 12:25+02 → IST 17:05+03` + `U6774`; layover 2h40; elapsed ~11h00; acceptable but tighter.
- `TK1824 CDG 14:20+02 → IST 18:55+03` + `U6774`; layover 0h50; reject unless a protected through-ticket proves MCT/through baggage.
- `TK1828 CDG 19:45+02 → IST 21.08 00:10+03` + `SU631 IST 12:50+03 → SVX 19:55+05`; long overnight layover 12h40; useful only if late Paris departure matters.

## Reporting pattern

When this priority is stated, final answer should start with the recommended clean itinerary, not a cheapest bucket. Mention approximate total only after the operational recommendation. Explicitly say `SAW/VF excluded because user requested IST exactly`.

Suggested phrasing:

> Мой выбор: `U6773 + TK1833` туда и `TK1822 + U6774` обратно. Это не самый дешёвый вариант, но он соответствует приоритетам: exact IST, SU/U6/TK, 1 пересадка в каждую сторону, нормальные буферы.

## Canonical golden answer artifact

The user explicitly approved the answer and asked to preserve it as a golden answer. Local artifact:

`/home/konstantin/flight_search_artifacts/ist_exact_su_u6_tk_2026-08-15_20/golden_answer.md`

Use this artifact as the regression fixture for tone, ordering, and recommendation style on similar requests: brief status first, then verified facts, then the clean recommended itinerary, then practical purchase grouping, then rejected/tight options with named reasons.

### Golden answer skeleton

1. State that ranking switched from cheapest to **fast/convenient/exact IST/SU-U6-TK**.
2. Verified facts:
   - `SVX→IST 15.08`: `U6773` is the direct preferred segment found.
   - `IST→CDG` / `CDG→IST`: TK direct from/to exact `IST`, not `SAW`.
   - `IST→SVX`: `U6774` on 20.08 evening; `SU631` / `U6774` on 21.08.
   - `SAW/VF` excluded because user asked for `IST exactly`.
3. Main recommendation:
   - outbound: `U6773 SVX 07:20+05 → IST 10:50+03`, layover `3h20`, `TK1833 IST 14:10+03 → CDG 17:00+02`;
   - return: `TK1822 CDG 11:40+02 → IST 16:10+03`, layover `3h35`, `U6774 IST 19:45+03 → SVX 21.08 02:25+05`.
4. Practical purchase grouping:
   - U6 one-way `SVX→IST`;
   - TK round trip `IST→CDG→IST`;
   - U6 one-way `IST→SVX`.
5. Alternatives/rejections:
   - `U6773 + TK1827` as safer outbound buffer, later arrival;
   - `U6773 + TK1825` demoted for `1h35` separate-ticket/baggage risk;
   - `TK1824 + U6774` rejected for `0h50` layover unless protected through-ticket.

