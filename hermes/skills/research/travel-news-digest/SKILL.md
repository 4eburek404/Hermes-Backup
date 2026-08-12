---
name: travel-news-digest
description: "Travel news digest — flights, hotels, business trips."
---

# Travel News Digest

Aggregate travel industry news (aviation, hotels, business travel/MICE) from multiple sources into a categorized digest. The user works in an aviation ticket office (Авиакасса) and needs a multi-source briefing — NOT a single-source summary.

## Critical Rule

**Always use MULTIPLE sources.** The user explicitly rejected a single-source summary ("атор только нашенл?!"). Even if one source has good content, gather from at least 3-4 sources before compiling the digest. The user may provide specific URLs — use ALL of them.

## CLI Script — PRIMARY METHOD (0 tokens, ~4 seconds)

The `fetch_travel_news.py` script is the **primary method** for gathering and formatting the digest. It runs standalone (no LLM, no agent) and collects from all sources in `sources.yaml`.

### Quick Start

```bash
cd ~/AppData/Local/hermes/skills/research/travel-news-digest/scripts

# Full digest (fetch + process + format)
python fetch_travel_news.py all --days 7 --output markdown

# Health check all sources
python fetch_travel_news.py health

# Only P1 Russian sources
python fetch_travel_news.py all --days 7 --region ru --priority P1

# JSON output (for pipelining)
python fetch_travel_news.py all --output json

# Clear dedup cache
python fetch_travel_news.py clear-cache
```

### Commands

| Command | Description |
|---------|-------------|
| `all` | Fetch + process + format (full pipeline) |
| `fetch` | Only fetch raw data → `raw_items.json` |
| `process` | Only filter/classify from cache |
| `digest` | Only format from cache |
| `health` | Check source availability |
| `clear-cache` | Clear SQLite dedup cache |

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--days` | 7 | News from last N days |
| `--output` | markdown | `markdown` or `json` |
| `--region` | all | `ru`, `intl`, or `all` |
| `--priority` | all | `P1`, `P2`, `P3`, or `all` |

### Dependencies (must be in Hermes venv)

```bash
python -m pip install beautifulsoup4 feedparser lxml
# curl_cffi, pyyaml, jinja2 already installed
```

### Tests

```bash
cd ~/AppData/Local/hermes/skills/research/travel-news-digest
python -m pytest tests/ -v -m "not slow"   # unit tests (~0.2s)
python -m pytest tests/ -v -m slow          # integration tests (network)
```

### Configuration

Edit `scripts/sources.yaml` to add/remove sources. Each source has:
- `fetch`: `rss`, `curl_cffi`, or `google_news`
- `region`: `ru` or `intl`
- `priority`: `P1`, `P2`, `P3`
- `topics`: list of topics (`aviation`, `hotels`, `business_travel`, `mice`, `general`)
- For `rss`: `rss:` URL
- For `curl_cffi`: `impersonate:`, `selector:`, `text_min_length:`
- For `google_news`: `query:`, `hl:`, `gl:`, `ceid:`

Sources with `general` in `topics` are filtered by keyword — only items matching travel keywords are kept. Travel-specific sources (BBT, Skift, etc.) keep all items.

### Russian-language sources (primary)

| Source | URL | Access method |
|--------|-----|---------------|
| BBT (Buying Business Travel Russia) | `https://buyingbusinesstravel.com.ru/news/` | **RSS `/news/rss/` is the simplest reliable method** — curl returns valid XML with titles, dates, full descriptions. Fallback: curl listing + grep article URLs. |
| АТОР | `https://www.atorus.ru/news/` | browser_navigate — snapshot has headlines |
| Турдом | `https://www.tourdom.ru/news` | browser_navigate. RSS: `/rss/` |
| АвиаПорт | `https://www.aviaport.ru/news/` | browser_navigate. RSS: `/rss/` |
| RATA News | `https://ratanews.ru/` | curl (Next.js app). RSS: **`/rss.xml`** (NOT `/rss/` — 404!) |
| Sostav.ru | `https://www.sostav.ru/` | curl. RSS: `/rss/` |
| Клерк.Ру | `https://www.klerk.ru/` | curl. RSS: `/feed/` |
| Интерфакс | `https://www.interfax.ru/` | curl. RSS: `/rss.asp` |
| Коммерсантъ | `https://www.kommersant.ru/` | curl. **RSS `/rss/` has XML parsing errors** (mismatched tag). Use curl + HTML extraction. |
| Ведомости | `https://www.vedomosti.ru/` | curl. RSS: `/rss/news` |

