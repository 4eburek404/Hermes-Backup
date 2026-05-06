# Google Flights SVX→LON July 2026 — Detailed Findings

**Test date:** 2026-05-01  
**Route:** Екатеринбург (SVX) → London (LON), 19 Jul 2026, return 24 Jul 2026  
**Locale tested:** Russian (hl=ru, gl=RU) and English/UK (hl=en, gl=GB)

## Results Summary

### All flights shown (without airline filter)
All 5 results: **Flydubai + Emirates**, departure SVX 02:40, transit Dubai (DXB).

| # | Destination | Arrival | Duration | Layover DXB | Class | Price RT |
|---|---|---|---|---|---|---|
| 1 | STN (Stansted) | 18:45 | 20h05m | 7h20m | Эконом+Премиум | 339,451 ₽ |
| 2 | LHR (Heathrow) | 20:15 | 21h35m | 8h50m | Эконом+Премиум | 339,451 ₽ |
| 3 | LGW (Gatwick) | 21:30 | 22h50m | 9h55m | Эконом+Премиум | 339,484 ₽ |
| 4 | LGW (Gatwick) | 19:45 | 21h05m | 8h00m | Эконом | 431,779 ₽ |
| 5 | LHR (Heathrow) | 14:25 | 15h45m | 2h45m | Эконом | 434,356 ₽ |

### Turkish Airlines filter (TK applied)
**Zero results.** Google Flights message: "No options matching your filters."

### Prices from calendar (for date flexibility reference)
- 19→23 Jul: ₽338,882
- 19→24 Jul: ₽339,451
- 19→25 Jul (Sat): ₽326,067 (cheapest nearby)
- 19→26 Jul (Sun): ₽326,669
- 20→24 Jul: ₽707,858 (!!!)
- 21→26 Jul through 28→30 Jul range: ₽338,882–₽345,539

## Key Findings

1. **Sanctions filter is absolute**: No Russian carriers (SU, U6) shown at all. No code-share flights operated by Russian carriers. This is NOT IP/locale-based — changing `gl=GB&hl=en` makes no difference.

2. **Turkish Airlines not shown**: Despite TK operating IST↔LHR daily and having SU code-share to SVX, Google Flights returns 0 results when TK filter is applied. This suggests TK is also filtered from SVX-origin routes (possibly because TK's SVX route itself involves SU code-share, or because Google treats Russia-origin differently).

3. **Prices 3–4× over Travelpayouts**: Same Flydubai routing via DXB costs ₽339k on Google Flights vs ₽97k (best combo) or comparable amounts on Travelpayouts. Google appears to show a different fare bucket or currency conversion markup.

4. **Price calendar IS useful**: Even though the absolute prices are inflated, the relative price pattern across dates can inform cheap-date scouting. The calendar shows RT prices for ±30 days around selected dates.

5. **Return flight details**: When clicking an outbound flight, Google shows 2 return options:
   - Emirates+Flydubai LGW 10:05 → SVX 05:55+1 (15h50m, DXB 3h55m) — ₽339,484 RT
   - Emirates+Flydubai LGW 23:55 → SVX 01:40+2 (21h45m, DXB 9h35m, Business class) — ₽612,344 RT

## Comparison with Travelpayouts for same route

| Source | Best price | Airlines shown | TK available |
|---|---|---|---|
| Google Flights | ₽339,451 | Flydubai, Emirates only | No (0 results) |
| Travelpayouts API | ₽97,999 (combo) | SU, U6, TK, BA, W9, XQ, 2S + more | Yes (as operating_carrier) |
| Kupibilet (headless) | ~₽60,000–67,000 | Via AYT (SunExpress, Corendon) + via IST | Partial |

## Browser Automation Notes

- **URL search format**: `https://www.google.com/travel/flights/search?q=Flights+from+SVX+to+LON+on+2026-07-19+return+2026-07-24&curr=RUB&hl=en`
- **Natural language query** with airline name: `q=Turkish+Airlines+flights+from+SVX+to+LON` — Google correctly applies the airline filter
- **TFS parameter**: Complex protobuf-like parameter; don't try to construct manually. Let Google parse the natural language query instead.
- **Airline filter button**: `button "Airlines, Not selected"` (or `button "Авиакомпании, Не выбрано"` in Russian) — opens a filter panel. Also available via quick-filter buttons after search.
- **Date picker**: Click `textbox "Departure"/"Return"` → calendar dialog with price calendar
- **Tabs**: "Best" (top flights) and "Cheapest" (lowest price sort) tabs — both show same limited set for this route
- **"Limited flight results" banner**: Google explicitly shows "Google Flights has limited flight results on this route" for SVX→LON