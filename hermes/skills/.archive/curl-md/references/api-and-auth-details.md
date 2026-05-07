# curl.md — API & Auth Details

Extracted from official docs (`https://curl.md/docs/guide/api.md`, `https://curl.md/docs/faq.md`) and CLI source (`https://github.com/wevm/curl.md/blob/main/cli/src/internal/auth.ts`, `cli/src/internal/session.ts`, `cli/src/utils.ts`).

## Rate Limiting (from official API docs)

On the main fetch endpoint, free usage is rate limited and returns 429 with code `rate_limit_exceeded` when exceeded.

- Standard fetches: `100/hour` anonymous, `1,000/hour` authenticated
- Objective queries: `3/hour` anonymous, `10/hour` authenticated
- Paid usage skips these rate limits

Successful responses include rate-limit headers:
- `x-ratelimit-limit`
- `x-ratelimit-remaining`
- `x-ratelimit-reset`

Rate-limited responses also include `retry-after`.

## HTTP API

### Fetch endpoint

```sh
# Markdown (default)
curl "https://curl.md/<url>"

# With objective + keywords
curl "https://curl.md/<url>?o=<objective>&k=<keywords>"

# JSON response
curl "https://curl.md/<url>" -H "Accept: application/json"
# Returns: {"content": "markdown text"}
```

### Response headers

- `x-cache` — HIT or MISS
- `x-request-id` — request identifier for debugging
- `x-tokens-count` — estimated token count for the final response
- `x-tokens-saved` — estimated tokens saved versus the source content
- `x-cost-mills` — request cost in mills
- `x-credits-remaining` — remaining prepaid credits, when available

### Error codes

```json
{"code": "rate_limit_exceeded", "message": "Rate limit exceeded. Try again in <seconds>s"}
{"code": "fetch_failed", "message": "Upstream returned <status>"}
{"code": "invalid_api_key", "message": "Invalid API key"}
```

## TypeScript SDK

```ts
import { createClient } from 'curl.md'

const client = createClient()
const res = await client.fetch('docs.github.com/en/webhooks', {
  keywords: ['pull_request'],
  objective: 'pull request webhook event payload',
  token: process.env.CURLMD_API_KEY,  // optional API key
})

// JSON response
const json = await res.json()
```

Request options: `objective`, `keywords`, `mode` (rush|smart), `fresh`, `token`.

## Authentication

### Device flow (how the CLI does it)

1. `POST https://curl.md/api/auth/device` → `{"code":"...","interval":1,"user_code":"...","verification_uri":"https://curl.md/auth/device"}`
2. User opens `https://curl.md/auth/device?user_code=<user_code>` in browser and confirms
3. Polling: `POST https://curl.md/api/auth/device/token` with `{"code":"<code>"}` — returns `authorization_pending` until confirmed, then returns tokens
4. CLI default timeout: 5 minutes (`defaultLoginTimeoutMs = 5 * 60 * 1000`)
5. Poll interval: from API response `interval` field (default 5 seconds)

### Token types

- **Session tokens**: Obtained via device flow. Stored in `~/.local/share/curl-md/sessions/https%3A%2F%2Fcurl.md.json`. Contains `refresh_token` + `refresh_token_expires_at`. The CLI mints short-lived auth headers from the refresh token automatically via `POST /api/auth/headers`.
- **API tokens**: Created via `md token create <name>`. For scripts/CI. Can be org-scoped (`md org switch <org>` first). Use as `Authorization: Bearer <token>` header or `token` query param.

### Session file format

```json
{
  "organization_id": "optional-org-id",
  "refresh_token": "rt_...",
  "refresh_token_expires_at": "2026-06-06T12:00:00Z"
}
```

File mode: 0600. Location: `$XDG_DATA_HOME/curl-md/sessions/` or `~/.local/share/curl-md/sessions/`.

### Account info

```sh
md auth status          # Check if authenticated
md auth login           # Interactive login (opens browser)
md auth logout          # Revoke session
md token create <name>  # Create API token
md token list           # List API tokens
md token delete <id>    # Delete API token
```

## Organizations

```sh
md org create <name>
md org invite <email>
md org list
md org member
md org switch <name>
md org view
```

## Credits (paid usage)

```sh
md credits add          # Add prepaid credits (payment page)
md credits status       # Check balance
```

Credits skip rate limits entirely. Cost is in mills (1/1000 cent). See `x-cost-mills` and `x-credits-remaining` response headers.