### International sources

| Source | URL | Access method |
|--------|-----|---------------|
| Simple Flying | `https://simpleflying.com/` | browser_navigate — snapshot has latest headlines |
| Travel Weekly | `https://www.travelweekly.com/Travel-News` | **Cloudflare-blocked** — use archive.org workaround (see below) |
| Skift | `https://skift.com/` | curl + RSS `/feed/` — broad industry coverage |
| Skift Meetings | `https://skift.com/meetings/` | curl + RSS `/meetings/feed/` — MICE |
| FlightGlobal | `https://www.flightglobal.com/` | curl + RSS `/feed` — aviation, regulation |
| AeroTelegraph | `https://www.aerotelegraph.com/` | curl + RSS `/feed` — aviation (EN+DE) |
| The Points Guy | `https://thepointsguy.com/` | curl + RSS `/feed/` — aviation, loyalty, hotels |
| GBTA | `https://www.gbta.org/` | curl — **RSS `/feed/` is broken** (not valid XML). Use curl + HTML extraction. |
| The Company Dime | `https://www.thecompanydime.com/` | curl + RSS `/feed/` — business travel |
| 4Hoteliers | `https://www.4hoteliers.com/` | curl + RSS `/rss/` — hotels |
| ITCM | `https://www.itcm.co.uk/` | curl + RSS `/feed/` — MICE |
| MICE Talk | `https://micetalk.com/` | curl + RSS `/feed/` — MICE |
| CAPA Centre for Aviation | `https://centreforaviation.com/` | curl (HTML) — analysis, some paywalled |
| Aviation Herald | `https://avherald.com/` | **browser_navigate only** — curl returns empty page; browser snapshot has full incident list with dates |
| FlyerTalk | `https://www.flyertalk.com/` | curl + RSS — frequent-flyer community |
| One Mile at a Time | `https://onemileatatime.com/` | curl + RSS `/feed/` |
| View from the Wing | `https://viewfromthewing.com/` | curl + RSS `/feed/` |
| Cranky Flier | `https://crankyflier.com/` | curl + RSS `/feed/` |
| Airlive | `https://airlive.net/` | curl + RSS `/feed/` — breaking aviation |
| Business Traveller (UK) | `https://www.businesstraveller.com/` | curl + RSS `/feed/` |

**Full 87-source catalog with priorities (P1/P2/P3):** `C:\Users\user\travel-news-sources-final.md`
**Subagent-generated RF source list (gemma4:31b):** `C:\Users\user\rf-travel-sources-gemma.md`
**Subagent-generated international source list:** `C:\Users\user\travel-news-sources-international.md`

### Source Discovery via Google News RSS (WORKS — use this!)

Google News RSS **works** via the `web-content-acquisition` skill's script, even though Google Search web UI is blocked. This is the primary tool for discovering new sources and finding articles by topic.

```bash
SKILL_DIR="$HOME/AppData/Local/hermes/skills/research/web-content-acquisition"
cd "$SKILL_DIR" && python scripts/google_news_rss_titles.py --query "авиаперевозки командировки отели 2026" --limit 20
# English: --hl en --gl US --ceid US:en
```

Run 3 queries in parallel: aviation, hotels, business travel. Extract source domains from results to discover new sources. Then curl each source to verify accessibility.

### Sources discovered via Google News RSS (not yet in main catalog)

| Source | URL | Coverage |
|--------|-----|----------|
| RATA News | `https://ratanews.ru/` | Aviation, travel industry (Российский союз туриндустрии) |
| dp.ru (Деловой Петербург) | `https://www.dp.ru/` | Business travel, corporate news |
| Sostav.ru | `https://www.sostav.ru/` | Marketing, business travel analysis |
| Logistics.ru | `https://logistics.ru/` | Business travel, supply chain |
| Клерк.Ру | `https://klerk.ru/` | Travel expenses, tax, командировочные |
| Интерфакс | `https://interfax-russia.ru/` | Hotel industry, tourism stats |
| ura.news | `https://ura.news/` | Airport disruptions, regional aviation news |
| Фонтанка.ру | `https://www.fontanka.ru/` | St. Petersburg aviation news |
| Московская перспектива | `https://mosperspektiva.com/` | Hotel market Moscow |
| RB.ru | `https://rb.ru/` | Business travel trends |
| russianemirates.com | `https://russianemirates.com/` | UAE-Russia flights, Dubai news |
| DKNews.kz | `https://dknews.kz/` | Kazakhstan/Central Asia aviation |
| DigitalBusiness.kz | `https://digitalbusiness.kz/` | Central Asia business travel tech |
| SecPost | `https://secpost.ru/` | Travel tech security (DDoS on booking platforms) |

