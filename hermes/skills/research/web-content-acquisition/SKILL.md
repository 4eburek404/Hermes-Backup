---
name: web-content-acquisition
description: "Fetch, extract, and process web content into clean agent-consumable form. Covers url-to-markdown (curl.md CLI), article extraction (article CLI + fallback), news search (Google News RSS + SearXNG), and grounding artifacts. Use when the agent needs to read a URL, search news, extract article text, or convert HTML to Markdown."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [web, fetch, markdown, article, news, rss, searxng, extraction, curl, agent-context, grounding]
    related_skills: [knowledge-architecture]
---

# Web Content Acquisition

Fetch, extract, and process web content into clean agent-consumable form — from raw URLs to structured news digests.

## Decision Matrix: Which Tool for Which Task

| Task | Primary tool | Fallback |
|------|-------------|----------|
| Fetch a doc/article URL as clean Markdown | `md <url>` (6-500x compression) | `curl \| python3` pipeline |
| Fetch with keyword/objective pre-filter | `md <url> -o "objective" -k "kw1,kw2"` | `curl \| python3` + keyword grep |
| Extract article text for summarization | `article read <url>` | `scripts/fallback_extract_article.py` |
| News headline digest (Russian) | Google News RSS `hl=ru&gl=RU` | SearXNG `language=ru` |
| News with Western perspective | Google News RSS `hl=en&gl=US` | SearXNG `language=en` |
| Cross-source news verification | SearXNG (multi-engine) | Google RSS `hl=ru` + `hl=en` |
| Non-news web search | SearXNG | — |
| JS-heavy / SPA page | `browser_navigate` | `article --json read` (check `body_preview`) |
| Private/internal/auth-required page | `browser_navigate` (with session) | — |

## Tool 1: curl.md CLI (`md`) — URL-to-Markdown

Convert any URL to clean, token-optimized Markdown. Reduces context size 6-500x vs raw HTML.

### Basic Usage

```sh
export PATH="$HOME/.local/bin:$PATH"
md <url>                           # Full page as Markdown
md <url> -o "objective"            # Only sections matching objective
md <url> -k "keyword1,keyword2"    # Pre-filter by keywords
md <url> -o "obj" -k "kw1,kw2"     # Combine both for max precision
md <url> --fresh                   # Bypass cache
md <url> -o "obj" -m rush          # Rush mode (fast, less precise)
```

### Rate Limits (verified 2026-05-06)

| | Anonymous | Free authenticated | Paid |
|---|---|---|---|
| **Standard fetches** | 100/hour | 1,000/hour | Unlimited |
| **Objective queries** | 3/hour | 10/hour | Unlimited |

**Always authenticate.** Anonymous objective queries (3/hr) exhaust instantly. Auth via GitHub OAuth: `md auth login` (manual device flow for headless — see `references/curlmd-api-and-auth.md`).

**If rate-limited**, fall back to `curl | python3` pipeline or `article` CLI.

### Compression Reference

| Source | Raw HTML | `md` basic | `md` filtered | Compression |
|--------|----------|-----------|----------------|-------------|
| MDN Fetch API | 173 KB | 27 KB | 318 B | ×544 |
| General docs | varies | ~6-7x | ~50-500x | — |

### HTTP API (when CLI unavailable)

```sh
curl "https://curl.md/<url>"                          # text/markdown
curl "https://curl.md/<url>?o=objective&k=kw1,kw2"   # filtered
curl "https://curl.md/<url>" -H "Accept: application/json"  # JSON
curl "https://curl.md/<url>" -H "Authorization: Bearer <token>"
```

### Limitations

- All fetches go through curl.md service — won't work for private/internal URLs or sites behind auth.
- Cache: default returns cached results. Use `--fresh` for latest content.
- SPA/JS-heavy sites: server-side rendering only; JS apps may not render fully.
- Response headers useful for debugging: `x-cache`, `x-tokens-count`, `x-tokens-saved`, `x-ratelimit-remaining`.

See `references/curlmd-api-and-auth.md` for full API docs, headless device flow, token management, and installation details.

## Tool 2: Article CLI — Article Extraction

Extract article text from a URL, typically for summarization or saving to memory. CLI at `~/.local/bin/article`, source at `/home/konstantin/.hermes/hermes-agent/skills/research/web-content-acquisition/cli/`.

### Usage

```sh
article read <url>                   # Extract article text
article --json read <url>            # JSON with content field
article summary-input <url>          # Truncated for summarization (includes nav)
article --json doctor --check-url '<url>'  # Reachability check
```

### Handling extraction noise

- **Nav noise**: `article read` extracts `<article>` → `<main>` → `<body>` — nav pollution common on Bitrix, WordPress. Individual article pages are much cleaner than listing pages.
- **JS-heavy listing pages**: AJAX-loaded content (`/news/` on Bitrix) yields nav/shell only. Use `browser_navigate` or find direct article URLs. Check with `article --json read` — inspect `body_preview` for real content vs. empty shell.
- **`summary-input` does NOT strip nav** — it truncates at `--max-chars` preserving structure for downstream summarization, not clean extraction.
- **News sites often block automated requests** — Google News, DuckDuckGo restrict curl/scraper access. Prefer RSS feeds or browser rendering.

See `references/article-cli-usage.md` for full command reference and examples.
See `references/news-and-rss-followup.md` for finding direct publisher URLs behind Google News/RSS wrappers.

### Fallback: standalone Python extractor

