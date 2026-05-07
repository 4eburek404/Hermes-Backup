# Infrastructure

Назначение: карта устойчивой AI/Hermes-инфраструктуры Константина. «Что у нас есть, где лежит, какие инварианты». Процедуры — в `runbooks.md`, навыки — в Hermes skills.

## System map

```text
Telegram DM
   ↓
Hermes Gateway
   ↓
Hermes Agent (~/.hermes/hermes-agent)
   ├── built-in memory: ~/.hermes/memories/
   ├── config: ~/.hermes/config.yaml
   ├── auth: ~/.hermes/auth.json
   ├── sessions/search: ~/.hermes/state.db / session store
   ├── cron jobs
   ├── skills
   └── providers/models
        ├── Ollama custom/local endpoint
        └── OpenAI Codex OAuth provider
```

## Stable paths

| Purpose | Path |
|---|---|
| Hermes project/source | `/home/konstantin/.hermes/hermes-agent` |
| Main config | `/home/konstantin/.hermes/config.yaml` |
| Hermes OAuth/auth store | `/home/konstantin/.hermes/auth.json` |
| Codex CLI auth source | `/home/konstantin/.codex/auth.json` |
| Gmail App Password | (see himalaya config) |
| Google Calendar SA key | (see gcal section below) |
| Long term docs | `/home/konstantin/docs/` |

## Providers and models

### Ollama / custom endpoints

- `ollama-local`: OpenAI-compatible path, `http://127.0.0.1:11434/v1`, Hermes `chat_completions`. This remains the default/local compatibility provider and must not be silently repointed to native `/api/chat`.
- `ollama-native`: native Ollama path, `http://127.0.0.1:11434`, Hermes `api_mode: ollama_native_chat`, default model `glm-5.1:cloud`. Core provider support landed in Hermes Agent branch `fix/ollama-native-chat-provider`, commits `764731bad` and `f76e76b5d`.
- Models shown in Hermes `/model` for the compatibility path are configured under `providers.ollama-local.models` in `~/.hermes/config.yaml`; native model tags are configured under `providers.ollama-native.models`.
- Cron/model pinning should specify the intended provider path explicitly. Use `ollama-local` for `/v1` compatibility semantics; use `ollama-native` only when the caller expects native `/api/chat` fields (`format`, `think`, `options.num_predict`, `message.content`).
- **Verify exact tags before adding.** Example: `gemma4:cloud` invalid; correct = `gemma4:31b-cloud`.

Compatibility configured models: `glm-5.1:cloud`, `deepseek-v4-flash:cloud`, `deepseek-v4-pro:cloud`, `kimi-k2.6:cloud`, `gpt-oss:120b-cloud`, `gpt-oss:20b-cloud`, `gemma4:31b-cloud`.
Native provider has a larger verified cloud-tag list in `providers.ollama-native.models`; do not guess tags from model family names.

### OpenAI Codex provider

- Codex CLI at `/usr/bin/codex`, version `codex-cli 0.125.0`.
- Hermes expects credentials under `providers.openai-codex` in `~/.hermes/auth.json`. Top-level key = wrong shape (caused past failures).
- **Security:** never print/save OAuth token values; only verify key presence.

## Development repositories and deployed apps

### GitHub access (verified 2026-04-30)

- Authenticated as `4eburek404`; HTTPS + `gh` token.
- Token scopes: `read:org`, `repo`, `workflow`.
- Global git identity: `user.name=4eburek404`, `user.email=app.in.the.air.2020@gmail.com`.
- **Security:** do not print/document GitHub token values; refer to `gh` CLI config.

### Server Monitor dashboard / iOS app

- Repo: `/home/konstantin/github_repo/server_monitor_iOS_app` (GitHub: `4eburek404/server_monitor_iOS_app`).
- Production: `/home/konstantin/dashboard`.
- Auth: Flask login/session (web), HTTP Basic Auth (API/WebSocket/native), iOS Keychain (client).
- Tailscale Funnel may expose login page; Tailscale web login is not the access gate.
- Holographic metrics card: fact counts/growth/categories, slow cache (default 6h, min 300s, env `SERVER_MONITOR_HOLOGRAPHIC_REFRESH_SECONDS`). Fact `content` not exposed.
- Hermes session card: distinguishes recent active from stale SessionDB rows. Default 6h threshold, env `SERVER_MONITOR_HERMES_OPEN_SESSION_RECENT_SECONDS`, min 300s.
- Docker card: guest Hermes container names `hermes-guest`, `hermes-guest-dashboard`; env `SERVER_MONITOR_HERMES_GUEST_DOCKER_CONTAINERS`.
- **Credentials** belong in service/runtime config only — not in repo/docs/chat.
- For deployment/API details, read repo `AGENTS.md` before changing the app.
- High `open sessions` = diagnostic clue, not proof of stuck processes; verify live processes.

### Travelpayouts flight search plugin

