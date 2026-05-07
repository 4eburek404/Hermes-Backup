---
name: web-article-reader
description: Read, summarize, and save web articles from URL. Handles HTML extraction when browser is unavailable.
version: 1.1.0
tags: [web, article, research, curl, memory]
---

# Web Article Reader

Read a web article from a URL, extract clean text, summarize it, and optionally save key points to holographic memory.

## Grounding Artifact Contract

For URL/API-backed claims, do not rely on the visible URL string alone. Preserve evidence so the controller/user can audit what was actually read.

1. **Create artifacts for source-backed work.** When summarizing, comparing, saving, or citing article content, save the extraction/request output to a deterministic path in the current workspace, for example:
   ```text
   ./extracts/<domain>_<slug_or_hash>.md
   ./api_responses/<domain>_<slug_or_hash>.json
   ./queries/<topic>_<YYYY-MM-DD>.txt
   ```
   If there is no project workspace, use a temporary task directory and report the path.
2. **Artifact path in the answer.** For any important quoted or summarized claim, keep the source URL plus artifact path in notes/report or final evidence. If no artifact exists, label the claim as ungrounded/non-persistent and re-extract before relying on it.
3. **Current-source discipline.** For current events, product versions, pricing, policies, legal/travel facts, or time-sensitive pages, check the current date with a tool and fetch the page/API live. Do not answer from stale training-memory.
4. **Multi-step article/research workflows.** If the work has more than one source, a comparison, or delegated subagents, write `plan.md → notes.md → report.md` (or a skill-specific equivalent) alongside `./extracts/` so progress and verification survive context loss.

## When to use

User shares a URL to an article/blog post/web page and wants to discuss it or save it.

## Steps

1. **Extract article with `article` CLI** (installed at `~/.local/bin/article`, source `/home/konstantin/code/clis/article/`). Executable examples are in `references/cli-usage.md`; keep this core as workflow/instructions only.

2. **If `article` output is noisy** (nav/menu/footer pollution common on Bitrix, WordPress etc.):
   - `article read` extracts `<article>` → `<main>` → `<body>` — this often includes repeated nav.
   - For clean text, pass the output to summarization which tolerates noise, or use `--json read` and extract the content field programmatically.
   - `summary-input` truncates at `--max-chars` but does NOT strip nav — it preserves structure for downstream summarization, not as a clean extractor.

3. **If `article` returns only nav/shell** (JS-heavy listing pages):
   - Listing pages that load content via AJAX (e.g. `/news/` on Bitrix sites) will only yield navigation HTML.
   - Switch to `browser_navigate` for JS rendering, or try finding a direct article URL and extract that instead.
   - Confirm with `article --json request get` — check `body_preview` for real content vs. empty shell.
   - Quick reachability check before full extraction: `article --json doctor --check-url '<URL>'` — verifies network access and returns status without downloading the full page.

4. **For news/RSS follow-up requests, find the direct publisher source before summarizing.** Google News and search-result wrapper URLs may return HTTP 200 but not the actual article text. Search the publisher site by exact headline/distinctive phrase, then extract the direct article URL with `article --json read`. See `references/news-and-rss-followup.md` for examples and pitfalls from Russian travel-news sources.

5. **Summarize** with structured key points. For long articles, use headers as natural section breaks.

6. **Relate to user's context** — connect article themes to the user's known work, projects, or architecture.

7. **Save to memory on request** — use `fact_store` with entity = domain/author name, tags = `article,<topic>`, and content = compact summary with URL + key theses. Always `search` for duplicates first.

### Fallback: standalone Python extractor (if `article` CLI unavailable)

The fallback implementation lives outside the instruction core: `scripts/fallback_extract_article.py`. Run it with `python3 /home/konstantin/.hermes/skills/research/web-article-reader/scripts/fallback_extract_article.py '<URL>'`. It is primitive (`<article>` → `<main>` → `<body>`); for JS-heavy pages use browser rendering instead.

## Pitfalls

- **JS-heavy listing pages** (Bitrix, SPA frameworks): `article` returns nav/shell only — content is loaded via AJAX. Use browser for these or find direct article URLs.
- **Nav noise in extraction**: `article read` on `<main>`/`<body>` includes repeated navigation menus. Individual article pages are much cleaner than listing pages.
- **`summary-input` does not strip nav** — it truncates at `--max-chars` preserving structure for downstream summarization. Do not expect clean article text from it.
- **News sites often block automated requests**: many news outlets (e.g., Google News, news.google.com, DuckDuckGo) restrict curl/Jina AI scraper access, returning empty or error responses. Prefer using RSS feeds (`.rss` URLs) when available, or fall back to browser rendering with `browser_navigate`.
- Browser may not be available — try `article` CLI first, fallback to `curl | python3` only if CLI is absent.

## Verification

- After extraction, quickly scan output for article-specific content (headline, body text). If only nav/footer — the page needs browser rendering.
- Confirm all major sections of the article were extracted (compare headings count).
- Confirm artifact paths exist for cited URL/API-backed claims (`./extracts/`, `./api_responses/`, `./queries/`, or temporary task directory); missing artifact means the claim is ungrounded/non-persistent.
- For current/time-sensitive claims, confirm the page/API was fetched live in the current session/date instead of relying on stale training-memory.
- After saving to fact_store, call `fact_feedback` on the saved fact.