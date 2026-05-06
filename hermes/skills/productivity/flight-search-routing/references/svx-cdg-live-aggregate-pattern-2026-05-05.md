# SVX↔CDG live aggregate pattern — 2026-05-05

Session context: user asked for `15.08 SVX-CDG, 19.08 CDG-SVX`; current date was 2026-05-05, interpreted as 2026-08-15 outbound and 2026-08-19 return, economy/RUB.

## What happened

- Travelpayouts/Aviasales round-trip `SVX→CDG→SVX` returned 0 results.
- Travelpayouts one-way direct/connecting `SVX→CDG` and `CDG→SVX` also returned 0 results.
- Segmenting via IST exposed useful Russian/Turkey legs but did not produce the best practical Paris itinerary on the requested dates.
- `flights --json kb-search` live aggregate produced many direct city-pair options and was more useful for SVX↔CDG.

Commands used:

```bash
flights --json kb-search SVX CDG --depart-date 2026-08-15 --limit 10 --timeout 45
flights --json kb-search CDG SVX --depart-date 2026-08-19 --limit 10 --timeout 45
```

## Useful options found

### Balanced / low-risk-ish among found live options

Outbound live Kupibilet: ~38,329 RUB

- `SVX 2026-08-15 15:00+05 → EVN 17:45+04` — SU684
- `EVN 2026-08-16 03:00+04 → FRA 05:40+02` — DE4338
- `FRA 2026-08-16 08:30+02 → CDG 09:50+02` — DE4265
- 2 changes; elapsed about 21h50; arrives next day.

Return live Kupibilet: ~39,034 RUB

- `CDG 2026-08-19 15:40+02 → ADB 20:05+03` — XQ917
- `ADB 2026-08-19 22:00+03 → AYT 23:05+03` — XQ7293
- `AYT 2026-08-20 10:05+03 → SVX 16:50+05` — DP956
- 2 changes; elapsed about 22h10.

Combined reference price: ~77,363 RUB.

### If same-day arrival to Paris matters

Outbound live Kupibilet: ~44,882 RUB

- `SVX 2026-08-15 01:35+05 → GYD 03:40+04` — J2646
- `GYD 2026-08-15 09:20+04 → PRG 12:00+02` — J2109
- `PRG 2026-08-15 17:30+02 → CDG 19:25+02` — QS1036
- 2 changes; elapsed about 20h50; arrives on the requested outbound date.

Combined with the ADB/AYT return above: ~83,916 RUB.

### Cheapest raw live pair found, but worse risk

- Outbound EVN/FRA option above: ~38,329 RUB.
- Return `CDG→BEG→BUD→EVN→SVX`: ~37,121 RUB.
- Combined ~75,450 RUB, but 3 changes on the return and more self-transfer/baggage/visa exposure; do not present as the default recommendation without risk warning.

## Separate direct-segment correction

The user corrected the workflow: for Russia↔Europe one-stop questions, do not rely only on aggregate one-stop results. Search direct-only segments through candidate hubs and assemble compatible pairs.

Artifacts:

- Manual corrected search: `/home/konstantin/flight_search_artifacts/svx_cdg_2026-08-15_2026-08-19_separate_segments_kupibilet.json`
- Regression smoke for the new CLI gate: `/home/konstantin/flight_search_artifacts/svx_cdg_2026-08-15_2026-08-19_kb_assemble_cli_ayt.json`

Current canonical CLI gate:

```bash
flights --json route kb-assemble SVX CDG \
  --depart-date 2026-08-15 \
  --return-date 2026-08-19 \
  --hub AYT --hub IST --hub TBS --hub EVN --hub DXB \
  --segment-limit 30
```

Candidate hubs checked as direct segments in the original correction: `AYT`, `TBS`, `EVN`, `DXB`, `IST`, `SAW`, `GYD`, `BEG`, `AUH`.

Key corrected findings:

- Practical AYT outbound: `SVX→AYT DP955 2026-08-15 06:05+05→09:30+03` + `AYT→CDG XQ510 13:35+03→16:55+02`; live segment total ~55,139 RUB; layover 4h05; same-day Paris arrival.
- AYT return direct-segment assembly: `CDG→AYT XQ511 2026-08-19 17:45` + `AYT→SVX DP956 2026-08-20 10:05+03→16:50+05`; return around mid-30k RUB in the live segment assembly; overnight AYT layover.
- Cheapest displayed IST return: `CDG→IST AF1390 2026-08-19 22:55+02→2026-08-20 03:30+03` + `IST→SVX SU631 2026-08-21 12:50+03→19:55+05`; ~37,727 RUB, but layover 33h20 and arrival 21.08, so demote despite price.
- IST both ways exists but is not the default best answer: outbound via `SVX→IST U6773` + `IST→CDG TK1827` was ~70,785 RUB; with the cheap IST return the round-trip was ~108,512 RUB and still operationally poor on the return.

## Route-specific lessons

- For SVX↔CDG, do not stop after empty Travelpayouts round-trip or one-way city-pair cache. Run Kupibilet live aggregate before concluding no options.
- After any aggregate answer, if the user asks for one stop or a hub, run direct-only segment searches and assemble pairs. Report actual airport codes and layover buffers, not just the aggregate itinerary label.
- IST is a useful default hub for Russia↔Europe, but not always the best practical answer for CDG on specific dates. Compare direct city-pair live aggregate with hub assembly and AYT/TBS/EVN/DXB-style segment assembly.
- Demote London (`LGW/LTN/STN/LHR`) results for Paris itineraries unless user explicitly accepts UK transit/visa exposure and airport-change risk.
- Separate “cheapest”, “same-day arrival”, and “fewer/safer transfers” buckets. On this route the cheapest acceptable option arrived CDG the next day; the same-day arrival option cost materially more.
- Always label Travelpayouts results as cached/advisory and Kupibilet as live aggregate/not official airline source; final fare and seat availability must be rechecked before purchase.
