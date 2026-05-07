# Article Body Extraction — Session Notes (2026-05-06)

## What Works

- **Google News RSS script** (`scripts/google_news_rss_titles.py`) reliably returns headlines with dates and source attribution. Use it as the first step to discover articles.

- **Site search pages** are the most reliable way to discover article URLs when you only have a headline and source name:
  - `irk.today/?s=<query>` — returns search results with full article URLs
  - Pattern: use URL-encoded Russian text; the response contains `<a href>` links with absolute URLs

- **curl + python3 pipeline** reliably extracts article body text from Russian news sites:
  - Strip `<script>`, `<style>`
  - Strip all HTML tags
  - `html.unescape()` for entities
  - Collapse whitespace
  - Keyword-based windowing (find keyword, extract ±500–5000 chars)

## What Doesn't Work

- **`browser_navigate`** — Chrome sandbox error (`No usable sandbox!`) in container/VM environments. Don't attempt for article extraction.
- **`delegate_task` with `["browser"]` toolset** — subagent inherits the same sandbox limitation; wastes turns and returns nothing useful.
- **URL guessing from slugs** — Russian headlines don't map predictably to URLs. Examples of mismatches:
  - `irkutskmedia.ru` returns 404 for guessed URLs
  - `irk.today` uses transliterated slugs (й→y, ы→y), making manual construction error-prone
  - `sibir.info` URLs are not guessable from headlines alone

## Site-Specific Notes

### irk.today
- Search: `https://irk.today/?s=<url-encoded-query>`
- Article URL pattern: `/<YYYY>/<MM>/<DD>/<transliterated-slug>/`
- Cyrillic transliteration is non-obvious: «генеративный» → `generativnyy`, «Приангарья» → `priangarya`
- Always use site search to find the correct URL rather than constructing it

### irkutskmedia.ru
- Returns 404 for many guessed URL patterns
- Search page not tested — fall back to Google News RSS title discovery

### sibir.info (Сибирское информационное агентство)
- Article URLs are not guessable from headlines
- Use Google News RSS to discover, then curl to extract

## Recommended Workflow for "Tell me more about X"

1. Run Google News RSS script with targeted query (include location/organization names)
2. Parse headlines — identify the specific article(s) the user is asking about
3. Construct site search URL from the source domain in the headline
4. Fetch site search page, extract article URL via regex on `<a href>` tags
5. curl + python3 pipeline to extract article body
6. Present structured summary (who, what, numbers, timelines, source attribution)