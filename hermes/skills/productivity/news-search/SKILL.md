---
name: news-search
description: "Search and summarize news from Russian and international sources. Direct curl/RSS approach — do NOT delegate to subagents."
version: 1.1.0
author: nous
license: MIT
metadata:
  hermes:
    tags: [news, search, rss, web-search, searxng]
---

# News Search

Fetch, filter, and summarize Russian and international news for Konstantin.

## Core Principle

**Search news yourself directly.** Do NOT use `delegate_task` for news search — Konstantin explicitly corrected this: «Не надо делегировать, ищи сам». Always use terminal curl + python parsing yourself. Delegate_task is for coding tasks, not for search queries.

## Current-Date and Grounding Contract

News is inherently time-sensitive. Before producing a news/search answer:

1. **Current date first.** Check the current date/time with a tool (`date -Iseconds` or equivalent) and use it to interpret freshness, time zones, and stale stories. Do not answer current-news questions from stale training-memory.
2. **Save source artifacts.** Every specific headline, URL, RSS item, search result, or API-backed claim used in the final answer should have a saved artifact in the current workspace or a temporary task directory:
   ```text
   ./api_responses/news_<query_slug>_<YYYY-MM-DD>.xml|json
   ./extracts/<publisher>_<article_slug_or_hash>.md
   ./queries/news_<query_slug>_<YYYY-MM-DD>.txt
   ```
   If the answer is a quick one-off digest and no persistent artifact is created, state that grounding is from current tool output only and do not present it as archived/auditable; if no current tool output or artifact backs a claim, label it ungrounded.
3. **URL is not proof.** A Google News redirect, search-result URL, or article URL string is not enough. If a claim matters, extract the direct publisher source or save the RSS/API response that contained it.
4. **Multi-source or high-stakes news/research.** For comparisons, decisions, conflict-sensitive topics, or multi-step research, write `plan.md → notes.md → report.md` plus source artifacts. For simple headline lookup, do not add this overhead.
5. **Escalate only when needed.** If sources conflict or a story materially affects a decision, use a verifier pass with `researcher_summary`, `facts_to_verify`, and artifact paths; otherwise direct search plus artifact grounding is sufficient.

## Primary Method: Google News RSS

The most reliable and fastest approach. No API key needed.

Use the support script instead of embedding parser code in the instruction core: `python3 /home/konstantin/.hermes/skills/productivity/news-search/scripts/google_news_rss_titles.py --limit 20`. For a search query add `--query '<topic>'`; for Western perspective use `--hl en --gl US --ceid US:en`.

### URL Parameters

- `hl=ru` — interface language (use `en` for English)
- `gl=RU` — geo location
- `ceid=RU:ru` — country edition
- Topic feeds: append `&topic=CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB` for Russia-specific, or use search: `&q=Иран+США` for topic search

### Structure of RSS items

Each `<item>` contains:
- `<title>` — headline (may be compound: "Headline - Source")
- `<link>` — Google redirect URL
- `<pubDate>` — GMT timestamp
- `<description>` — HTML with `<ol><li>` listing related articles from multiple sources — useful for seeing coverage breadth

## Alternative: SearXNG (self-hosted)

SearXNG aggregates Google, Bing, DuckDuckGo and other engines via a single JSON API. However:

- Public instances are mostly rate-limited (403/429) or disabled for JSON
- A **self-hosted instance** via Docker is the only reliable path:
  ```
  docker run -d --name searxng -p 8888:8080 searxng/searxng
  ```
  Then query: `http://localhost:8888/search?q=...&categories=news&language=ru&format=json`

- SearXNG advantages over raw Google News RSS:
  - Multi-engine aggregation (wider source coverage)
  - JSON output (easier to parse programmatically)
  - Privacy (self-hosted = no Google tracking)
  - General search (not limited to news)

## SearXNG Setup Details (self-hosted)

See `references/searxng-setup.md` for Docker config, settings.yml, and the detailed side-by-side comparison tested 2026-05-04.

Quick start lives in `references/searxng-setup.md`; keep `SKILL.md` focused on selection rules and pitfalls. Query the local instance at `http://localhost:8888/search?...&categories=news&format=json` after setup.

Key pitfalls:
- Engine names in settings.yml must be **lowercase** (e.g. `google news`, not `Google News`) or SearXNG crashes on startup
- `limiter: false` needed for localhost usage without extra config
- Bind to `127.0.0.1` only (not `0.0.0.0`) for security
- 5/10 public SearXNG instances are rate-limited/block JSON — self-hosting is the only reliable path
- `publishedDate` is often `null` in SearXNG news results (depends on engine); Google News RSS always has dates

## Reference Files

- `references/searxng-setup.md` — Docker setup, settings.yml, deployment steps
- `references/searxng-comparison.md` — Full raw test data from 8-case cross-language comparison (2026-05-04)
- `references/article-extraction.md` — Article body extraction workflow, site-specific notes, curl+python pipeline
- `scripts/google_news_rss_titles.py` — executable Google News RSS fetch/parser kept outside `SKILL.md`

## Comparison: Google News RSS vs SearXNG (tested 2026-05-04)

### Quantitative results (same query, RU+EN)

| Criterion | Google News RSS | SearXNG (self-hosted) |
|---|---|---|
| Availability | ✅ Works without setup | Requires Docker deployment |
| Speed | ✅ Instant | Slower (meta-search across engines) |
| Regional tuning | ✅ `gl=RU&hl=ru` out of the box | Requires config tuning |
| Source diversity | Google News aggregation | Google + Bing + DDG + Yahoo etc. |
| Format | XML/RSS (trivial parsing) | JSON API (programmer-friendly) |
| Privacy | Google sees queries | Full privacy (self-hosted) |
| Maintenance | Zero | Docker updates, rate-limit config |
| General search | News only | Web, images, news, etc. |
| **Dates in results** | **✅ 100% always** | ❌ 0–60% (engine-dependent) |
| **Niche RU topics** | ✅ 5+ relevant results | ⚠️ 2–3 results |