```sh
python3 /home/konstantin/.hermes/hermes-agent/skills/research/web-content-acquisition/scripts/fallback_extract_article.py '<URL>'
```

Primitive extraction (`<article>` → `<main>` → `<body>`). For JS-heavy pages use browser rendering instead.

## Tool 3: News Search

Search and summarize Russian and international news.

### Core Principle

**Search news yourself directly with terminal curl + python parsing.** Do NOT delegate news search to subagents. Delegate_task is for coding tasks, not search queries.

### Primary: Google News RSS

Use the support script: `python3 /home/konstantin/.hermes/hermes-agent/skills/research/web-content-acquisition/scripts/google_news_rss_titles.py --limit 20`. Add `--query '<topic>'` for search; `--hl en --gl US --ceid US:en` for Western perspective.

URL parameters: `hl=ru` (language), `gl=RU` (geo), `ceid=RU:ru` (edition). Topic search: `&q=Иран+США`.

### Cross-language routing (KEY insight)

- `hl=ru` + Russian query + any `gl` → **same RU sources** regardless of gl
- `hl=en` + English query + `gl=US` → **completely different Western perspective**: Axios, NYT, CNBC
- `hl=en` + Russian query → broken results, mismatch

### SearXNG (self-hosted alternative)

Multi-engine aggregation (Google + Bing + DDG + Yahoo etc.) via self-hosted Docker instance at `http://localhost:8888/search?q=...&categories=news&language=ru&format=json`.

See `references/searxng-setup.md` for Docker config and `references/searxng-comparison.md` for full cross-language test data.

**Key SearXNG pitfalls:**
- Engine names in `settings.yml` must be **lowercase** or SearXNG crashes
- `limiter: false` needed for localhost
- Bind to `127.0.0.1` only
- `publishedDate` often `null` (engine-dependent); Google News RSS always has dates
- Self-hosting is the only reliable path — public instances are mostly rate-limited

### Which tool for which news case

| Case | Best choice | Why |
|---|---|---|
| RU news digest | Google RSS `hl=ru&gl=RU` | Fastest, 100% dates, best RU sources |
| Western perspective on geopolitics | Google RSS `hl=en&gl=US` | NYT/Reuters/Axios vs BBC Russia |
| Niche RU topic | Google RSS `hl=ru&gl=RU` | More results than SearXNG |
| Cross-source verification | SearXNG `language=ru` | 3 engines in parallel |
| Non-news web search | SearXNG | Google RSS is news-only |
| Privacy-sensitive query | SearXNG | Self-hosted, no tracking |

### News article body extraction

For details beyond headlines, extract the full article text:
1. Google News RSS `<description>` contains `<ol><li>` with links to multiple sources — parse these first.
2. Site search: `https://<domain>/?s=<query>` → find direct article URLs.
3. Extract text: prefer `md <url>` when not rate-limited; fall back to `curl | python3` pipeline.
4. Verify extraction contains headline keywords before presenting to user.

## Grounding Artifact Contract

For URL/API-backed claims, preserve evidence so the user can audit what was actually read.

1. **Create artifacts for source-backed work.** Save extraction/request output:
   ```text
   ./extracts/<domain>_<slug_or_hash>.md
   ./api_responses/<domain>_<slug_or_hash>.json
   ./queries/<topic>_<YYYY-MM-DD>.txt
   ```
2. **Artifact path in the answer.** For important claims, keep source URL + artifact path. No artifact = label "ungrounded/non-persistent."
3. **Current-source discipline.** For time-sensitive content, check current date with a tool and fetch live. Don't answer from stale training-memory.
4. **Multi-source/research.** Write `plan.md → notes.md → report.md` alongside `./extracts/`.

## Shared Fallback: curl + python3 Pipeline

When `md` and `article` CLI are unavailable or rate-limited:

```bash
curl -sL "<url>" -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys, re, html as htmlmod
raw = sys.stdin.read()
raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', raw)
text = htmlmod.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
print(text[:10000])
"
```

## Cross-Cutting Pitfalls

1. **Browser sandbox**: `browser_navigate` fails with `No usable sandbox!` in container/VM environments. Don't waste turns on it for article extraction — go straight to curl.
2. **delegate_task with browser**: Same sandbox issue propagates to subagents.
3. **404 pages**: Russian news sites use non-obvious URL patterns. Verify extracted text contains expected keywords.
4. **Rate limit cascade**: If `md` is rate-limited, fall back to `curl | python3`. If `article` is blocked, try `md` or browser.
5. **JS-heavy pages**: Neither `md` nor `article` can render JavaScript. Use `browser_navigate` in environments where it works.
6. **Nav noise**: Always verify extraction contains article-specific content, not just nav/footer boilerplate.
7. **Cyrillic URL slugs**: `irk.today` uses transliteration (й→y). Site search (`?s=`) is more reliable than guessing slugs.
8. **`md` server dependency**: All fetches go through curl.md service. Won't work for private/internal URLs.
9. **News current-date grounding**: Always check current date before producing news answers. Don't answer from stale training-memory.

## Verification Checklist

- [ ] Extraction output scanned for article-specific content (headline, body text), not just nav/footer.
- [ ] Rate limits respected — fallback tool used when primary is limited.
- [ ] For time-sensitive claims, page was fetched live in current session.
- [ ] Grounding artifacts exist for cited URL/API-backed claims.
- [ ] News results include source attribution and date.
- [ ] Multi-language news routing applied correctly (`hl`/`gl` parameters).
- [ ] SearXNG engine names lowercase in `settings.yml` (if self-hosted).
