# CLI Automation Plan: fetch_travel_news.py

Standalone Python-скрипт для автоматизации сбора travel-news дайджеста без LLM-агента.

## Architecture

```
┌─────────┐    ┌──────────┐    ┌─────────┐
│  FETCH  │───▶│ PROCESS  │───▶│ DIGEST  │
│ (сбор)  │    │(фильтр)  │    │(формат) │
└─────────┘    └──────────┘    └─────────┘
  ~30 sec        ~1 sec          ~1 sec
```

### Stage 1 — FETCH

Three fetcher types, all run in parallel (asyncio + curl_cffi.AsyncSession):

| Type | Method | Count | Example sources |
|------|--------|-------|-----------------|
| RSS | `curl` → `xml.etree` → title+link+date+description | ~15 | BBT, RATA, Коммерсантъ, Skift, FlightGlobal |
| HTML | `curl_cffi` (impersonate=safari) → BeautifulSoup → headlines | ~20 | Travel Weekly, BTN, PhocusWire, Hotel Management |
| Google News RSS | `google_news_rss_titles.py` subprocess | 8 queries | 4 RU + 4 EN by topic |

### Stage 2 — PROCESS

Pure Python, no LLM:
- **Keyword filter** — discard irrelevant (keywords: авиа/рейс/отель/командир/airline/hotel/business travel/...)
- **Classify** by topic: ✈️ aviation / 🏨 hotels / 🎫 business travel
- **Classify** by region: 🇷🇺 RU / 🌍 intl (from config or domain)
- **Deduplicate** — normalized title hash + URL
- **Sort** by date (newest first)
- **Limit** — top-N within `--days` window (default 7)

### Stage 3 — DIGEST

Jinja2 template → Markdown per skill format:

```markdown
# 📰 Дайджест: перелёты, отели, командировки
**Неделя DD–DD месяц YYYY · Источники: N**

## ✈️ ПЕРЕЛЁТЫ
### Россия
- **Headline** — description (Source, DD.MM)
### Мир

## 🏨 ОТЕЛИ
### Россия
### Мир

## 🎫 КОМАНДИРОВКИ / БИЗНЕС-ТРЕВЕЛ

## 📌 Источники
```

## CLI

```bash
# Full pipeline: fetch + process + digest
python fetch_travel_news.py all --days 7 --output markdown

# Only RU, only P1 sources
python fetch_travel_news.py all --days 7 --region ru --priority P1 --output json

# With optional LLM summarization of top-20
python fetch_travel_news.py all --summarize --top 20
```

## Cron automation

```python
cronjob(
    action='create',
    name='Travel News Digest',
    schedule='every monday 9am',
    script='fetch_travel_news.py all --days 7',
    no_agent=True,       # 0 tokens, script-only
    deliver='origin'     # → current chat
)
```

## Two modes

| Mode | no_agent | Tokens | Time | Quality |
|------|----------|--------|------|---------|
| Free | True | 0 | ~30s | Headlines + RSS description |
| LLM | False | ~5K | ~2min | LLM-summarized top-20 |

## Dependencies

- `curl_cffi` (v0.15.0) — Cloudflare bypass via TLS fingerprint
- `beautifulsoup4` — HTML parsing
- `feedparser` or `xml.etree` — RSS parsing
- `pyyaml` — config loading
- `jinja2` — markdown templating

## Key design decisions

1. **RSS-first** — sources with RSS are preferred (faster, more reliable, structured)
2. **curl_cffi safari** — for Cloudflare-blocked sites (Travel Weekly, BTN, PhocusWire, etc.)
3. **Google News RSS** — fills gaps, discovers new sources
4. **Cache** in `~/.cache/travel-news/` — avoid redundant fetches
5. **Standalone** — script works without agent, no LLM required for basic mode
6. **sources.yaml** — static config, edited manually (see template: `templates/sources.yaml.template`)

## Review findings (deepseek-v4-flash:0731 + gemma4:31b)

Pending — subagent reviews were dispatched but not yet received. Update this section with review findings.