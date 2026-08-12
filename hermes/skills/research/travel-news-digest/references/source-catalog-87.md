# Source Catalog: 87 Sources (Verified 2026-08-12)

Compiled from 4 parallel subagents + manual curl/RSS verification.

Legend: ✅200 = curl accessible | ⚠️403 = Cloudflare (use archive.org) | ❌000 = DNS/timeout | RSS = feed available

---

## 🇷🇺 Russian-Language Sources (31)

### Tourism / Industry (broad)

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 1 | BBT (Buying Business Travel Russia) | `https://buyingbusinesstravel.com.ru/news/` | Командировки, MICE, авиация, отели | ✅ curl | ✅ `/news/rss/` |
| 2 | АТОР | `https://www.atorus.ru/news/` | Турбизнес, авиация, отели | ✅ browser | ❌ |
| 3 | Турдом | `https://www.tourdom.ru/news` | Турбизнес, опер. новости | ✅ browser | ✅ `/rss/` |
| 4 | АвиаПорт | `https://www.aviaport.ru/news/` | Авиация, аэропорты | ✅ browser | ✅ `/rss/` |
| 5 | RATA News | `https://ratanews.ru/` | Турбизнес, авиация, отели | ✅ curl (Next.js) | ✅ `/rss.xml` (NOT `/rss/` — 404) |
| 6 | Турпром | `https://tourprom.ru/` | Турбизнес, новости | ✅ curl | ❌ (find) |
| 7 | Московская перспектива | `https://mosperspektiva.com/` | Гостиницы, городские новости | ⚠️ timeout | ❌ |

### Aviation

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 8 | Уральские авиалинии | `https://www.uralairlines.ru/` | Авиакомпания | ✅ curl | ❌ |
| 9 | Аэрофлот | `https://www.aeroflot.ru/` | Авиакомпания | ⚠️ 503 | ❌ |
| 10 | S7 Airlines | `https://www.s7.ru/` | Авиакомпания | ⚠️ 403 | ❌ |

### Hotels / Booking

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 11 | Ostrovok | `https://www.ostrovok.ru/` | Бронирование отелей | ✅ curl | ❌ |
| 12 | Bronevik | `https://bronevik.com/` | Бронирование отелей | ✅ curl | ❌ |
| 13 | Суточно.ру | `https://www.sutochno.ru/` | Аренда жилья | ✅ curl | ❌ |
| 14 | TopHotels | `https://www.tophotels.ru/` | Отзывы об отелях | ✅ curl | ❌ |
| 15 | Travel.ru | `https://www.travel.ru/` | Турбизнес, путешествия | ✅ curl | ❌ |

### Business / MICE

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 16 | Sostav.ru | `https://www.sostav.ru/` | Маркетинг, командировки | ✅ curl | ✅ `/rss/` |
| 17 | Деловой Петербург (dp.ru) | `https://dp.ru/` | Бизнес, командировки | ✅ curl | ❌ |
| 18 | Logistics.ru | `https://logistics.ru/` | Логистика, деловой туризм | ✅ curl | ❌ |
| 19 | Клерк.Ру | `https://www.klerk.ru/` | Налоги, командировочные | ✅ curl | ✅ `/feed/` |
| 20 | Event-Industry.ru | `https://www.event-industry.ru/` | MICE, мероприятия | ✅ curl | ❌ |
| 21 | Horeca.ru | `https://www.horeca.ru/` | HoReCa, гостиницы | ✅ curl | ❌ |

### General Business Media

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 22 | Интерфакс | `https://www.interfax.ru/` | Новости, авиация, турбизнес | ✅ curl | ✅ `/rss.asp` |
| 23 | Коммерсантъ | `https://www.kommersant.ru/` | Бизнес, авиация, отели | ✅ curl | ✅ `/rss/` |
| 24 | Ведомости | `https://www.vedomosti.ru/` | Бизнес, экономика | ✅ curl | ✅ `/rss/news` |
| 25 | ТАСС | `https://tass.ru/` | Новости | ⚠️ 403 | ✅ (browser) |

### Transport

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 26 | РЖД | `https://www.rzd.ru/` | Ж/д, транспорт | ✅ curl | ❌ |
| 27 | Aviasales | `https://www.aviasales.ru/` | Авиабилеты, тренды | ✅ curl | ❌ |

### Google News RSS (RU meta-aggregator)

| # | Query | Topics |
|---|-------|-------|
| 28 | `"авиаперевозки командировки отели 2026"` | All |
| 29 | `"авиакомпании рейсы аэропорт 2026"` | Aviation |
| 30 | `"отели гостиницы бронирование 2026"` | Hotels |
| 31 | `"командировки деловой туризм 2026"` | Business travel |

---

## 🌍 International / English Sources (56)