- Path: `/home/konstantin/.hermes/plugins/travelpayouts-flights/`.
- Name: `travelpayouts-flights`; tool: `travelpayouts_flight_search`; toolset: `travelpayouts`.
- Advisory price search only; no booking. Auth via `TRAVELPAYOUTS_TOKEN` from `~/.hermes/.env` (header, not URL param; never print value).
- Plugin/tool changes need new session or gateway restart.
- API returns cached prices; always recheck on aggregator/airline site before purchase.

### Selected productivity skills

- `flight-search-routing`: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md` — multi-segment flight search and hub-routing analysis.
- `hh-ru`: `/home/konstantin/.hermes/skills/productivity/hh-ru/SKILL.md` — hh.ru vacancies, employers, salary statistics, OAuth notes, and API rate-limit handling.

## Active automations

### Morning weather cron

| Field | Value |
|---|---|
| Name | `Погода Верхняя Салда — каждое утро` |
| Job ID | `f4a74c81f4c0` |
| Schedule | `0 3 * * *` host time |
| User time | 06:00 UTC+5 |
| Model | `glm-5.1:cloud` / `ollama-local` |
| Toolsets | `terminal`, `web` |

Fetches Open-Meteo current + daily forecast, formats compact Russian emoji report. Model chosen after benchmark: best balance for short Telegram weather. Recovery: recreate from this section + runbook.

### Daily knowledge distillation cron

| Field | Value |
|---|---|
| Name | `Ежедневная дистилляция знаний` |
| Job ID | `62e7a25f4e15` |
| Schedule | `0 18 * * *` host time |
| User time | 21:00 UTC+5 |
| Model | `gpt-5.5` / `openai-codex` |
| Skill | `daily-knowledge-distillation` |
| Toolsets | `session_search`, `file`, `terminal`, `web`, `memory` |

Curates useful knowledge into `/home/konstantin/docs/` and atomic facts into `fact_store`. Workers: `glm-5.1:cloud`, `gemma4:31b-cloud`. `deepseek-v4-pro:cloud` is excluded from the production worker pool because prior benchmark notes about “unsuitable as primary/full prompt” were repeatedly reintroduced as “best worker” guidance. Fallback curator: `gpt-oss:120b-cloud`.

### Gmail daily digest cron

| Field | Value |
|---|---|
| Name | `gmail-daily-digest` |
| Job ID | `e6bf264768e7` |
| Schedule | `0 5 * * *` host time |
| User time | 08:00 UTC+5 |
| Model | `gemma4:31b-cloud` / `ollama-local` |
| Skill | `himalaya` |
| Toolsets | `terminal`, `file` |

### Calendar daily digest cron

| Field | Value |
|---|---|
| Name | `calendar-daily-digest` |
| Job ID | `8018f1559f5d` |
| Schedule | `0 3 * * *` host time |
| User time | 06:00 UTC+5 |
| Model | `glm-5.1:cloud` / `ollama-local` |
| Skill | `google-workspace` |
| Toolsets | `terminal`, `file` |

### Gmail via Himalaya

- CLI v1.2.0, `~/.local/bin/himalaya`.
- Account: `gmail` (default), `ks.orlov@gmail.com`. Auth: Gmail App Password (chmod 600).
- Config: `~/.config/himalaya/config.toml`.
- IMAP: `imap.gmail.com:993` TLS; SMTP: `smtp.gmail.com:587` STARTTLS.
- Russian locale folder names: `[Gmail]/Корзина` (Trash), `[Gmail]/Спам` (Spam).

### Google Calendar via service account

- SA: `hermes-calendar@formidable-feat-492812-e9.iam.gserviceaccount.com`.
- Key: protected path (chmod 600); exact path not documented here.
- Calendar ID: `ks.orlov@gmail.com`. Project: `formidable-feat-492812-e9`.
- SA has `writer` ACL. Digest jobs may intentionally use `calendar.readonly` scope.
- Access: Python `google-api-python-client` + `google.oauth2.service_account.Credentials`. CalDAV via App Password does NOT work for Google Calendar.

## n8n

- Docker container (`n8nio/n8n:latest`, port 5678, SQLite backend).
- Data bind mount: `/home/konstantin/n8n/data` → `/home/node/.n8n`; n8n runs as UID 1000, so the host data directory must be owned by `1000:1000`.
- No `WEBHOOK_URL`; no production workflows yet.
- Suitable for deterministic trigger→action; analytical tasks (complex flight search) better handled by Hermes.

## Default model

- `model.default = glm-5.1:cloud`, `model.provider = ollama-local`.
- Pinned cron jobs ignore this default.

## Memory architecture

- Built-in Hermes memory: active (push, auto-injected).
- Holographic (local): active at `~/.hermes/memory_store.db` (pull, agent queries via `fact_store`).
- `auto_extract: false` — manual curation only.
- `on_memory_write()` hook mirrors `memory add` calls into holographic.
- Other installed providers (not active): byterover, honcho, mem0, openviking, retaindb, supermemory.

## Operational risks

- **Timezone:** cron uses host timezone, not user UTC+5. Always check `date` before cron work.
- **Memory sprawl:** don't dump session results into docs; use `session_search` for history.
- **Secret leakage:** never put credential values or exact secret-file paths in docs/chat.