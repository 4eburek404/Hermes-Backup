# SVX→LHR 2026-08-16 frontier regression

Session-specific regression/example for the generic business-flight-routing policy. Use this only for calibration of London/LHR frontier handling; do not treat prices or availability as durable facts.

## Why this exists

A user test on `16.08 SVX LHR` exercised three reusable rules:

1. For London business travel, target exact `LHR` first; do not let `LON`/secondary-airport results determine the answer.
2. For carrier-sensitive or exact-airport routing, inspect `route kb-assemble` `data.segment_results` as well as final `data.ranked` so price/source ordering does not hide frontier options.
3. When the user challenges an omission, answer with the correct procedure and skill guardrail first, not a long error narrative.

## Repro shape

Artifact path used in the session:

```text
/home/konstantin/flight_search_artifacts/svx_lhr_2026-08-16_live
```

Core command shape:

```bash
flights --json route kb-assemble SVX LHR \
  --depart-date 2026-08-16 \
  --origin-airport SVX \
  --destination-airport LHR \
  --hub IST --hub TBS --hub DXB --hub GYD --hub EVN --hub AYT --hub SAW \
  --currency RUB \
  --profile business \
  --ticketing separate \
  --min-same-airport-min 90 \
  --limit-per-pair 20 \
  --segment-limit 40 \
  --include-candidates 160 \
  --include-rejected-pairs 100 \
  --include-segment-results 40
```

Cross-check non-Russian hub segments with `fli`:

```bash
fli flights IST LHR 2026-08-16 --format json --currency RUB --all
fli flights DXB LHR 2026-08-16 --format json --currency RUB --all
fli flights TBS LHR 2026-08-16 --format json --currency RUB --all
```

## Frontier examples from the session

Best-balanced same-day LHR recommendation under the current 90/120 buffer policy:

```text
U6773  SVX 16.08 07:20 +05 → IST 16.08 10:50 +03
TK1985 IST 16.08 13:15 +03 → LHR 16.08 15:10 +01
Connection: 145 min, IST→IST, same airport; clears 120-min business-preferred threshold
```

Safer-buffer same-day option:

```text
U6773  SVX 07:20 +05 → IST 10:50 +03
TK1971 IST 14:50 +03 → LHR 16:40 +01
Connection: 240 min, IST→IST, same airport; later arrival but larger buffer
```

Cheaper/later same-day option:

```text
SU630  SVX 10:30 +05 → IST 13:55 +03
TK1983 IST 19:05 +03 → LHR 21:05 +01
Connection: 310 min, IST→IST, lower price but much later arrival
```

BA alternative:

```text
U6773  SVX 07:20 +05 → IST 10:50 +03
BA717  IST 15:40 +03 → LHR 17:50 +01
Connection: 290 min, IST→IST
```

Overnight cheaper frontier not primary:

```text
WZ1403 SVX 16.08 12:55 +05 → TBS 16.08 15:25 +04
BA891  TBS 17.08 07:10 +04 → LHR 17.08 10:00 +01
Connection: 945 min, overnight in TBS
```

## Answering pattern reinforced

For future London business searches, present:

- **Recommended for business:** exact-LHR same-day option with the best overall balance; ≥120 min same-airport clears business-preferred buffer.
- **Tight:** if it is 90–119 min, label the buffer trade-off explicitly and do not make it first unless the user asked for earliest arrival.
- **Cheaper/later:** if materially cheaper but late arrival or overnight, demote explicitly.
- **Carrier bucket:** if TK/BA options exist, show the best representative instead of saying only the global rank.
- **Rejected/demoted:** secondary airports, cross-airport substitutions, overnight waits, and tight self-transfer windows only when they explain a decision.

## Non-durable data warning

Flight numbers, prices, availability, and schedules are snapshots from one live session. Re-run live tools for any real purchase or future date check.