### Aviation — RSS accessible (Tier 1)

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 32 | Simple Flying | `https://simpleflying.com/` | Aviation, airlines | ✅ browser | ✅ `/feed/` |
| 33 | Skift | `https://skift.com/` | All industry, business travel | ✅ curl | ✅ `/feed/` |
| 34 | Skift Meetings | `https://skift.com/meetings/` | MICE | ✅ curl | ✅ `/meetings/feed/` |
| 35 | FlightGlobal | `https://www.flightglobal.com/` | Aviation, regulation, fleets | ✅ curl | ✅ `/feed` |
| 36 | AeroTelegraph | `https://www.aerotelegraph.com/` | Aviation (EN+DE) | ✅ curl | ✅ `/feed` |
| 37 | The Points Guy | `https://thepointsguy.com/` | Aviation, loyalty, hotels | ✅ curl | ✅ `/feed/` |
| 38 | FlyerTalk | `https://www.flyertalk.com/` | Forum, loyalty | ✅ curl | ✅ `/forum/external.php?type=RSS2` |
| 39 | One Mile at a Time | `https://onemileatatime.com/` | Aviation, loyalty | ✅ curl | ✅ `/feed/` |
| 40 | View from the Wing | `https://viewfromthewing.com/` | Aviation, analysis | ✅ curl | ✅ `/feed/` |
| 41 | Live and Let's Fly | `https://liveandletsfly.com/` | Aviation, reviews | ✅ curl | ✅ `/feed/` |
| 42 | God Save The Points | `https://godsavethepoints.com/` | Aviation, loyalty | ✅ curl | ✅ `/feed/` |
| 43 | Cranky Flier | `https://crankyflier.com/` | Aviation, ops analysis | ✅ curl | ✅ `/feed/` |
| 44 | Runway Girl Network | `https://runwaygirlnetwork.com/` | Cabin, IFE, passenger experience | ✅ curl | ✅ `/feed/` |
| 45 | Paddle Your Own Kanoo | `https://paddleyourownkanoo.com/` | Aviation (irreverent) | ✅ curl | ✅ `/feed/` |
| 46 | SamChui | `https://samchui.com/` | Aviation, luxury | ✅ curl | ✅ `/feed/` |
| 47 | AeroTime Hub | `https://www.aerotime.aero/` | Aviation, industry | ✅ curl | ✅ `/feed` |
| 48 | Airline Reporter | `https://www.airlinereporter.com/` | Aviation, reviews | ✅ curl | ✅ `/feed/` |
| 49 | Travel Codex | `https://travelcodex.com/` | Loyalty, aviation, hotels | ✅ curl | ✅ `/feed/` |
| 50 | Airlive | `https://airlive.net/` | Aviation, incidents, real-time | ✅ curl | ✅ `/feed/` |
| 51 | Leeham News | `https://leehamnews.com/` | Aviation, fleet, analysis | ✅ curl | ✅ `/feed/` |
| 52 | Business Traveller (UK) | `https://www.businesstraveller.com/` | Business travel, reviews | ✅ curl | ✅ `/feed/` |

### Aviation — HTML only (Tier 2, no RSS)

| # | Site | URL | Topics | Access |
|---|------|-----|-------|--------|
| 53 | CAPA Centre for Aviation | `https://centreforaviation.com/` | Analysis, regulation | ✅ curl (HTML) |
| 54 | Routes Online | `https://www.routesonline.com/` | Route development | ✅ curl (homepage) |
| 55 | Airways Magazine | `https://airwaysmag.com/` | Aviation, fleets | ✅ curl (HTML) |
| 56 | Aviation Week | `https://aviationweek.com/` | Aviation, regulation | ✅ curl (paywall) |
| 57 | Aviation Herald | `https://avherald.com/` | Incidents, safety | ✅ curl |
| 58 | Airline Ratings | `https://www.airlineratings.com/` | Safety, reviews | ✅ curl |
| 59 | Aero-Mag | `https://www.aero-mag.com/` | Aviation tech | ✅ curl |
| 60 | Breaking Travel News | `https://www.breakingtravelnews.com/` | General travel trade | ✅ curl |
| 61 | Travolution | `https://www.travolution.com/` | Travel tech | ✅ curl |

### Hotels / Hospitality

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 62 | 4Hoteliers | `https://www.4hoteliers.com/` | Hotels, hospitality | ✅ curl | ✅ `/rss/` |
| 63 | Hotel News Resource | `https://www.hotelnewsresource.com/` | Hotels | ✅ curl | ❌ |
| 64 | Hotel News Now (CoStar) | `https://www.hotelnewsnow.com/` | Hotels, market | ⚠️ 403 (archive.org) | ❌ |
| 65 | Hotel Management | `https://www.hotelmanagement.net/` | Hotels | ⚠️ 403 (archive.org) | ❌ |
| 66 | Hospitality Net | `https://www.hospitalitynet.org/` | Hotels, aggregator | ⚠️ 403 (archive.org) | ❌ |

