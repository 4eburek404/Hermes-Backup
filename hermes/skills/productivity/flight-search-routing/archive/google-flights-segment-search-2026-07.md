# Google Flights Segment Search — SVX↔LON via IST, July 2026

**Test date:** 2026-05-01
**Method:** Search each segment separately on Google Flights (one-way mode)
**Reason:** Direct SVX→LON search returns only Flydubai/Emirates at 339k+₽ due to sanctions filter. Segment search bypasses this for non-Russian-origin segments.

## Key Discovery

**The sanctions filter on Google Flights is departure-based, not route-based.** It blocks routes where the departure city is in Russia. But:
- **IST→LON** (departure Turkey): ✅ Full results, 12+ Turkish Airlines flights
- **LON→IST** (departure UK): ✅ Full results, 12+ Turkish Airlines flights
- **IST→SVX** (departure Turkey): ✅ Shows Azerbaijan Airlines + Emirates/Flydubai
- **SVX→IST** (departure Russia): ❌ Only Flydubai/Emirates via Dubai

This means for hub-based itineraries, searching **non-Russian segments individually** on Google Flights yields real prices and schedules, while the Russian-origin segment needs Travelpayouts/Kupibilet/Ural Airlines.

## Segment Results

### IST → LON, 19 Jul 2026 (Turkish Airlines, one-way)

| Depart | Arrive | Airport | Duration | Price |
|-------|--------|---------|----------|-------|
| 07:50 | 09:50 | IST→LHR | 4ч | 13 385 ₽ |
| 07:55 | 09:55 | IST→LGW | 4ч | 13 004 ₽ |
| 09:40 | 11:40 | IST→LHR | 4ч | 15 030 ₽ |
| 11:05 | 13:10 | IST→LGW | 4ч 5м | 13 004 ₽ |
| 13:15 | 15:10 | IST→LHR | 3ч 55м | 15 030 ₽ |
| 14:50 | 16:40 | IST→LHR | 3ч 50м | 15 030 ₽ |
| 14:35 | 16:40 | IST→STN | 4ч 5м | 14 500 ₽ |
| 19:05 | 21:05 | IST→LHR | 4ч | 15 404 ₽ |
| **20:25** | **22:25** | **IST→LGW** | **4ч** | **9 640 ₽** ← cheapest |
| 20:25 | 22:25 | IST→LHR | 4ч | 10 387 ₽ |

All flights are **nonstop**, operated by Turkish Airlines.

### LON → IST, 24 Jul 2026 (Turkish Airlines, one-way)

| Depart | Arrive | Airport | Duration | Price |
|-------|--------|---------|----------|-------|
| 06:30 | 12:25 | LHR→IST | 3ч 55м | 36 026 ₽ |
| 06:40 | 12:35 | STN→IST | 3ч 55м | 38 944 ₽ |
| 07:25 | 13:15 | LGW→IST | 3ч 50м | 40 160 ₽ |
| 10:50 | 16:45 | STN→IST | 3ч 55м | 46 884 ₽ |
| 10:50 | 16:50 | LGW→IST | 4ч | 40 160 ₽ |
| 11:20 | 17:15 | LHR→IST | 3ч 55м | 36 535 ₽ |
| **14:05** | **20:00** | **LGW→IST** | **3ч 55м** | **33 136 ₽** ← cheapest |
| 16:45 | 22:35 | LHR→IST | 3ч 50м | 36 026 ₽ |
| 17:35 | 23:30 | STN→IST | 3ч 55м | 38 944 ₽ |
| 17:35 | 23:30 | LGW→IST | 3ч 55м | 40 669 ₽ |
| 18:30 | 00:15+1 | LHR→IST | 3ч 45м | 36 026 ₽ |
| 22:40 | 04:20+1 | LHR→IST | 3ч 40м | 36 026 ₽ |

All flights are **nonstop**, operated by Turkish Airlines.

### IST → SVX, 24 Jul 2026 (one-way)

