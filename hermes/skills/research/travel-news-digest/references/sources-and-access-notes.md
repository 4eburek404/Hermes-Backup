# Sources & Access Notes

Session-validated notes on each source — what works, what doesn't, what to expect.

## BBT (buyingbusinesstravel.com.ru) — PRIMARY for командировки

**RSS feed (SIMPLEST method, verified 2026-08-12):** `curl -sL https://buyingbusinesstravel.com.ru/news/rss/` returns valid XML with `<title>`, `<pubDate>`, and full `<description>` for each article. Use this as the first-choice access method — faster and more reliable than HTML scraping.

**Category structure:** URL slugs use transliteration:
- `/news/trevel-menedzhment/` — travel management (командировки, GBTA, WTTC)
- `/news/aviatsiya/` — aviation
- `/news/oteli/` — hotels
- `/news/tekhnologii/` — technology
- `/news/mice/` — MICE

**URL quirks:**
- Some slugs have trailing hyphens: `syrian-airlines-vozobnovit-polyety-iz-damaska-v-moskvu-/`
- Some slugs differ from what you'd guess: `gbta-mirovye-rashody-na-delovye-poezdki-dostignut-rekordnykh-1-71-trln-v-2026-godu/` (not `...na-komandirovki...`)
- ALWAYS extract from listing page — never guess

**Content extraction regex:** Works by finding the category label + date pattern:
```python
m = re.search(r'(Тревел-менеджмент|Авиация|Отели|Технологии)\s+\d+\s+\w+\s+\d{4}', body)
```

## Travel Weekly — Cloudflare blocked, use archive.org

**Direct access:** Fails (browser + curl). Cloudflare "Just a moment..." page.
**Archive.org:** `https://web.archive.org/web/2026/https://www.travelweekly.com/Travel-News`

**Article URL pattern on archive.org:**
```
/web/20260809013848/https://www.travelweekly.com/Travel-News/Airline-News/<slug>
/web/20260809013848/https://www.travelweekly.com/Travel-News/Corporate-Travel/<slug>
```

**Key categories found:**
- `Travel-News/Airline-News/` — airlines
- `Travel-News/Corporate-Travel/` — business travel (Amex GBT, Gray Dawes, etc.)
- `Travel-News/Car-Rental-News/` — ground transport
- `Travel-News/Government/` — visa/regulation

## Simple Flying — browser snapshot works

No curl needed. `browser_navigate` to homepage gives:
- LATEST section: 6-8 recent articles with relative timestamps
- Featured: 4 articles with images
- Threads: community discussions (skip for digest)

## АТОР (atorus.ru) — browser snapshot works

Homepage `https://www.atorus.ru/news/` gives ~20 recent articles with dates.
No paginated archive at `/news/2026/08/` — 404. Use main page only.

## Турдом (tourdom.ru) — browser snapshot works

`https://www.tourdom.ru/news` gives recent articles with timestamps (e.g. "Вчера в 21:00").
Good for operational news (flight disruptions, tourist incidents).

## АвиаПорт (aviaport.ru) — browser snapshot works

`https://www.aviaport.ru/news/` gives aviation industry news.
Has tabs: "Сегодня (44)", "Вчера (80)", "2 дня назад (83)".
Good for Russian aviation industry (Аэрофлот results, Минтранс, аэропорты).

## Search engines — web UI blocked, but Google News RSS WORKS

- Google Search (web UI): "sorry" page, IP 196.240.57.34 — BLOCKED
- Google Cache: blocked
- DuckDuckGo HTML: empty page
- Yandex News: encoding error (0xad byte)

**Google News RSS WORKS** via `google_news_rss_titles.py` (in web-content-acquisition skill). This is the exception — use it for source discovery and article search:
```bash
SKILL_DIR="$HOME/AppData/Local/hermes/skills/research/web-content-acquisition"
cd "$SKILL_DIR" && python scripts/google_news_rss_titles.py --query "авиаперевозки командировки отели 2026" --limit 20
# English: --hl en --gl US --ceid US:en
```
Run 3 parallel queries (aviation, hotels, business travel) in both RU and EN for maximum source coverage.

**Do not attempt Google Search / DuckDuckGo / Yandex News web UI.** Go directly to known source URLs or use Google News RSS.

## Aviation Herald — browser_navigate ONLY (verified 2026-08-12)

`curl -sL https://avherald.com/` returns an **empty page** — the server detects non-browser clients and returns no content. `browser_navigate` works: the snapshot contains the full incident list with dates, aircraft types (B738, A320, B788, etc.), and one-line incident descriptions. No RSS feed exists.

The snapshot structure: each incident is a LayoutTable with date headers ("Tuesday Aug 11th 2026") and incident entries ("Incident United B788 near Boston on Aug 10th 2026, cracked windshield"). Extract by scanning for "Incident" / "Accident" keywords in the snapshot text.

## Broken RSS feeds (verified 2026-08-12)

| Source | RSS URL | Issue |
|--------|---------|-------|
| GBTA | `https://www.gbta.org/feed/` | Returns non-XML content (syntax error on parse) — use curl + HTML extraction |
| Коммерсантъ | `https://www.kommersant.ru/rss/` | XML mismatched tag error (line 9) — use curl + HTML extraction |
| Ведомости | `https://www.vedomosti.ru/rss/news` | RSS works (returns valid XML) despite Cloudflare on HTML pages |