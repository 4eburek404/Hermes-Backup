# SVX ↔ London, 19–24 July 2026 — Carrier-filtered results (SU/U6/TK)

Session context: user requested flights Екатеринбург→Лондон 19.07 and Лондон→Екатеринбург 24.07, then asked to filter for Аэрофлот (SU), Уральские авиалинии (U6), Turkish Airlines (TK).

## Method

Used `flights --json request search SVX LON --depart-date 2026-07-19 --currency RUB --live` (one-way) and filtered the `operating_carrier` field per leg in the JSON response. This produced more results than the round-trip Travelpayouts API call, and enabled carrier-level filtering.

## Outbound: SVX → LON, 19 July — SU/U6/TK options

| Price | Duration | Changes | Carriers | Route |
|---|---|---|---|---|
| 28 753 ₽ | 38h15m | 1 | SU + XQ | SVX 01:25 → AYT 04:50 → LGW 11:40(+1д), ночь в Анталье |
| 31 183 ₽ | 12h00m | 1 | SU + XQ | SVX 01:25 → AYT 04:50 → LTN 09:25 |
| 33 841 ₽ | 14h55m | 1 | SU + VF | SVX 10:30 → IST 13:55 → SAW/STN 21:25 (cross-airport!) |
| **37 421 ₽** | 15h55m | 1 | **SU + TK** | SVX 10:30 → IST 13:55 → LGW 22:25 |
| 41 336 ₽ | 18h05m | 2 | SU + TK + W9 | SVX 10:30 → IST → AYT → LTN 00:35(+1д) |
| 43 745 ₽ | 39h30m | 2 | SU + LO | SVX 10:30 → IST → WAW → LHR 22:00(+1д) |
| **45 246 ₽** | **11h20m** | 1 | **SU + BA** | SVX 10:30 → IST → **LHR** 17:50 ★ best option |
| 46 027 ₽ | 15h55m | 1 | SU + TK | SVX 10:30 → IST → LGW 22:25 |
| 54 802 ₽ | 15h30m | 2 | SU + LO | SVX 10:30 → IST → WAW → LHR 22:00 |
| 82 416 ₽ | 40h10m | 3 | U6 + LH + EN | SVX → DME → IST → FRA → LCY — 3 transfers, Schengen visa required |

★ Best outbound: SU630 + BA717 through IST to LHR, 45 246 ₽, 11h 20m, single 1h45m connection.

## Return: LON → SVX, 24 July — SU/U6/TK options

Only 2 results with SU/U6/TK in operating carriers:

| Price | Duration | Changes | Carriers | Route |
|---|---|---|---|---|
| 52 752 ₽ | 16h15m | 1 | W9 + SU | LGW 14:55 → AYT 21:20 → SVX 11:10(+1д), night stay in Antalya |
| 52 753 ₽ | 15h35m | 1 | W9 + U6 | LTN 07:05 → IST 13:10 → SVX 02:40(+1д) |

**Key finding:** Turkish Airlines (TK) did not operate directly LON→SVX or LON→IST→SVX on 24.07 in the cache. SU also absent from the return leg. Only U6 (Уральские) appears via IST on the second segment. The reverse direction is dominated by W9 (Wizz Air UK) on the LON→hub leg.

## Combined best (SU-prefiltered)

- Outbound: 45 246 ₽ (SU+BA, IST→LHR)
- Return: 52 753 ₽ (W9+U6, LTN→IST→SVX)
- **Total: ~98 000 ₽**

## Technical notes

- `flights route plan` with `--prefer-carrier SU --prefer-carrier U6 --prefer-carrier TK` is the CLI-native way to rank with carrier preference. However, `flights request search --live` returns raw Travelpayouts data with per-leg `operating_carrier` — more precise for filtering.
- One-way queries produce more results than round-trip for carrier filtering.
- The `main_airline` field is the marketing carrier, not necessarily the operating carrier. Always check `operating_carrier` on each `flight_leg`.