### Cross-language routing (KEY insight)

Google News `hl` (language) and `gl` (region) are **separate axes** with different effects:
- `hl=ru` with Russian query + any `gl` → **same RU sources** regardless of gl=RU/US/GB
- `hl=en` + English query + `gl=US` → **completely different perspective**: Axios, NYT, CNBC, Reuters, Times of Israel instead of BBC Russia, Life.ru
- `hl=en` + Russian query → broken results, mismatch

SearXNG `language=en` activates qwant+reuters engines (unavailable in RU mode), but dates are spotty.

**Decision matrix — which tool + language for which case:**

| Case | Best choice | Why |
|---|---|---|
| RU news digest (morning) | Google RSS `hl=ru&gl=RU` | Fastest, 100% dates, best RU sources |
| Western perspective on geopolitics | Google RSS `hl=en&gl=US` | NYT/Reuters/Axios/CNBC — entirely different angle |
| Niche RU-market topic | Google RSS `hl=ru&gl=RU` | SearXNG returns 2–3 vs Google's 5+ |
| Cross-source verification | SearXNG `language=ru` | 3 engines in parallel, spot discrepancies |
| Non-news web search | SearXNG `language=en or ru` | Google RSS is news-only |
| Privacy-sensitive query | SearXNG (any language) | Self-hosted, no Google tracking |
| Western niche topic | SearXNG `language=en` | qwant+reuters yield unique articles |

**Default**: Google News RSS `hl=ru&gl=RU`. Switch when you need western perspective (`hl=en&gl=US`), cross-verification (SearXNG), or non-news search (SearXNG).

See `references/searxng-comparison.md` for the full raw test data from the 8-case cross-language comparison.

## Article Body Extraction

When Konstantin asks for details beyond headlines (e.g. «А что там за X?»), extract the full article text:

### Step 1 — Get the article URL

RSS titles often lack direct URLs. Two strategies:

1. **Google News RSS description field** contains `<ol><li>` with links to multiple sources — parse these first.
2. **Site search page**: If you know the site domain from the headline slug, fetch `https://<domain>/?s=<url-encoded-query>` and extract `<a href>` links containing keywords from the headline. The `irk.today` pattern: use `?s=` for search; the article URL follows `/<year>/<month>/<day>/<slug>/` convention.

### Step 2 — Fetch and extract text

**Prefer `md` (curl.md CLI) when not rate-limited.** It produces cleaner Markdown with less noise than the raw `curl | python3` pipeline. Falls back gracefully:

```sh
# Preferred: curl.md (clean Markdown, ~7x less tokens than HTML)
export PATH="$HOME/.local/bin:$PATH"
md "<article_url>"

# With objective to narrow to relevant section:
md "<article_url>" -o "article body" -k "keyword1,keyword2"

# Fallback: curl + python3 (works when rate-limited, no dependency on external service)
```

If `md` returns rate-limit error (`RATE_LIMIT_EXCEEDED`), fall back to the `curl | python3` pipeline below. Anonymous quota is 100 fetches/hour (3 objective/hour); see `curl-md` skill for auth instructions.

**Use `curl + python3` pipeline.** Do NOT use `browser_navigate` (fails with Chrome sandbox error in container) or `delegate_task` with browser toolset (same sandbox issue, subagent inherits the environment limitation).

```bash
curl -sL "<article_url>" -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys, re, html as htmlmod
raw = sys.stdin.read()
raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', raw)
text = htmlmod.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
for kw in ['keyword1', 'keyword2']:  # keywords from headline
    idx = text.lower().find(kw.lower())
    if idx > 0:
        start = max(0, idx - 500)
        print(text[start:start+5000])
        break
"
```

### Step 3 — Verify extraction

- If output is mostly navigation/boilerplate instead of article text, the URL may be wrong or the site may require JS rendering. Try the site search page to find the correct URL.
- Some sites (irkutskmedia.ru) return 404 for guessed URLs — always verify with site search.
- `irk.today` uses Cyrillic slugs with `й` → `y` transliteration (e.g. «Иркутск» → `irkutske`, «генеративный» → `generativnyy`). The URL discovery via `?s=` search page is more reliable than guessing.

### Pitfalls

- **Browser sandbox**: `browser_navigate` fails with `No usable sandbox!` in container/VM environments. Don't waste turns on it for article extraction — go straight to curl.
- **delegate_task with browser**: Same sandbox issue propagates to subagents. Don't delegate web fetching to a subagent expecting browser tools to work.
- **404 pages**: Russian news sites often use non-obvious URL patterns. Always validate that extracted text contains the expected headline keywords before presenting to user.
- **Encoding**: Use `html.unescape()` for HTML entities (`&laquo;`, `&raquo;`, `&mdash;`, etc.). Curl handles encoding; the python pipeline decodes it.

## Summarization Style

For Konstantin, deliver:
- **Brief status first**, then grouped by topic
- **Concreteness**: who, what, where, with numbers when available
- **Russian-language** news as priority, key international stories included
- Flag confidence if story has limited sourcing
- Use flag emoji for countries: 🇺🇸🇷🇺🇮🇷🇩🇪🇫🇮🇦🇲 etc.
- Separate checked facts from interpretation; include source/artifact caveat when artifacts are absent or source is a search/RSS wrapper