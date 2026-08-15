# Expanded Source Catalog

Sources discovered and validated during session 2026-08-12. Organized by category and access method.

## Russian-language sources — Aviation

| Source | URL | Access | Notes |
|--------|-----|-------|-------|
| АвиаПорт | `https://www.aviaport.ru/news/` | browser_navigate | Tabs: Сегодня/Вчера/2 дня назад. Good for Аэрофлот results, Минтранс, аэропорты. |
| RATA News | `https://ratanews.ru/` | curl | Российский союз туриндустрии. Aviation + travel industry. URL patterns unpredictable — use site search. |
| ura.news | `https://ura.news/` | curl | Regional aviation news, airport disruptions (Екатеринбург, Кольцово). Good for operational disruptions. |
| Фонтанка.ру | `https://www.fontanka.ru/` | curl | St. Petersburg aviation news (Пулково). |
| russianemirates.com | `https://russianemirates.com/` | curl | UAE-Russia flights, Dubai airline news. |

## Russian-language sources — Hotels

| Source | URL | Access | Notes |
|--------|-----|-------|-------|
| Московская перспектива | `https://mosperspektiva.com/` | curl (TLS issues) | Hotel market Moscow. May need browser fallback — SSL handshake timeouts on curl. |
| Интерфакс | `https://interfax-russia.ru/` | curl (empty responses) | Hotel industry stats, tourism numbers. Curl sometimes returns empty — try browser. |
| ГАРАНТ | `https://garant.ru/` | curl | Legal/regulatory changes for hotel booking rules. |

## Russian-language sources — Business Travel / MICE

| Source | URL | Access | Notes |
|--------|-----|-------|-------|
| BBT | `https://buyingbusinesstravel.com.ru/news/` | curl (RELIABLE) | PRIMARY for командировки. See SKILL.md for extraction regex. |
| dp.ru | `https://www.dp.ru/` | curl (404 on guessed URLs) | Деловой Петербург. Business travel, corporate news. URLs unpredictable — use site search. |
| Sostav.ru | `https://www.sostav.ru/` | curl (404 on guessed URLs) | Marketing + business travel analysis. URLs unpredictable. |
| Logistics.ru | `https://logistics.ru/` | curl (404 on guessed URLs) | Business travel + supply chain. Drupal-based, URL patterns non-obvious. |
| Клерк.Ру | `https://klerk.ru/` | curl | Travel expenses, tax, командировочные правила. Good for regulatory changes. |
| RB.ru | `https://rb.ru/` | curl | Business travel trends, bleisure (командировка+отдых). |
| DKNews.kz | `https://dknews.kz/` | curl | Kazakhstan/Central Asia aviation + business travel. |
| DigitalBusiness.kz | `https://digitalbusiness.kz/` | curl | Central Asia business travel tech, AI agents for командировки. |

## Russian-language sources — Travel Tech / Security

| Source | URL | Access | Notes |
|--------|-----|-------|-------|
| SecPost | `https://secpost.ru/` | curl | Travel tech security (e.g. DDoS on hotel booking platforms). |

## International sources — Aviation

| Source | URL | Access | Notes |
|--------|-----|-------|-------|
| Simple Flying | `https://simpleflying.com/` | browser_navigate (RELIABLE) | LATEST section with timestamps. Good for global airline news. |
| Travel Weekly | `https://www.travelweekly.com/Travel-News` | archive.org ONLY | Cloudflare blocks browser + curl. Use `https://web.archive.org/web/2026/https://www.travelweekly.com/Travel-News`. Categories: Airline-News, Corporate-Travel, Car-Rental-News, Government. |

## International sources — Hotels / Business Travel

Discovered via Google News RSS `hl=en` (not yet fully validated for accessibility):

| Source | URL | Coverage |
|--------|-----|----------|
| Skift | `https://skift.com/` | Travel industry analysis |
| PhocusWire | `https://phocuswire.com/` | Travel technology |
| Business Travel News (BTN) | `https://www.businesstravelnews.com/` | Corporate travel |
| Hotel Management | `https://www.hotelmanagement.net/` | Hotel industry |
| Travel Daily Media | `https://www.traveldailymedia.com/` | Global travel news |
| GBTA | `https://www.gbta.org/` | Business travel association |
| CAPA Centre for Aviation | `https://centreforaviation.com/` | Aviation analysis |
| FlightGlobal | `https://www.flightglobal.com/` | Aviation industry |
| The Points Guy | `https://thepointsguy.com/` | Consumer aviation |
| CNBC Travel | `https://www.cnbc.com/travel/` | Business travel economy |
| Reuters Travel | `https://www.reuters.com/world/travel/` | Global travel news |
| NerdWallet Travel | `https://www.nerdwallet.com/travel` | Travel inflation, costs |

## Key Insight: URL Guessing Fails for Russian News Sites

Most Russian news sites (dp.ru, Sostav.ru, Logistics.ru, Интерфакс, RATA News) have unpredictable URL patterns. Constructing URLs from article titles DOES NOT WORK — results in 404. Instead:

1. Use Google News RSS to find the article title + source domain.
2. Use site search: `https://<domain>/?s=<query>` or `https://<domain>/search?q=<query>`.
3. Parse the RSS `<description>` field — it often contains direct links to the article on the publisher's site.
4. For BBT specifically: extract URLs from the listing page via `grep -oP 'href="/news/[^"]*"'`.

## Subagent Delegation Pattern for Source Discovery

The user may ask for more sources ("нужно больше сайтов"). Use `delegate_task` with parallel subagents:

- One subagent for Russian-language sources (aviation, hotels, business travel)
- One subagent for international/English sources
- The user may ask to "swap roles" and run again — dispatch a second pair with the same goals
- Wait for ALL subagents to complete, then merge into a single unified list
- Each subagent should verify accessibility (curl test) and note Cloudflare/paywall issues