### Cloudflare-blocked sources — use `curl_cffi` with `impersonate='safari'` (RELIABLE)

`curl_cffi` (v0.15.0, installed) bypasses Cloudflare/Akamai TLS fingerprinting. Use `impersonate='safari'` (NOT 'chrome' — chrome often still gets 403):

```python
from curl_cffi import requests
r = requests.get("https://www.travelweekly.com/Travel-News", impersonate="safari", timeout=15)
print(r.status_code, len(r.text))  # 200, 91829
```

**Sites unlocked by curl_cffi+safari (tested 2026-08-12):**

| Source | URL | Status with curl_cffi safari |
|--------|-----|------------------------------|
| Travel Weekly | `https://www.travelweekly.com/Travel-News` | ✅ 200 — articles extractable |
| BTN (Business Travel News) | `https://www.businesstravelnews.com/` | ✅ 200 |
| PhocusWire | `https://www.phocuswire.com/` | ✅ 200 |
| Hotel News Now | `https://www.hotelnewsnow.com/` | ✅ 200 |
| Hotel Management | `https://www.hotelmanagement.net/` | ✅ 200 |
| Travel Daily News | `https://www.traveldailynews.com/` | ✅ 200 |
| Travel Pulse | `https://www.travelpulse.com/` | ✅ 200 |
| LoyaltyLobby | `https://loyaltylobby.com/` | ✅ 200 |

