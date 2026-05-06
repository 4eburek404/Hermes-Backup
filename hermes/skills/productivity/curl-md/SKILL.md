---
name: curl-md
description: "Convert any URL to optimized Markdown using curl.md CLI. Reduces token usage 6-500x vs raw HTML. Use for fetching docs, articles, and web pages as clean Markdown for agent context."
version: 1.0.0
author: konstantin
license: MIT
metadata:
  hermes:
    tags: [web, markdown, tokens, fetch, curl, agent-context]
---

# curl.md — URL → Markdown for Agents

Convert any URL to clean, token-optimized Markdown. Reduces context size 6-500x vs raw HTML.

## When to Use

- Fetching documentation pages (MDN, Cloudflare, Vercel, etc.) for agent context
- Extracting article content for summarization or analysis
- Pre-filtering docs to only relevant sections (saves massive tokens)
- Replacing manual HTML→text parsing with `curl | python3 -c "re.sub..."`
- Cron jobs monitoring docs/changelogs

## CLI Usage

```sh
# Basic: fetch full page as Markdown
md <url>

# With alias (same as md)
curl.md <url>
curlmd <url>

# Narrow content with objective — keeps only sections matching your query
md <url> -o "streaming response body"

# Pre-filter by keywords (comma-separated, no spaces)
md <url> -k "ReadableStream,getReader"

# Combine objective + keywords for maximum precision
md <url> -o "streaming response body" -k "ReadableStream,getReader"

# Force fresh fetch (bypass cache)
md <url> --fresh

# Mode: rush (fast, less precise) or smart (default, better filtering)
md <url> -o "objective" -m rush
```

## Compression Results (verified 2026-05-06)

| Source | Raw HTML | curl.md basic | curl.md filtered | Compression |
|--------|----------|---------------|------------------|-------------|
| MDN Fetch API | 173 KB | 27 KB | 318 B | ×544 |
| MDN Fetch API | 173 KB | 27 KB | 3.7 KB | ×47 |

**Rule of thumb:** Basic fetch → 6-7x compression. Filtered with objective+keywords → 50-500x.

## Output Format

```markdown
---
title: Page Title
url: https://original-url.com/page
site: original-url.com
---

[Page content as clean Markdown]

---

Powered by [curl.md](https://curl.md)
```

Frontmatter always includes `title`, `url`, `site`. Use this for source attribution.

## Decision Matrix

| Case | Command | Why |
|------|---------|-----|
| Quick fact from a doc page | `md <url> -o "fact" -k "term1,term2"` | Maximum token savings |
| Full article for summarization | `md <url>` | Need complete context |
| Monitoring docs for changes | `md <url> --fresh` | Bypass stale cache |
| Code reference lookup | `md <url> -o "how to use X" -k "X,method"` | Only relevant examples |
| News article extraction | `md <url>` | Full text, no nav/ads |

## Integration Patterns

### In terminal() calls
```sh
export PATH="$HOME/.local/bin:$PATH"
md example.com -o "objective" -k "keyword1,keyword2"
```

### In execute_code()
```python
from hermes_tools import terminal
result = terminal(f'md {url} -o "objective" -k "kw1,kw2"')
markdown_content = result["output"]
```

### In delegate_task context
Tell subagents: "Use `md <url>` to fetch web pages as Markdown instead of raw HTML. Add `-o "objective" -k "keywords"` to narrow content."

## Rate Limits (verified from official docs 2026-05-06)

| | Anonymous | Free authenticated | Paid |
|---|---|---|---|
| **Standard fetches** | 100/hour | 1,000/hour | Unlimited |
| **Objective queries** | 3/hour | 10/hour | Unlimited |

Authenticated = free GitHub OAuth login via `md auth login`.

Rate-limited responses return HTTP 429 with code `rate_limit_exceeded` and a `retry-after` header. Response headers include `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset`.

**Practical impact:** Anonymous objective queries (3/hour) exhaust very fast. Auth is essential for any real workflow. Batch tasks need authentication even at 10 obj/hour — space requests over time.

## Authentication

### Interactive auth (requires browser)

```sh
md auth login
```

Opens browser for GitHub OAuth. Displays confirmation code + URL. **Does NOT work headlessly** — the CLI calls `xdg-open` and polls the device flow with a 5-minute timeout. In container/VM environments without a browser, use the manual device flow below.

### Manual device flow (headless auth)

When `md auth login` can't open a browser (headless server, container, VM):

