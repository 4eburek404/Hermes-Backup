# SearXNG Self-Hosted Setup — Konstantin's Instance

## Instance Details

- **Host**: localhost:8888 (127.0.0.1 only)
- **Docker image**: searxng/searxng:latest
- **Container name**: searxng
- **Config volume**: `~/.searxng/settings.yml` → `/etc/searxng/settings.yml:ro`
- **Restart policy**: unless-stopped

## settings.yml

```yaml
use_default_settings: true

general:
  instance_name: "SearXNG Local"
  debug: false

search:
  default_lang: "ru-RU"
  formats:
    - html
    - json
  safe_search: 0

server:
  secret_key: "searxng-local-2026"
  limiter: false
  image_proxy: true
  port: 8080
  bind_address: "0.0.0.0"

ui:
  static_use_hash: true

engines:
  - name: google news
    engine: google_news
    shortcut: gnews
    disabled: false

  - name: bing news
    engine: bing_news
    shortcut: binews
    disabled: false

  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg
    disabled: false

  - name: yahoo
    engine: yahoo
    shortcut: ynews
    disabled: false
    categories: [news]

  - name: reuters
    engine: reuters
    shortcut: reu
    disabled: false
    categories: [news]

outgoing:
  request_timeout: 10
  max_request_timeout: 15

preferences:
  lock:
    - language
    - safe_search
```

## Pitfalls Encountered

1. **Engine names must be lowercase** — using `Google News` (capitalized) causes crash: `Engine config error: ambiguous name: google news`. Use lowercase `google news`.
2. **limiter: false** — required for localhost; without it, SearXNG may rate-limit even local requests.
3. **Bind to 127.0.0.1** — the docker `-p 127.0.0.1:8888:8080` ensures no external access.
4. **Container internal port is always 8080** — the `port` setting in settings.yml is the internal port (don't change to 8888).
5. **Missing limiter.toml warning** — harmless: `missing config file: /etc/searxng/limiter.toml` appears when limiter is disabled.
6. **wikidata engine error** — `KeyError: 'name'` on startup is non-critical; wikidata just won't be available.
7. **Public instances unreliable** — tested 5 public SearXNG instances, all returned 403/429/empty for JSON API. Self-hosting is the only working path.

## Command Reference

```bash
# Start
docker start searxng

# Stop
docker stop searxng

# Restart
docker restart searxng

# View logs
docker logs searxng --tail 20

# Rebuild after config change
docker rm -f searxng
docker run -d --name searxng --restart unless-stopped \
  -p 127.0.0.1:8888:8080 \
  -v ~/.searxng/settings.yml:/etc/searxng/settings.yml:ro \
  searxng/searxng:latest
```

## Query Examples

```bash
# Russian news (JSON)
curl -s "http://localhost:8888/search?q=новости+Россия&categories=news&language=ru&format=json"

# Topic search
curl -s "http://localhost:8888/search?q=Иран+США&categories=news&language=ru&format=json"

# General web search (not just news)
curl -s "http://localhost:8888/search?q=SearXNG+setup&language=en&format=json"
```

## Tested Comparison (2026-05-04)

### Query: "новости 4 мая 2026" (Russian, news category)

**Google News RSS:**
- 15 top articles with precise headlines and timestamps
- Sources: Интерфакс, Ведомости, BBC, Meduza, DW, Фонтанка
- All relevant, fresh, with exact GMT timestamps
- Focus on significant political/military topics

**SearXNG (self-hosted, localhost:8888):**
- 21 results from 5 engines: startpage news, duckduckgo news, bing news, wikinews
- 5 engines failed: brave (rate limit), qwant (crash), yahoo (protocol error), karmasearch (denied)
- `publishedDate` is `null` for most startpage/bing/ddg results (aggregator pages)
- Wikinews provides dates but articles are niche
- Results are broader but less precise: generic "новости за 4 мая" pages instead of specific headlines

### Summary Table

| Criterion | Google News RSS | SearXNG (self-hosted) |
|---|---|---|
| Headline precision | ✅ Specific articles | ⚠️ Many aggregator pages |
| Publication dates | ✅ Always present | ⚠️ Often null |
| Source diversity | Google News only | 3-5 engines (some fail) |
| Format | XML/RSS | ✅ JSON API |
| Setup effort | Zero | Docker + config |
| Privacy | Google logs queries | ✅ Fully self-hosted |
| General search | News only | ✅ Web, images, etc. |