| Depart | Arrive | Airline | Stops | Duration | Price |
|-------|--------|---------|-------|----------|-------|
| **12:00** | **00:35+1** | **Azerbaijan Airlines** | **1 (GYD 4ч50м)** | **10ч 35м** | **23 235 ₽** |
| 16:25 | 05:55+1 | Emirates/Flydubai | 1 (DXB 2ч5м) | 11ч 30м | 111 505 ₽ |
| 02:10 | 05:55+1 | Flydubai/Emirates | 1 (DXB 16ч15м) | 25ч 45м | 111 505 ₽ |
| 06:55 | 05:55+1 | TK/Flydubai/Emirates | 2 (OTP, DXB) | 21ч | 158 820 ₽ |
| 02:10 | 01:40+1 | Flydubai/Emirates | 1 (DXB 11ч55м) | 21ч 30м | 194 204 ₽ |
| 18:35 | 01:40+2 | Flydubai/Emirates | 1 (DXB 19ч30м) | 29ч 5м | 486 440 ₽ (Business) |
| 23:30 | 01:40+2 | Emirates/Flydubai | 1 (DXB 14ч45м) | 24ч 10м | 486 440 ₽ (Business) |

**Best IST→SVX:** Azerbaijan Airlines via Baku — 23 235 ₽, 10ч 35м, departure 12:00 arrival 00:35+1.

### SVX → IST, 19 Jul 2026

**Google Flights shows only:** Flydubai/Emirates via DXB from 273 685 ₽ (round-trip pricing, useless).
**Use Travelpayouts/Kupibilet for this segment instead.**

From Travelpayouts data:
- SU (Аэрофлот) SVX 10:30 → IST 13:55: ~31-37k₽ one-way
- U6 (Уральские) direct: check Kupibilet/Ural Airlines headless

## Optimal Combinations (Estimated Total)

Using Google Flights for IST↔LON + Travelpayouts for SVX↔IST:

| Route | Segment | Source | Price |
|-------|---------|--------|-------|
| **Cheapest via TK+AH** | | | |
| SVX→IST | SU direct ~10:30→13:55 | Travelpayouts | ~31-37k₽ |
| IST→LON | TK 20:25→22:25 LGW | Google Flights | 9 640 ₽ |
| LON→IST | TK 14:05→20:00 LGW | Google Flights | 33 136 ₽ |
| IST→SVX | AH 12:00→00:35+1 via GYD | Google Flights | 23 235 ₽ |
| **TOTAL** | | | **~97-103k₽** |

| Route | Segment | Source | Price |
|-------|---------|--------|-------|
| **More convenient via TK** | | | |
| SVX→IST | SU direct | Travelpayouts | ~31-37k₽ |
| IST→LON | TK 14:50→16:40 LHR | Google Flights | 15 030 ₽ |
| LON→IST | TK 18:30→00:15+1 LHR | Google Flights | 36 026 ₽ |
| IST→SVX | AH 12:00→00:35+1 via GYD | Google Flights | 23 235 ₽ |
| **TOTAL** | | | **~105-111k₽** |

## Connection Time Analysis

**Outbound (19 Jul):**
- SVX→IST: arr ~13:55 (SU) → IST→LON: dep 14:50 (TK) = **55 min connection** ⚠️ TOO TIGHT for separate tickets
- Better: SVX→IST arr ~13:55 → IST→LON 19:05 (TK) = **5h 10m** ✅ safe

**Return (24 Jul):**
- LON→IST: arr 20:00 (LGW, TK) → IST→SVX: dep 12:00+1 (AH) = **16h layover** (overnight in IST) ✅
- Or: LON→IST arr 00:15+1 (LHR, TK) → IST→SVX is no same-day option, need next day

## Google Flights Search Technique

### One-way segment search (key discovery)

```
URL: https://www.google.com/travel/flights/search?q=One+way+flights+from+IST+to+LON+on+July+19+2026+Turkish+Airlines&curr=RUB&hl=en&gl=GB
```

The `q=` natural language query with airline name works perfectly for non-Russian routes.
- "One way" in query sets one-way mode
- Airline name ("Turkish Airlines") applies the airline filter
- `curr=RUB` for ruble pricing
- `gl=GB` locale for better results

### Extracting flight data from JS

```js
// Extract all flight results from Google Flights page
const items = document.querySelectorAll('li');
const results = [];
items.forEach(li => {
  const text = li.innerText?.trim();
  if (text && text.includes('RUB') && (text.includes('Nonstop') || text.includes('stop'))) {
    results.push(text.replace(/\n+/g, ' | ').substring(0, 300));
  }
});
JSON.stringify(results, null, 2);
```

This produces clean pipe-separated flight lines like:
```
"8:25 PM | – | 10:25 PM | Turkish Airlines | 4 hr | IST–LGW | Nonstop | 192 kg CO2e | -7% emissions | RUB 9,640"
```