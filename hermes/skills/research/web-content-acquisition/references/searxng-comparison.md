# SearXNG vs Google News RSS — Full Comparison Data

Tested 2026-05-04. 8 test cases, Russian + English, on self-hosted SearXNG (localhost:8888).

## Quantitative Summary

| Case | G.ru | G.en | S.ru | S.ru dates | S.en | S.en dates |
|---|---|---|---|---|---|---|
| Breaking: СВО/Украина | 8 | 8 | 8 | 3/8 | 8 | 2/8 |
| Topic: ОПЕК+ нефть | 8 | 8 | 8 | 0/8 | 8 | 0/8 |
| Local: БПЛА Москва | 8 | 8 | 8 | 4/8 | 8 | ? |
| Person: Захарова | 8 | 8 | 8 | 0/8 | 8 | ? |
| Fact-check: Туапсе | 8 | 8 | 8 | 0/8 | 8 | ? |
| Sport: Кубок Гагарина | 8 | 8 | 8 | 0/8 | 8 | ? |
| Niche: FAW Joyee | 8 | 0 | 4 | 0/4 | 2 | 1/2 |
| Broad scan | 8 | 8 | 8 | 3/8 | 8 | ? |

G = Google News RSS (always 8/8 with dates). S = SearXNG.

## Key Findings

### 1. Google News Dates: 100% Always
Every Google News RSS item has `<pubDate>`. SearXNG depends on which engine returned the result: bing/ddg/startpage rarely include dates; qwant/wikinews usually do.

### 2. Language = Different Perspective (Google News)
- Same Russian query with gl=RU/US/GB → identical results (region doesn't override language)
- Switch hl=ru → hl=en + English query → completely different sources (Axios, NYT, Reuters vs Life.ru, BBC Russia)
- This is the single most powerful knob: **switch language to get the other side's framing**

### 3. SearXNG language=en Activates Extra Engines
- `language=ru`: bing news, ddg news, startpage news (no dates, moderate quality)
- `language=en`: + qwant news, reuters (these have dates, unique articles)
- brave.news, karmasearch, yahoo: consistently unresponsive regardless of language

### 4. Niche Topics: Google RU Dominates
- FAW Joyee: Google RU = 5 specific auto-portal articles. SearXNG RU = 2–3. Google EN = 0. SearXNG EN = 1 Russian leak + 1 stale Chinese.
- Lesson: niche RU-market topics only exist in Google's RU index.

### 5. SearXNG Unresponsive Engines (consistent)
- brave.news: "Suspended: too many requests"
- karmasearch news: "Suspended: access denied"
- qwant news: "unexpected crash" (in RU mode; works in EN mode)
- yahoo/yahoo news: "HTTP protocol error"

## SearXNG Setup Notes

- Config: `~/.searxng/settings.yml`
- Engine names MUST be lowercase (`google news` not `Google News`) or container crashes
- `limiter: false` required for localhost
- Bind `127.0.0.1:8888:8080` only
- Docker: `searxng/searxng:latest`