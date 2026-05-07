---
name: hh-ru
description: Search vacancies, employers, and reference data via hh.ru public API. Handles rate limits, auth, and structured output for Telegram.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hh.ru, vacancies, jobs, employers, russia, labor-market, api]
    related_skills: []
---

# hh.ru API Skill

Search Russian labor market data via hh.ru public REST API (`https://api.hh.ru`).

## When to Use

- User asks about job vacancies, salary ranges, employer info, or labor market data in Russia/CIS
- User needs to research demand for a profession, compare salaries by region, or find specific employers
- User asks about specializations, industries, or career paths in Russia

## API/Auth Reference

Detailed OAuth flows, endpoint lists, dictionaries, area IDs, salary-statistics IDs, and request shapes live in `references/api-reference.md`.

Core invariants to keep in the instruction path:

- Always send a non-empty `User-Agent`; hh.ru rejects unset/blacklisted agents.
- Without a token, `/vacancies` can hit a 403/IP-ban after ~10–15 requests for 3+ minutes; stop and back off instead of retry-hammering.
- Resolve `area` from live `/areas/113` or `/suggests/areas`; do not rely on hardcoded city IDs.
- Salary-statistics area IDs (`10001` etc.) are a separate ID space from vacancy `area` IDs.
- Use `professional_role` instead of legacy `specialization` for public role filtering.
- Currency is usually `RUR`, not `RUB`; report gross/net when `salary.gross` is present.
- Prefer the local `hh-ru` CLI when available; examples live in `references/request-examples.md`, and a minimal smoke client lives in `scripts/hh_ru_api_smoke.py`.

## Steps

1. **Clarify query** — what profession, which city/region, experience level, salary range, employment type, remote/onsite.
2. **Build request** — use appropriate area ID, text query, and filters. For salary comparison, make parallel requests with different area IDs.
3. **Execute search** — call `/vacancies` conservatively (`per_page=20-50` for normal use, smaller for smoke tests). If it returns `403 {"type":"forbidden"}`, treat it as rate-limit/IP-ban evidence: stop repeated vacancy calls, report the limitation, wait/back off, or use a configured token instead of hammering the endpoint.
4. **Get details** — for top results, fetch `/vacancies/{id}` for full description and key_skills.
5. **Analyze & summarize** — group by salary bands, highlight demand trends, compare across regions.
6. **Present results** — structured markdown, no wide tables (Telegram compatibility). Use labeled key-value pairs.

## Output Format

Deliver as structured markdown. For vacancy lists:
- **Title + employer + salary range**
- Key requirements as bullet list
- Link to full vacancy on hh.ru

For salary research:
- Salary distribution by experience level
- Regional comparison (min/avg/max)
- Trend notes

## Pitfalls

- **Rate limits are much worse than documented.** Without token: ~10-15 requests to `/vacancies` then 3+ minute IP ban. Dict/reference endpoints are more tolerant. After ban, exponential backoff with 180+ second initial wait.
- **Area IDs overlap.** City IDs are nested inside region IDs inside country 113. Always verify by requesting `/areas/113` and matching by name, not by hardcoded ID.
- **Salary area IDs ≠ regular area IDs.** `/salary_statistics` uses macro-region IDs (10001, 10002...) — different from `/areas` city IDs. Do NOT mix them.
- **Salary data is incomplete.** ~50% of vacancies don't publish salary. Always note sample size and bias.
- **Descriptions are HTML.** The `description` field contains raw HTML. Strip tags before presenting.
- **`professional_roles` replaces `specializations`.** Use `/professional_roles` (public) instead of `/specializations` (auth required). Pass `professional_role` param in vacancy search.
- **Currency is RUR** (not RUB). Salaries may be in other currencies (USD, EUR) — check `salary.currency` field. Currency dict has `rate` field for conversion.
- **Gross/net.** hh.ru salaries are typically gross (before tax). `salary.gross` field = true means gross. Note this in output.
- **`/salary_statistics/paid/salary_evaluation` requires payment.** The "paid" in the path means it's a paid service — requires employer account with active subscription.
- **Two area systems:** `/areas` for vacancy filtering, `/salary_statistics/dictionaries/salary_areas` for salary data. Different ID spaces.
- **User-Agent is required.** Without it → 400 `bad_user_agent: unset`. Blacklisted UAs → 400 `bad_user_agent: blacklisted`.
- **`employment_type` vs `employment_form` vs `schedule`** — three different filters! `employment_type` (full/part/project), `employment_form` (FULL/PART/PROJECT/FLY_IN_FLY_OUT/SIDE_JOB), `schedule` (fullDay/shift/flexible/remote/flyInFlyOut). Check which param the endpoint expects.
- **`business_trip_readiness`** filter available if relevant to query (ready/sometimes/never).
- **Currency code is `RUR`** (not `RUB`). Some endpoints use `RUR`, others may accept `RUB` but prefer `RUR`.
- **Authorization code is single-use and short-lived.** Must exchange immediately. Reuse → error `code has already been used`.
- **Refresh token is single-use.** Using it twice → error `token has already been refreshed`. Always store the NEW pair after refresh.
- **App approval takes up to 15 business days.** Plan ahead.
- **App token refresh limited to 1 per 5 minutes.** Faster → 403 `app token refresh too early`.
- **Local `hh-ru` CLI output must redact response cookies as well as request auth.** In the 2026-05-03 CLI audit, `hh-ru --json roles` returned HTTP 200 but included a `Set-Cookie` response header in the JSON envelope. Treat response headers as potentially sensitive: redact `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, and API-key-like headers before printing or relaying tool output.

## Verification Checklist

Before presenting hh.ru results as evidence:

- [ ] Every HTTP request includes a non-empty `User-Agent`; hh.ru can reject unset/blacklisted agents with `400 bad_user_agent`.
- [ ] If `/vacancies` returns `403 {"type":"forbidden"}`, stop repeated vacancy calls; report rate-limit/IP-ban state, wait/back off, or use a configured token instead of hammering the endpoint.
- [ ] Region filters were resolved from live `/areas/113` or `/suggests/areas`, not from stale hardcoded IDs.
- [ ] Salary-statistics area IDs (`10001` etc.) were not mixed with regular vacancy area IDs (`1`, `45`, etc.).
- [ ] Vacancy descriptions had HTML stripped before user-facing output.
- [ ] Salary analysis states sample size and bias: many vacancies have `salary: null`.
- [ ] Salary output states currency (`RUR` by default) and gross/net when `salary.gross` is present.
- [ ] API status and source freshness are explicit when results are limited by rate limits, auth, or paid endpoints.
- [ ] If using the local `hh-ru` CLI, response headers are sanitized before user-facing relay; do not expose `Set-Cookie`, `Cookie`, `Authorization`, `Proxy-Authorization`, or API-key-like header values.

## Reference Files

- `references/oauth-and-errors.md` — OAuth token exchange errors, auth usage errors, captcha handling, rate limit observations from live testing, two-instance note, app registration status.
- `references/request-examples.md` — cURL and local CLI request examples, kept out of the instruction core.
- `scripts/hh_ru_api_smoke.py` — small reusable Python smoke client with redacted headers and optional `HH_RU_TOKEN`.
