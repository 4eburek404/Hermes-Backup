# Browser Headless Workflows

Step-by-step instructions for headless browser flight searches. Load this file only when actually performing browser-based searches.

## Chrome on Ubuntu 24.04+ Prerequisite

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
echo '{"args":["--no-sandbox","--disable-gpu","--disable-dev-shm-usage","--disable-software-rasterizer","--no-zygote"]}' > ~/.agent-browser/launch-config.json
```

## Execution Discipline

Do not report a "browser search" unless browser tool actually reached the results page. If timeout or missing browser tools — state as blocker, keep cached/API findings labeled as non-live. Run a short smoke-test first before spending a long agent run.

## Kupibilet (Headless — Works)

**⚠️ URL navigation (`/search/SVX-LON/...`) always redirects to homepage — dead end.** Always use form fill.

### Workflow

1. Navigate to `https://www.kupibilet.ru/` (homepage only)
2. Dismiss cookie popup (click "Согласен")
3. **"Откуда":** Clear via JS (`input.focus(); input.value=''; input.dispatchEvent(new Event('input',{bubbles:true}));`), type Russian city name (e.g. "Екатеринбург"), select from dropdown
4. **"Куда":** Type city name (e.g. "Лондон"), select "LON" for all airports or specific
5. **Dates:** Click date field → navigate months via `.rdp-nav_next.click()` → switch to "Точная дата" mode → click departure → click return. **Bug:** first click may not register, try again.
6. Click **"Найти"**, wait 8-10s for results

### Data Extraction (from results page)

```js
// Route segments
/(\\d{2}:\\d{2})\\s+([A-Z]{3})\\s+(\\d{2}:\\d{2})/g
// Airport codes
/\\b(SVX|STN|LHR|LGW|LTN|IST|SAW|AYT)\\b/g
// Prices
/(\\d{1,3}\\s?\\d{3})\\s?₽/g
```

### Round-Trip Searches

For round-trip (SVX↔LON), query Kupibilet `frontend_search` with two `trips` in one payload. Dedupe/rank by arrival date, same-airport connections, Schengen/self-transfer risk — **not raw cheapest price**. CLI: `flights kb-search SVX LON`.

### Ranking Rules (Kupibilet Round-Trip)

- Don't recommend cheapest if it arrives too late for the trip
- Remove/flag airport mismatches (arrival ≠ next departure)
- Prefer same-airport international layovers ≥3h for separate tickets
- London airport change across stay = acceptable open-jaw, NOT same-day transfer
- Flag Schengen transit/self-transfer risk separately from price

## Ural Airlines UI (Headless — Fallback for Flight Details)

**Best for: SVX↔IST direct**, when Travelpayouts cache misses U6.

1. Navigate to `https://www.uralairlines.ru/`
2. Close popup → fill "Откуда" (IATA code) → fill "Куда" (Russian city name "Стамбул") → select from dropdown
3. Click date field → navigate months → click departure date → click return date
4. Click **"ИСКАТЬ"**, wait 10-15s

Calendar JS fallback if accessibility tree misses date cells:
```js
const tds = document.querySelectorAll('td');
for (const td of tds) {
  const rect = td.getBoundingClientRect();
  if (td.textContent.trim() === '23' && rect.left > 900 && rect.width > 0) { td.click(); break; }
}
```