### Business Travel / Corporate / MICE

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 67 | GBTA | `https://www.gbta.org/` | Business travel, regulation | ✅ curl | ✅ `/feed/` |
| 68 | The Company Dime | `https://www.thecompanydime.com/` | Business travel | ✅ curl | ✅ `/feed/` |
| 69 | ITCM | `https://www.itcm.co.uk/` | MICE, incentive travel | ✅ curl | ✅ `/feed/` |
| 70 | MICE Talk | `https://micetalk.com/` | MICE | ✅ curl | ✅ `/feed/` |
| 71 | Corporate Travel Community | `https://www.corporatetravelcommunity.com/` | Corporate travel, TMC | ⚠️ timeout | ❌ |
| 72 | BTN (Business Travel News) | `https://www.businesstravelnews.com/` | Corporate travel, TMC | ⚠️ 403 (archive.org) | ❌ |
| 73 | Travel Mole | `https://travelmole.com/` | Travel trade | ✅ curl | ✅ `/feed/` |
| 74 | Corporate Livewire | `https://www.corporatelivewire.com/` | Corporate, business travel | ✅ curl | ❌ |

### Travel Technology

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 75 | Travel Tech News | `https://traveltechnews.com/` | Travel tech, GDS | ✅ curl | ✅ `/feed/` |
| 76 | PhocusWire | `https://www.phocuswire.com/` | Travel tech | ⚠️ 403 (archive.org) | ❌ |

### Regional / General

| # | Site | URL | Topics | Access | RSS |
|---|------|-----|-------|--------|-----|
| 77 | TTG Asia | `https://www.ttgasia.com/` | Travel trade, APAC | ✅ curl | ✅ `/feed/` |
| 78 | Travel Weekly US | `https://www.travelweekly.com/` | General travel | ⚠️ 403 (archive.org) | ❌ |
| 79 | Travel Pulse | `https://www.travelpulse.com/` | General travel | ⚠️ 403 | ❌ |
| 80 | Travel Daily News | `https://www.traveldailynews.com/` | General travel | ⚠️ 403 (archive.org) | ❌ |
| 81 | TTG Media | `https://www.ttgmedia.com/` | Travel trade, UK | ⚠️ 403 (archive.org) | ❌ |
| 82 | LoyaltyLobby | `https://loyaltylobby.com/` | Loyalty, hotels | ⚠️ 403 (archive.org) | ❌ |

### Google News RSS (EN meta-aggregator)

| # | Query | Topics |
|---|-------|-------|
| 83 | `"aviation airline industry news"` | Aviation |
| 84 | `"hotel hospitality industry news"` | Hotels |
| 85 | `"business travel corporate travel news"` | Business travel |
| 86 | `"MICE meetings incentive travel news"` | MICE |
| 87 | `"travel technology GDS booking news"` | Travel tech |

---

## ❌ Dead / Inaccessible (do NOT attempt)

| Site | URL | Reason |
|------|-----|--------|
| Buying Business Travel UK | `buyingbusinesstravel.com` | DNS fail (use .ru version) |
| Business Traveler | `businesstraveler.com` | DNS fail |
| BTN Online (Europe) | `btnonline.com` | DNS fail |
| Travel Weekly Asia | `travelweeklyasia.com` | DNS fail |
| Travel Daily UK | `traveldailyuk.com` | DNS fail |
| MICE Review | `micereview.com` | DNS fail |
| Air Transport News | `airtransportnews.com` | DNS fail |
| Procurement.travel | `procurement.travel` | 530 FTP error |
| Airline Geeks | `theairlinegeeks.com` | Timeout (try browser) |
| anna.aero | `anna.aero` | Timeout (try browser) |
| Pax International | `pax-international.com` | Timeout |

---

## Recommended Top 20 for Digest

### РФ (10)
1. BBT — командировки, MICE (curl + RSS)
2. АТОР — турбизнес (browser)
3. Турдом — опер. новости (browser + RSS)
4. АвиаПорт — авиация (browser + RSS)
5. RATA News — турбизнес (curl + RSS `/rss.xml`)
6. Интерфакс — деловые новости (curl + RSS)
7. Коммерсантъ — бизнес (curl + RSS)
8. Sostav.ru — маркетинг/бизнес (curl + RSS)
9. Клерк.Ру — командировочные расходы (curl + RSS)
10. Google News RSS (RU) — мета-поиск

### International (10)
11. Skift — вся индустрия (curl + RSS)
12. Simple Flying — авиация (browser + RSS)
13. FlightGlobal — авиация (curl + RSS)
14. The Points Guy — авиация, лояльность (curl + RSS)
15. AeroTelegraph — авиация (curl + RSS)
16. GBTA — business travel (curl + RSS)
17. The Company Dime — business travel (curl + RSS)
18. 4Hoteliers — отели (curl + RSS)
19. Travel Weekly — общий travel (archive.org)
20. Google News RSS (EN) — мета-поиск