```sh
# 1. Initiate device code — get code + user_code
curl -sL -X POST "https://curl.md/api/auth/device" -H "Content-Type: application/json"
# Returns: {"code":"<code>","interval":1,"user_code":"<USER_CODE>","verification_uri":"https://curl.md/auth/device"}

# 2. Open verification URL in YOUR browser (from any device), confirm the user_code
#    https://curl.md/auth/device?user_code=<USER_CODE>

# 3. Poll for token — run after confirming in browser
curl -sL -X POST "https://curl.md/api/auth/device/token" -H "Content-Type: application/json" -d '{"code":"<code>"}'
# Returns on success: {"authorization":"Bearer ...","expires_at":"...","refresh_token":"...","refresh_token_expires_at":"..."}
# Returns pending: {"code":"authorization_pending","message":"Authorization pending"}
# Returns expired: {"code":"expired_token","message":"Token expired"}

# 4. Save session to disk so CLI picks it up
mkdir -p ~/.local/share/curl-md/sessions
cat > ~/.local/share/curl-md/sessions/https%3A%2F%2Fcurl.md.json << 'EOF'
{
  "refresh_token": "<refresh_token>",
  "refresh_token_expires_at": "<refresh_token_expires_at>"
}
EOF
chmod 600 ~/.local/share/curl-md/sessions/https%3A%2F%2Fcurl.md.json

# 5. Verify
md auth status
```

Session storage: `~/.local/share/curl-md/sessions/https%3A%2F%2Fcurl.md.json` (XDG_DATA_HOME-based). File has mode 0600. The CLI reads refresh_token from this file to mint short-lived auth headers automatically.

### API tokens (for scripts/CI)

```sh
md token create <name>       # Create org-scoped: md org switch <org> && md token create <name>
md token list
md token delete <id>
```

Use token via header: `Authorization: Bearer <token>` or query param `token=<token>`.

## HTTP API (alternative to CLI)

The hosted endpoint works without CLI installation:

```sh
# Basic fetch — returns text/markdown by default
curl "https://curl.md/developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch"

# With objective + keywords
curl "https://curl.md/developer.mozilla.org/...?o=streaming+response+body&k=ReadableStream,getReader"

# JSON response
curl "https://curl.md/example.com" -H "Accept: application/json"
# Returns: {"content": "# Example\n..."}

# With auth token
curl "https://curl.md/example.com" -H "Authorization: Bearer <token>"
```

Same rate limits as CLI. Useful in scripts or subagent contexts where CLI isn't installed.

## Response Headers (useful for debugging)

- `x-cache` — `HIT` or `MISS`
- `x-request-id` — for debugging
- `x-tokens-count` — estimated tokens in response
- `x-tokens-saved` — estimated tokens saved vs source
- `x-cost-mills` — request cost in mills (1/1000 cent)
- `x-credits-remaining` — remaining prepaid credits (when available)

## Limitations

- **Server dependency:** All fetches go through curl.md service. Won't work for private/internal URLs or sites behind auth.
- **Cache:** Default returns cached results. Use `--fresh` for latest content.
- **SPA/JS-heavy sites:** Server-side rendering only; JavaScript-heavy apps may not render fully.
- **Version:** 0.1.1 (early stage, may change).
- **Binary size:** ~100MB (Bun-compiled binary).
- **Rate limit (authenticated):** 1,000 basic/hr, 10 objective/hr. Free auth via GitHub OAuth. Headers `x-ratelimit-remaining` show quota. Paid plans skip limits.
- **Rate limit (anonymous):** 100 basic/hr, 3 objective/hr — too restrictive. Always authenticate via `CURLMD_API_KEY` env var.
- **Headless auth:** `md auth login` requires browser. Use manual device flow: `curl -sL -X POST https://curl.md/api/auth/device`, open verification URL, poll `curl -sL -X POST https://curl.md/api/auth/device/token -d '{"code":"..."}'`, then `md token create <name>` for persistent API key.

## Integration with other skills

- **news-search**: Use `md <article_url>` instead of `curl | python3` pipeline for article extraction when not rate-limited. It produces cleaner Markdown with less noise, but shares the same rate limit — use `curl | python3` as fallback when rate-limited.
- **web-article-reader**: `md <url>` with `--objective` can pre-filter before the `article` CLI, reducing token waste on long pages.

## Reference Files

- `references/api-and-auth-details.md` — Full API docs, auth/device flow internals, session file format, token management, credits. Extracted from official docs and CLI source code (2026-05-06).

## Authentication (already done)

Account: **4eburek404** (GitHub OAuth, free tier).
API key: `curlmd_1x2ooi34i6ooeedhbs8b12q3zai31l26` (named "hermes", set in `~/.bashrc` as `CURLMD_API_KEY`).
Rate limits with auth: 1,000 basic/hr + 10 objective/hr (vs 100/3 anonymous).

### Rate limits (authenticated)

Standard fetches: **1,000/hour**. Objective queries: **10/hour**.
Headers `x-ratelimit-remaining` and `x-ratelimit-reset` show remaining quota.
When rate-limited: response includes `retry-after` header. Paid plans skip limits.

### Re-authentication

If auth expires: `md auth login` (device flow). Or set `CURLMD_API_KEY` env var.
Create new tokens: `md token create <name>`. List: `md token list`. Delete: `md token delete <name>`.
Auth status: `md auth status` or `md auth status --token <token>`.

## Installation (already done)

Binary at `~/.local/bin/curl.md` with symlink at `~/.local/bin/md`.
`CURLMD_API_KEY` set in `~/.bashrc`. PATH includes `~/.local/bin`.