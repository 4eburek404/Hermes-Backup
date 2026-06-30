# Airport Route Network Discovery

Use when the user asks "where can I fly direct from city X" or "what destinations does airport Y serve" — a route-network question, NOT a live-ticket-by-date question. The `flight-search` CLI cannot answer this: it searches live inventory for a specific route+date, not the full route map of an airport.

## When to use this instead of the CLI

- "В какие города можно улететь из X беспосадочным рейсом" — route network
- "What destinations does NTE serve" — route network
- "Is there a direct flight from X to Y" (without a date) — route existence, not booking

If the user gives a specific date + route, use the CLI (`python -m flights_cli --json search --request ...`), not this reference.

## Source hierarchy (use in order)

1. **Official airport website** — authoritative, current, distinguishes direct vs connecting. Usually at `<airport-domain>/destinations` or similar. May label flights "Vol direct" / "Vol avec escales" (FR) or "Direct" / "Connecting" (EN).
2. **Wikipedia "Airlines and destinations"** — quick, structured by airline with seasonal markers, but can lag behind new routes by months. URL: `en.wikipedia.org/wiki/<Airport_Name>_Airport`, section "Airlines and destinations".
3. **Google Flights "Explore"** or airport departure board — fallback if both above fail.

Google search itself may be CAPTCHA-blocked for automated browsers — go directly to Wikipedia/airport site by URL rather than searching.

## Browser extraction techniques for airport destination pages

### Carousel/slider layout (common on French/European airport sites)

Airport sites often use carousels grouped by country with city cards. The main page may show only 4-5 cities per country with a "+N destinations" link to a subpage.

**Step 1 — main page:** Extract all visible `h3` headings (country or city names) via `browser_console`:
```javascript
var h3s = document.querySelectorAll('h3'); var names = []; for(var i=0;i<h3s.length;i++){ var t = h3s[i].textContent.trim(); if(t && names.indexOf(t)===-1) names.push(t); } names.join(', ')
```

**Step 2 — expandable countries:** Find "+N destinations" links:
```javascript
var links = document.querySelectorAll('a'); var found = []; for(var i=0;i<links.length;i++){ var t = links[i].textContent.trim(); if(t.match(/^\+\d+ destinations?$/)) found.push(t + ' | href=' + links[i].href); } found.join('\n')
```
Navigate to each subpage URL and repeat the `h3` extraction.

**Step 3 — direct vs connecting:** On each page, classify by "Vol direct" / "Vol avec escales" label:
```javascript
var allH3 = document.querySelectorAll('h3'); var results = []; for(var i=0;i<allH3.length;i++){ var h3 = allH3[i]; var name = h3.textContent.trim(); if(!name || name.length>30) continue; var card = h3.parentElement.parentElement; var text = card.textContent; var isDirect = text.indexOf('Vol direct') !== -1; var isStop = text.indexOf('Vol avec escales') !== -1; results.push(name + ': ' + (isDirect ? 'DIRECT' : (isStop ? 'ESCALES' : 'UNKNOWN'))); } results.join('\n')
```

The `h3.parentElement.parentElement` (two levels up) is the card container that holds the flight-type label. One level up (`parentElement`) is only the heading wrapper.

## Known airport site structures

| Airport | URL pattern | Notes |
|---|---|---|
| Nantes (NTE) | `nantes.aeroport.fr/fr/toutes-les-destinations-en-direct-de-nantes` | Carousel by region → country. "+N destinations" subpages at `/fr/toutes-les-destinations/<country-slug>`. Labels: "Vol direct" / "Vol avec escales". |

(Add more as encountered.)

## Comparison: official site vs Wikipedia

Always compare. Official sites are more current (new routes announced months before Wikipedia editors update). Wikipedia may list routes that have been discontinued, and may miss seasonal-only or just-launched routes. When they disagree, the official site wins for "is there a direct flight" questions.

Example discrepancy found (Nantes, 2026-06-30):
- Official site has: Vienna (direct), Lapland/Rovaniemi (direct), Cairo (direct), Luxor (direct), Salerno (direct), San Vicente (direct), Brussels (new Oct 2026)
- Wikipedia has but official site marks as connecting: Bilbao, Santander, Bologna, Genoa, Turin, Verona, Dakhla, Ouarzazate
- Wikipedia has but official site doesn't list as direct: Paris-Orly (only CDG on site), Hamburg

## Presentation

Present results grouped by region (France → Europe → Africa → Americas → Middle East), with a separate callout for "on the site but with connections" destinations. Note the source and date of verification.