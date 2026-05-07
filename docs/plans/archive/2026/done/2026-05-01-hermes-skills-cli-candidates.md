# Plan: Hermes Skills CLI Candidates

## Goal

Зафиксировать список локальных Hermes skills, из которых рационально делать отдельные CLI.

Источник анализа: локальная установка Hermes `~/.hermes`, не Docker-инстанс.

## CLI Candidates

### 1. `productivity/hh-ru`

Приоритет: высокий.

Почему CLI:
- skill уже описывает REST API `hh.ru`, auth, rate limits, справочники, вакансии и работодателей;
- много повторяемой механики: токены, backoff, area lookup, structured Telegram/JSON output;
- CLI снизит риск банов и ошибок с region IDs.

Возможные команды:
- `hh search`
- `hh vacancy`
- `hh employer`
- `hh areas`
- `hh dictionaries`
- `hh auth status`

### 2. `productivity/flight-search-routing`

Приоритет: высокий.

Почему CLI:
- skill уже содержит правила multi-segment routing и airport compatibility;
- Travelpayouts/cache search удобнее нормализовать в коде, чем каждый раз собирать вручную;
- отдельная проверка self-transfer, airport mismatch и connection time хорошо ложится в deterministic CLI.

Возможные команды:
- `flights route`
- `flights segment-search`
- `flights validate-connection`
- `flights compare-hubs`
- `flights render --format json|md`

### 3. `note-taking/knowledge-architecture`

Приоритет: средний.

Почему CLI:
- внутри уже есть `scripts/distillation_worker.py`;
- worker logic для candidates, JSON parsing, dedup и vote counting лучше запускать как стабильную команду;
- mutation docs/fact_store лучше оставить агенту, а CLI сделать read-only/candidate-producing.

Возможные команды:
- `knowledge distill-candidates --input snippets.txt`
- `knowledge format-curator`
- `knowledge audit-docs --dry-run`

### 4. `research/web-article-reader`

Приоритет: средний-низкий.

Почему CLI:
- текущий skill предлагает `curl | python3`, что хрупко и неудобно;
- HTML extraction, fallback на `<body>`, cleanup и markdown/json output лучше сделать одной командой;
- сохранение в memory не должно быть default-действием CLI.

Возможные команды:
- `article read URL --format md|json`
- `article extract URL`
- `article summary-input URL`

### 5. `devops/systemd-web-service-deployment`

Приоритет: низкий для write CLI, средний для audit CLI.

Почему CLI:
- деплой/restart требуют контекста и осторожного агентного workflow;
- read-only audit хорошо автоматизируется: service status, unit metadata, ports, Tailscale Serve/Funnel, health/auth matrix.

Возможные команды:
- `service-audit systemd --service NAME`
- `service-audit ingress`
- `service-audit health --url URL`

## Not Recommended As Separate CLI

- `docs-review` — поглощён `knowledge-architecture`.
- `holographic-memory-hygiene` — поглощён `knowledge-architecture`; mutating memory лучше оставлять агенту.
- `konstantin-plan-governance` — поглощён `knowledge-architecture`; это policy/procedure, не CLI.
- `daily-knowledge-distillation` — функционально часть `knowledge-architecture`; отдельным CLI имеет смысл выносить только worker/candidate stage.
- `mcp/native-mcp` — уже покрывается существующим Hermes CLI: `hermes mcp add/list/test/configure/serve`.

## Status
Current status: done

## Notes

Этот список относится к локальным runtime skills в `~/.hermes/skills`. Docker Hermes skills сюда не включались.

Closed 2026-05-03: кандидаты высокого/среднего приоритета реализованы как локальные CLI в `[legacy CLI path removed; current source is the development repo skills tree]/`: `article`, `flights`, `hh-ru`, `knowledge`. `flights` version drift исправлен до 0.7.0; `hh-ru` response header redaction усилен для cookie-like headers. Durable current facts перенесены в fact_store.
