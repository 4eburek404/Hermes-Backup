# Extended Source Catalog — Russian Travel Industry News

Verified 2026-08-12 via curl + browser_navigate. HTTP codes from curl with UA header.

## Legend

- **Access**: curl = works with curl; browser = requires browser_navigate (Cloudflare/JS); RSS = has working RSS feed
- **Accessible**: ✅ = HTTP 200 via stated method; ⚠️ = works but with issues (paywall partial, 502 on curl but browser OK)

---

## PRIMARY TRAVEL INDUSTRY SOURCES (already in digest)

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 1 | BBT (Buying Business Travel Russia) | `https://buyingbusinesstravel.com.ru/news/` | Business travel, MICE, авиация, отели | curl | ✅ HTTP 200 |
| 2 | АТОР (Ассоциация туроператоров) | `https://www.atorus.ru/news/` | Туриндустрия, авиация, отели, MICE | browser | ✅ HTTP 200 |
| 3 | Турдом (TourDom) | `https://www.tourdom.ru/news` | Туризм, авиация, отели, туроператоры | browser + RSS | ✅ HTTP 200, RSS works: `https://www.tourdom.ru/rss/` |
| 4 | АвиаПорт | `https://www.aviaport.ru/news/` | Авиация, авиапром, аэропорты | browser | ✅ HTTP 200 |

---

## NEW SOURCES — TRAVEL INDUSTRY SPECIALIZED

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 5 | RATA News (Российский союз туриндустрии) | `https://www.ratanews.ru/` | Туриндустрия, авиарынок, отели, РСТ | browser | ✅ HTTP 200, content-rich (aviation + hotels + tourism) |
| 6 | Росcийский союз туриндустрии (РСТ) | `https://www.russiatourism.ru/news/` | Официальные новости РСТ, туриндустрия, regulation | browser + RSS | ✅ HTTP 200, RSS works: `https://www.russiatourism.ru/rss/` |
| 7 | Tourprom (Турпром) | `https://www.tourprom.ru/` | Туризм, авиакомпании, отели, направления | curl | ✅ HTTP 200 |
| 8 | Авиатранспортное обозрение (ATO.ru) | `https://www.ato.ru/` | Авиация, авиакомпании, аэропорты, авиапром | curl | ✅ HTTP 200 |
| 9 | АвиаПорт (news listing) | `https://www.aviaport.ru/news/` | Авиация (industry, airlines, airports) | browser | ✅ HTTP 200 |
| 10 | Профит.Тревел (Profi.Travel) | `http://www.profitravel.ru/` | B2B туризм, авиакомпании, отели, MICE | browser | ⚠️ Redirects to Aviasales — domain may have changed; verify before use |
| 11 | Welcome Times | `https://welcometimes.ru/` | HoReCa, отели, гостеприимство | curl | ✅ HTTP 200 |
| 12 | Hotel.report | `https://hotel.report/` | Отели, гостиничный бизнес, HoReCa | curl | ✅ HTTP 200 (HTTPS only, no www) |

---

## NEW SOURCES — AVIATION SPECIALIZED

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 13 | Авиация России | `http://www.rosaviatsia.ru/` | Росавиация (гос. регулятор) | curl (HTTP only) | ✅ HTTP 200 (HTTP only, no HTTPS) |
| 14 | AirCargo.ru | `https://www.aircargo.ru/` | Грузовая авиация, авиаперевозки | curl | ✅ HTTP 200 |
| 15 | АвиаБрокер (aex.ru) | `https://www.aex.ru/` | Авиация, аэрокосмическая промышленность | curl | ✅ HTTP 200 |
| 16 | Минтранс РФ | `https://www.mintrans.ru/news` | Транспорт, авиация, regulation | curl | ✅ HTTP 200 |

---

## NEW SOURCES — BUSINESS TRAVEL / MICE / CORPORATE

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 17 | Logistics.ru | `https://logistics.ru/` | Логистика, командировки, деловой туризм | curl | ✅ HTTP 200 |
| 18 | Smartway | `https://www.smartway.ru/` | Корпоративные поездки, командировки, travel-менеджмент | curl | ✅ HTTP 200 (small page, verify content) |
| 19 | FL-Group (Bnovo parent) | `https://www.fl-group.ru/` | Отели, гостиничные технологии | curl | ✅ HTTP 200 (small page) |

---