**Still blocked (curl_cffi doesn't help):**

| Source | Issue |
|--------|-------|
| Hospitality Net | 403 even with curl_cffi safari |
| TTG Media | 403 even with curl_cffi safari |
| TASS | 200 but anti-bot stub (servicepipe.tech) — use browser |
| S7 Airlines | 200 but anti-bot stub — use browser |
| РБК | Connection timeout (network-level) |

**Travel Weekly no longer needs archive.org** — use curl_cffi+safari directly. Much faster and gets live content.

### Blocked sources (do NOT waste time on)

| Source | Issue |
|--------|-------|
| Google Search (web UI) | IP-blocked (sorry page) — but Google News RSS WORKS |
| Google Cache | IP-blocked |
| DuckDuckGo HTML | Returns empty/broken page |
| Yandex News | Encoding errors (0xad byte) |
| Hospitality Net | 403 even with curl_cffi — use archive.org |
| TTG Media | 403 even with curl_cffi — use archive.org |

## Access Techniques

### BBT: curl + URL extraction (RELIABLE)

```bash
# Step 1: Get article URLs from the listing page
curl -sL "https://buyingbusinesstravel.com.ru/news/" | grep -oP 'href="/news/[^"]*"' | sort -u

# Step 2: Fetch each article (URLs are relative — prepend https://buyingbusinesstravel.com.ru)
for url in \
  "https://buyingbusinesstravel.com.ru/news/trevel-menedzhment/rossiyskie-kompanii-vdvoe-uvelichili-gorizont-planirovaniya-biznes-poezdok/" \
  "https://buyingbusinesstravel.com.ru/news/aviatsiya/rossiyskie-aviakompanii-sokhranili-obyemy-perevozok-na-urovne-proshlogo-goda/"; do
  echo "=== $url ==="
  curl -sL "$url" | python -c "
import sys, re, html
text = sys.stdin.read()
body = re.sub(r'<script.*?</script>', '', text, flags=re.S)
body = re.sub(r'<style.*?</style>', '', body, flags=re.S)
m = re.search(r'(Тревел-менеджмент|Авиация|Отели|Технологии)\s+\d+\s+\w+\s+\d{4}', body)
if m: body = body[m.start():]
body = re.sub(r'<[^>]+>', ' ', body)
body = html.unescape(body)
body = re.sub(r'\s+', ' ', body).strip()
print(body[:2500])
"
done
```

**Pitfall:** Do NOT guess article URLs from slugs — BBT uses transliteration with trailing hyphens on some URLs (e.g. `...-v-moskvu-/`). Always extract from the listing page first.

**Pitfall:** Some BBT article URLs from the listing may still 404. The listing page sometimes has stale links. Move on to the next one.

### Travel Weekly: curl_cffi+safari (PRIMARY) or archive.org (FALLBACK)

Travel Weekly is behind Cloudflare. `curl_cffi` with `impersonate='safari'` bypasses it (tested 2026-08-12, returns 200 with full article HTML). This is faster and gets live content. If curl_cffi fails (intermittent 403), fall back to archive.org.

**Primary — curl_cffi+safari:**
```python
from curl_cffi import requests
r = requests.get("https://www.travelweekly.com/Travel-News", impersonate="safari", timeout=15)
# 200, ~92KB HTML with article links
```

**Fallback — archive.org:**
```bash
curl -sL "https://web.archive.org/web/2026/https://www.travelweekly.com/Travel-News" | python -c "
import sys, re, html
text = sys.stdin.read()
articles = re.findall(r'<a[^>]*href=\"(/web/\d+/https://www\.travelweekly\.com/[^\"]*-News/[^\"]*)\"[^>]*>([^<]{20,})</a>', text)
seen = set()
for href, title in articles:
    title = html.unescape(title).strip()
    if title not in seen and 'Travel-News/' in href:
        seen.add(title)
        print(title)
"
```

### Simple Flying: browser snapshot (RELIABLE)

`browser_navigate` to `https://simpleflying.com/` works. The snapshot contains:
- Featured articles (with images)
- LATEST section with timestamps ("8 hours ago", "9 hours ago", etc.)
- Threads section (community discussions)

Extract headlines from the LATEST section. No need to open individual articles for a digest — headlines + first paragraph are enough.

### ATOR / Турдом / АвиаПорт: browser snapshot (RELIABLE)

Navigate to the news listing page. The snapshot contains article headlines with dates. For deeper content, click through (but note: ref IDs change after page reload — use `browser_console` with `document.querySelectorAll` to extract URLs if needed).

## Digest Format

Structure the digest as:

```
# 📰 Дайджест: перелёты, отели, командировки
**Неделя DD–DD месяц YYYY · Источники: ...**

## ✈️ ПЕРЕЛЁТЫ
### Россия
- **Headline** — summary (Source, DD.MM)
### Мир
- ...

## 🏨 ОТЕЛИ
### Россия
### Мир

## 🎫 КОМАНДИРОВКИ / БИЗНЕС-ТРЕВЕЛ

## 📌 Источники
```

### Format rules

- Each item: `**Headline** — one-sentence summary (Source, DD.MM)`
- Group by topic (✈️/🏨/🎫), then by region (Россия/Мир)
- Cite source and date for every item
- End with source links and an offer to: (1) set up a cron digest, (2) deep-dive a topic, (3) save as skill
- Language: Russian (user's working language)

## Workflow: Source Discovery for Digest

**PRIMARY method: CLI script.** Run `python scripts/fetch_travel_news.py all --days 7` first. This collects from 33+ sources in ~4 seconds (0 LLM tokens). Review the output. If the user needs deeper analysis or LLM-summaries, use the agent method below.

**FALLBACK method: manual agent collection.** For browser-only sources (АТОР) or when the script fails, use the agent method described below.

1. **Run the CLI script** (PRIMARY): `python scripts/fetch_travel_news.py all --days 7 --output markdown`
2. **Review the output** — check for missing sources, failed fetches, irrelevant items.
3. **Optional LLM summary** — if the user wants summaries, pipe JSON output to LLM: `python fetch_travel_news.py all --output json` and feed to agent.
4. **For browser-only sources** (АТОР) — use `browser_navigate` as fallback, merge results manually.
5. **If the user asks for MORE sources** — use `delegate_task` to spawn parallel subagents for source discovery.

### Hybrid parallel workflow (FASTEST, verified 2026-08-12)

Run Google News RSS queries (step 2) and `delegate_task` subagents (step 6) **in the same turn** — they are independent. While subagents fetch from BBT, АТОР, Турдом, and international RSS, you can simultaneously curl additional RSS feeds (RATA, Sostav, Интерфакс, Ведомости, Skift, FlightGlobal, TPG) yourself. This avoids idle waiting and covers ~20 sources in one round.

**Key:** `max_concurrent_children` defaults to 3 — dispatch at most 3 subagents per `delegate_task` call. If you need 4+ source groups, run the 4th group yourself in parallel terminal calls while the 3 subagents work.

## CLI Automation: fetch_travel_news.py (WORKING — 4 seconds, 0 tokens)

A standalone Python script collects, filters, and formats the digest without any LLM. Verified 2026-08-12: 33 sources, 597 items collected, 256 after filtering, 0 errors, **4 seconds**.

### Quick start

```bash
SKILL_DIR="$HOME/AppData/Local/hermes/skills/research/travel-news-digest"
cd "$SKILL_DIR/scripts"

# Full digest (markdown to stdout)
python fetch_travel_news.py all --days 7 --output markdown

# Only P1 sources, Russia
python fetch_travel_news.py all --days 7 --region ru --priority P1

# JSON output (for pipelining)
python fetch_travel_news.py all --output json

# Health check all sources
python fetch_travel_news.py health

# Clear dedup cache
python fetch_travel_news.py clear-cache
```

### Architecture (3 stages, single script)

1. **FETCH** — `asyncio` + `Semaphore(10)` parallel collection from 33 sources:
   - RSS (~15 sources): `feedparser` + `curl_cffi` for TLS-fingerprinted fetch
   - HTML (~5 sources): `curl_cffi` (impersonate=safari) + `BeautifulSoup4` selector-based extraction
   - Google News RSS (6 queries): subprocess to `google_news_rss_titles.py`
2. **PROCESS** — keyword classification (aviation/hotels/business_travel), dedup by URL + normalized title, SQLite cache (`~/.cache/travel-news/seen.db`, 30-day retention), date filtering
3. **DIGEST** — Markdown output grouped by topic (✈️/🏨/🎫) and region (🇷🇺/🌍)

### Dependencies (installed in Hermes venv)

```
curl_cffi==0.15.0  feedparser==6.0.14  beautifulsoup4==4.15.0  lxml==6.1.1  pyyaml  jinja2  httpx
```

If missing: `python -m pip install beautifulsoup4 feedparser lxml` (into Hermes venv python, NOT system python).

### Config: `scripts/sources.yaml`

YAML config with all sources, fetch type, RSS URL, CSS selectors, region, priority, topics, and keyword dictionaries for classification. Edit this file to add/remove sources.

### Cron setup (no_agent=True — 0 tokens, weekly delivery)

```python
cronjob(
    action='create',
    name='Travel News Digest',
    schedule='every monday 9am',
    script='fetch_travel_news.py all --days 7',
    no_agent=True,        # 0 tokens, script-only
    deliver='origin'       # → delivers markdown to chat
)
```

### Review findings (subagent review, 2026-08-12)

Two subagents (deepseek-v4-flash:0731, gemma4:31b) reviewed the plan. Key findings addressed:
- ✅ **Dependencies**: bs4/feedparser/lxml were missing → installed in Hermes venv
- ✅ **Dedup state**: SQLite cache added (`seen.db`) — prevents duplicate items across runs
- ✅ **Retry**: 3 retries with exponential backoff for curl_cffi (Travel Weekly instability)
- ✅ **Failed sources report**: `⚠️ Failed Sources` section appended to digest
- ✅ **Rate limit**: `Semaphore(10)` limits concurrent requests
- ✅ **Content filtering**: General news sources (Коммерсантъ, Интерфакс, Lenta) filtered by keyword match — items without travel keywords are dropped

### Files

- `scripts/fetch_travel_news.py` — **main script** (~550 lines, standalone, 0 LLM tokens)
- `scripts/sources.yaml` — source config (33 sources, keyword dictionaries)

### Reference Files

- `references/curl-cffi-cloudflare-bypass.md` — **curl_cffi+safari technique** for bypassing Cloudflare/Akamai TLS fingerprinting. Site-specific results, retry pattern, comparison with archive.org.
- `references/cli-automation-plan.md` — **CLI automation architecture** (fetch_travel_news.py, 3-stage pipeline, cron integration)
- `references/subagent-review-results.md` — **subagent review of CLI plan** (deepseek + gemma findings, fixes applied, rating 6→7.5/10)
- `references/sources-and-access-notes.md` — session-validated access notes per source (URL patterns, quirks, regex, what's blocked)
- `references/source-catalog-extended.md` — full catalog of 30+ verified sources (aviation, hotels, business travel, MICE, general news) with access methods and RSS feeds, verified 2026-08-12
- `references/expanded-source-catalog.md` — expanded source catalog (14+ RU sources, 12+ international) with access methods and pitfalls
- `references/subagent-model-config.md` — delegate_task model configuration, available Ollama Cloud models, subagent cancellation limits
- `references/source-catalog-87.md` — **comprehensive 87-source catalog** (31 RU + 56 international) compiled from 4 parallel subagents + manual curl/RSS verification. Includes RSS paths, access status, recommended Top-20. Verified 2026-08-12.
- `templates/sources.yaml` — **YAML config template** for fetch_travel_news.py with all sources, topics, keywords for classification

## Pitfalls

1. **Never single-source.** Even if one source is comprehensive, the user wants multiple perspectives. The user explicitly rejected a single-source summary ("атор только нашенл?!").
2. **Don't guess article URLs.** Extract from listing pages. BBT transliteration is unpredictable. Many Russian news sites use non-obvious URL patterns — 404 is common when guessing.
3. **Google News RSS WORKS** (via `google_news_rss_titles.py` script) even though Google Search web UI is blocked. Use it for source discovery and article search. Run from the script's directory: `cd "$SKILL_DIR" && python scripts/google_news_rss_titles.py --query "..."`.
4. **Load `web-content-acquisition` skill FIRST.** The user explicitly asked for it — it contains the RSS script, article extraction CLI, and curl fallback pipeline. Don't try to extract articles without it.
5. **Travel Weekly Cloudflare is unsolvable.** Don't click the "I'm human" checkbox repeatedly — it loops. Use archive.org.
6. **browser_click ref IDs expire** after any `browser_navigate` call. Don't reuse ref IDs from a previous page — take a fresh snapshot or use `browser_console` to extract links.
7. **The user works in aviation ticketing.** BBT (business travel) is the most relevant source for командировки. Simple Flying and Travel Weekly cover international aviation. АТОР/Турдом cover Russian leisure tourism.
8. **User wants LOTS of sources.** "нужно больше сайтов" — when the user asks for more, use `delegate_task` to spawn parallel subagents for source discovery. The user may ask for multiple rounds with swapped roles.
9. **Subagent task formulation: NARROW tasks succeed, BROAD tasks timeout.** "Find and test 15 sources" → 600s timeout (both deepseek and gemma). "curl these 15 specific URLs and report HTTP status" → 153s success (deepseek). Always provide explicit URL lists, curl command templates, and output format. Cap at ~25 curl calls per subagent. Set `delegation.child_timeout_seconds` to 300 max. Do NOT let subagents "explore" — give them a checklist.
10. **Subagent model switching.** Set `delegation.model` in config.yaml BEFORE dispatching. `hermes config set delegation.model "deepseek-v4-flash:0731"` then dispatch, then switch to next model for the second subagent. Cannot set per-task — it's global.
11. **Subagent review pattern.** To review a plan: dispatch one subagent as "technical reviewer" with the plan in the goal. Give explicit review criteria (find weaknesses, suggest improvements, rate 1-10). Keep the prompt under 500 words to avoid long generation times. gemma4:31b completed in 11s; deepseek-v4-flash:0731 interrupted at 540s (long generation).
9. **URL guessing from Google News RSS titles fails.** Russian sites (dp.ru, Sostav.ru, Logistics.ru) have unpredictable URL patterns. Don't construct URLs from article titles — use site search (`?s=`) or extract from the RSS `<description>` links.
10. **RATA News RSS is at `/rss.xml`, NOT `/rss/`.** The `/rss/` path returns 404. RATA News is a Next.js app — the RSS feed is declared in the HTML `<link rel="alternate" type="application/rss+xml" href="https://ratanews.ru/rss.xml">`.
11. **delegate_task inherits the parent model.** There is NO per-task model override parameter. All subagents run on the same model as the parent session. To use different models, set `delegation.model` / `delegation.provider` in config.yaml (global, affects ALL subagents). The user may ask for specific models (e.g. "deepseek-v4-flash:0731 + codex 5.6 luna high") — check `delegation.model` config and available models on the provider before promising.
12. **delegate_task cannot be cancelled.** Once dispatched, background subagents run to completion (or timeout). You cannot stop a running delegation — just ignore its results. Don't dispatch duplicate tasks hoping to replace running ones.
13. **РФ source-discovery subagents timeout at 600s.** Two independent РФ-source-discovery subagents both timed out (600s, 11-21 API calls). The task is too heavy for a single leaf agent — it involves Google News RSS queries + curl-testing 15+ URLs + content extraction. Split into smaller tasks (e.g. "test these 5 specific URLs" instead of "find and test 15 sources") or increase `delegation.child_timeout_seconds` in config.
14. **Ollama Cloud available models (2026-08-12):** `deepseek-v4-flash:0731`, `deepseek-v4-pro`, `glm-5.1`, `glm-5.2`, `kimi-k2.6`, `kimi-k2.7-code`, `kimi-k3`, `nemotron-3-ultra`, `nemotron-3-super`, `nemotron-3-nano:30b`, `minimax-m2.7`, `minimax-m3`, `mistral-large-3:675b`, `qwen3.5:397b`, `gpt-oss:20b`, `gpt-oss:120b`. Check with: `curl -s "https://ollama.com/v1/models" -H "Authorization: Bearer $OLLAMA_API_KEY" | python -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]"`.
15. **OpenAI models (e.g. "codex 5.6 luna high") require a separate provider.** Ollama Cloud does not serve OpenAI models. To use OpenAI models for subagents: (1) add `OPENAI_API_KEY` to `.env`, (2) add an `openai` provider block in `config.yaml` under `providers:`, (3) set `delegation.model` and `delegation.provider` to the OpenAI model/provider. Without an API key, only Ollama Cloud models are available.
16. **bs4/feedparser/lxml must be installed in Hermes venv.** `pip install` from system Python won't work — use `python -m pip install beautifulsoup4 feedparser lxml` (python = Hermes venv python). The CLI script imports these at module level — missing deps = ImportError.
17. **curl_cffi+safari is unstable for some sites.** Travel Weekly sometimes returns 403 even with `impersonate='safari'`. The script has 3x retry with exponential backoff, but if all retries fail, the source is listed in "⚠️ Failed Sources" section of the digest.
18. **General news sources (Коммерсантъ, Интерфакс, Lenta, Ведомости) are filtered by keywords.** Items from sources with `general` in their `topics` config are DROPPED unless they match travel keywords (авиа, отель, командир, airline, hotel, etc.). This prevents politics/war/celebrity news from polluting the digest.
19. **SQLite dedup cache at ~/.cache/travel-news/seen.db.** The script marks URLs as seen and skips them on future runs. Clear with `python fetch_travel_news.py clear-cache`. Cache retains entries for 30 days.
20. **format_markdown assigns each item to ONE topic only.** If a title matches both aviation and hotels keywords, it's assigned to the first match (aviation). This prevents duplicates across sections in the digest.
21. **Tests use tmp_path for SQLite isolation.** conftest.py monkeypatches SEEN_DB to tmp_path, so tests don't pollute the real ~/.cache/travel-news/seen.db. Integration tests are marked `@pytest.mark.slow` and excluded by default (`-m "not slow"`).
16. **delegate_task `max_concurrent_children` defaults to 3.** Dispatching 4+ tasks in one call fails with "Too many tasks". Either split across multiple `delegate_task` calls, reduce task count to 3, or increase `delegation.max_concurrent_children` in config.yaml. Plan subagent tasks in batches of ≤3.
17. **Aviation Herald requires browser_navigate, NOT curl.** `curl -sL https://avherald.com/` returns an empty page (server-side rendering detection). `browser_navigate` works — the snapshot contains the full incident list with dates, aircraft types, and incident descriptions. No RSS feed available.
18. **BBT RSS feed is the simplest access method.** `curl -sL https://buyingbusinesstravel.com.ru/news/rss/` returns valid XML with titles, dates, and full article descriptions. This is faster and more reliable than the curl+grep listing approach documented in the BBT access technique section. Use RSS first; fall back to listing+curl only if you need the full article body beyond the RSS description.
19. **GBTA RSS (`/feed/`) and Коммерсантъ RSS (`/rss/`) are broken.** GBTA returns non-XML content (syntax error on parse). Коммерсантъ returns XML with mismatched tags. Do not rely on these RSS feeds — use curl + HTML extraction or browser_navigate instead.