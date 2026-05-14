# hh.ru OAuth & Error Reference

Source: GitHub hhru/api docs + OpenAPI spec (27094 lines) + live testing Apr 2026.

## OAuth Token Exchange Errors

| HTTP | error | error_description | meaning |
|------|-------|-------------------|---------|
| 400 | invalid_request | account not found | wrong client_id + client_secret pair |
| 400 | invalid_request | account is locked | user account blocked |
| 400 | invalid_request | password invalidated | user must reset password on hh.ru |
| 400 | invalid_request | login not verified | account unverified |
| 400 | invalid_request | bad redirect url | redirect_uri mismatch |
| 400 | invalid_request | token is empty | refresh_token not sent |
| 400 | invalid_request | token not found | wrong refresh_token |
| 400 | invalid_request | code not found | authorization_code not found |
| 400 | invalid_client | client_id or client_secret not found | app deleted or wrong secret |
| 400 | invalid_grant | token has already been refreshed | refresh_token reuse attempted |
| 400 | invalid_grant | token not expired | trying to refresh valid access_token |
| 400 | invalid_grant | token was revoked | token revoked (e.g. password expired) |
| 400 | invalid_grant | bad token | wrong token value |
| 400 | invalid_grant | code has already been used | authorization_code reuse |
| 400 | invalid_grant | code expired | authorization_code expired |
| 400 | invalid_grant | code was revoke | authorization_code revoked |
| 400 | invalid_grant | token deactivated | user changed password |
| 400 | unsupported_grant_type | unsupported grant_type | wrong grant_type value |
| 403 | forbidden | app token refresh too early | refreshing app token <5 min after last |

## Auth Usage Errors (API calls with bad/expired auth)

| HTTP | type | value | meaning |
|------|------|-------|---------|
| 403 | oauth | bad_authorization | token invalid/missing |
| 403 | oauth | token_expired | access_token expired → refresh it |
| 403 | oauth | token_revoked | user revoked token |
| 403 | oauth | application_not_found | app was deleted |
| 403 | oauth | user_auth_expected | app token used where user token required |

## Captcha

Some operations protected by captcha. Response:

```json
{
  "type": "captcha_required",
  "value": "captcha_required",
  "fallback_url": "https://hh.ru/...",
  "captcha_url": "https://hh.ru/account/captcha?state=...&backurl=..."
}
```

`backurl` param required in `captcha_url` — must include scheme (`https://`).

## Rate Limit Observations (Live Testing Apr 2026)

- `/vacancies` endpoint: **~10-15 requests → IP banned**
- Ban duration: **3+ minutes** (tested 65s and 180s — still blocked after both)
- No `X-RateLimit` headers in responses
- `/dictionaries`, `/areas`, `/industries` — much more tolerant
- 403 responses during ban: `{"errors":[{"type":"forbidden"}]}`
- With app token: significantly higher limits (exact numbers TBD after approval)

## Two Hermes Instances

On this machine there are two Hermes data stores:
- **Local**: `~/.hermes/` (current agent)
- **Guest Docker**: `~/hermes-instances/guest/data/` (hermes-guest container, mounted at `/opt/data` inside)

Skills are **separate** between instances. Guest has categories not in local: `apple/`, `travel-planning`, `inference-sh`, `diagramming`. Local has categories not in guest: `flight-search-routing`, `systemd-web-service-deployment`, `.archive`.

## App Registration Status

- Konstantin's app: "Hermes agent", #21121, redirect_uri=`https://hh.ru`
- Status: pending review (up to 15 business days)
- Register at: https://dev.hh.ru/admin