## NEW SOURCES — GENERAL BUSINESS / NEWS (with strong travel sections)

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 20 | Интерфакс | `https://www.interfax.ru/` + RSS: `https://www.interfax.ru/rss.asp` | Новости, авиация, туризм, транспорт | curl + RSS | ✅ HTTP 200, RSS works |
| 21 | Ведомости | `https://www.vedomosti.ru/` + RSS: `https://www.vedomosti.ru/rss/news/` | Бизнес, экономика, туризм, отели | browser + RSS | ⚠️ curl 502 (Cloudflare), browser works, RSS returns 200 |
| 22 | Эксперт | `https://expert.ru/` | Бизнес-аналитика, экономика, туризм | curl | ✅ HTTP 200 |
| 23 | Деловой Петербург (dp.ru) | `https://www.dp.ru/` | Бизнес-новости Северо-Запада, туризм | curl | ✅ HTTP 200 |
| 24 | Бизнес ФМ (BFM.ru) | `https://www.bfm.ru/` | Бизнес-новости, экономика, travel | curl | ✅ HTTP 200 |
| 25 | Состав (Sostav.ru) | `https://www.sostav.ru/` | Маркетинг, реклама, индустрия, MICE | curl | ✅ HTTP 200 |
| 26 | Клерк.Ру | `https://www.klerk.ru/` | Налоги, командировки, учёт, travel expenses | curl | ✅ HTTP 200 |
| 27 | TAdviser | `https://www.tadviser.ru/` | ИТ-технологии, бизнес-системы, travel tech | browser | ✅ browser works (curl times out) |
| 28 | Лента.ру | `https://www.lenta.ru/` + RSS: `https://www.lenta.ru/rss/` | Общие новости, aviation incidents | curl + RSS | ✅ HTTP 200, RSS works |
| 29 | RTVI | `https://www.rtvi.ru/` + RSS: `https://www.rtvi.ru/rss/` | Общие новости, экономика | curl + RSS | ✅ HTTP 200, RSS works |
| 30 | URA.news | `https://www.ura.news/` | Региональные новости, экономика | curl | ✅ HTTP 200 (rate-limited: 429 on /news/) |

---

## NEW SOURCES — REGIONAL / NICHE (with aviation/tourism coverage)

| # | Site | URL | Covers | Access | Accessible |
|---|------|-----|--------|--------|------------|
| 31 | Russian Emirates | `https://russianemirates.com/` | Новости ОАЭ, авиакомпании ОАЭ, рейсы в Россию | curl | ✅ HTTP 200 |
| 32 | MSK1 / MSK Новости | `https://www.msknovosti.ru/` | Московские новости, аэропорты, рейсы | curl | ✅ HTTP 200 |
| 33 | Gorobzor | `https://www.gorobzor.ru/` | Региональные новости, авиаинциденты, рейсы | curl | ✅ HTTP 200 |
| 34 | East Russia | `https://www.eastrussia.ru/` | Дальний Восток, авиация, туризм | curl | ✅ HTTP 200 |
| 35 | Tonkosti.ru | `https://www.tonkosti.ru/` | Туристический портал, направления, гиды | curl | ✅ HTTP 200 |
| 36 | Travel.ru | `https://www.travel.ru/` | Туризм, путешествия, новости | curl | ✅ HTTP 200 |

---

## BLOCKED / PROBLEMATIC SOURCES (do NOT use)

| Site | Issue |
|------|-------|
| Google News / Google Search | IP-blocked (sorry page) |
| Yandex News | Encoding errors (0xad byte) |
| DuckDuckGo | Returns empty/broken page |
| Travel Weekly | Cloudflare challenge (use archive.org workaround) |
| RBC.ru | Timeout from this IP (both curl and browser) |
| Bnovo.ru | 502 error (may be temporary) |
| Continent Express | 503 (likely Cloudflare) |
| IBC Corporate Travel | 503 (likely Cloudflare) |
| Mainslot88.ru | 503 (likely Cloudflare) |

---

## WORKING RSS FEEDS (verified 2026-08-12)

| Source | RSS URL | Content |
|--------|---------|---------|
| Турдом | `https://www.tourdom.ru/rss/` | Full tourism/aviation news, all categories |
| Интерфакс | `https://www.interfax.ru/rss.asp` | General news (includes aviation/transport) |
| Лента.ру | `https://www.lenta.ru/rss/` | General news |
| RTVI | `https://www.rtvi.ru/rss/` | General news |
| РСТ | `https://www.russiatourism.ru/rss/` | Tourism industry official news |
| Ведомости | `https://www.vedomosti.ru/rss/news/` | Business news (RSS works even when HTML is Cloudflare-protected) |

---

## RECOMMENDATIONS FOR AVIATION TICKET OFFICE USE

**Most relevant new sources for авиакасса:**
1. **RATA News** — aviation market + hotel + tourism industry (browser)
2. **Авиатранспортное обозрение (ATO.ru)** — pure aviation, airlines (curl)
3. **Интерфакс** — official aviation news, Росавиация announcements (curl + RSS)
4. **Росавиация (rosaviatsia.ru)** — official regulator, flight restrictions, permits (curl HTTP)
5. **Минтранс** — transport regulation, subsidies, policy (curl)
6. **АвиаПорт** — deep aviation industry (browser)
7. **Logistics.ru** — business travel, командировки (curl)
8. **Tourprom** — tourism market, airline news (curl)
9. **Russian Emirates** — UAE-Russia flights, airlines (curl)
10. **Ведомости** — business/aviation via RSS (RSS only)