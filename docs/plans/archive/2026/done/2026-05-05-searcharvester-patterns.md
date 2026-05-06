# Plan: применить паттерны Searcharvester к Hermes skills и orchestration

## Goal

Перенести из Searcharvester проверенные паттерны, которые повышают достоверность web/delegate_task-работы и устойчивость оркестрации Hermes:

- снизить галлюцинации в research/flight/web skills;
- заставить сабагентов работать с актуальной датой, а не с training-memory;
- фиксировать grounding через файловые side effects;
- отделить методологию skills от механики scripts;
- сохранить архитектурные паттерны для будущего UI/оркестрации над ACP.

## Context

Источник анализа: `https://github.com/vakovalskii/searcharvester`.

Remote freshness check, проверено 2026-05-05:

- GitHub repo: `vakovalskii/searcharvester`, default branch `main`.
- Latest remote commit: `5afa68b` — `Detect hallucinated URLs by cross-checking extracts/ on disk`.
- Локальная копия `/home/konstantin/searcharvester` совпадает с remote latest commit.
- GitHub tags/releases/open PRs на момент проверки не найдены.
- Open issue #1 про frontend/API `localhost`/CORS при открытии UI с другого хоста; релевантно только для будущей UI/P3-работы, не меняет P0/P1 приоритеты текущего плана.

Локальная копия для проверки:

```text
/home/konstantin/searcharvester
```

Проверенные референсы в локальном коде Searcharvester:

- `hermes_skills/searcharvester-deep-research/SKILL.md` — двухраундовый пайплайн researcher → critic/fact-checker; skill как методология без кода.
- `simple_tavily_adapter/orchestrator.py` — свежая дата в `_mandatory_suffix()`, запуск `hermes acp` с `cwd=job.workspace_path`, `_Forwarder(Client)`, backfill из session-файлов, grounding-check через `./extracts/`.
- `simple_tavily_adapter/events.py` — flat event schema поверх ACP.
- `simple_tavily_adapter/main.py` — `_job_phase()` по артефактам `plan.md → notes.md → report.md`.

Предыдущая версия этого файла была архитектурной заметкой. Теперь файл нормализован как активный план в `/home/konstantin/docs/plans/`; durable результаты после выполнения нужно перенести в skills/runbooks/docs/fact_store, а сам план закрыть и архивировать по policy.

## Non-goals

- Не менять исходный репозиторий Searcharvester в рамках этого плана.
- Не строить новый UI/дашборд над ACP прямо сейчас.
- Не внедрять Docker/container isolation как обязательное требование; `cwd=job_dir` фиксируется как lightweight pattern для subprocess-запусков.
- Не превращать все skills в deep-research; двухраундовая схема нужна только там, где достоверность фактов важнее скорости.
- Не сохранять сырые session logs, credential data или полные transcripts в docs/plans.

## Steps

Ранжирование ниже — по полезности **здесь и сейчас**: максимум снижения ошибочных ответов в текущих Hermes skills при минимальной стоимости внедрения. Критерии: impact на достоверность, частота применения, effort, blast radius и наличие прямого текущего потребителя (`flight-search-routing` / web/API / delegate_task workflows).

Initial target skills for P0/P0.5:

- `productivity/flight-search-routing` — verifier-gate for critical travel facts, source/cached/live caveats.
- `software-development/subagent-driven-development` — mandatory date/current-context preamble in delegated task context; progress artifacts for multi-step work.
- `software-development/requesting-code-review` — structured reviewer handoff where applicable.
- Web/research/source-reading skills touched next — artifact/grounding contract when they make URL/API-backed claims.

### P0 — внедрить первым: дешёвые guardrails с максимальным эффектом

- [x] **P0.1 Date/current-context injection для каждого `delegate_task` context.** Внедрено в `subagent-driven-development`: каждый сабагент получает явную первую строку `CURRENT CONTEXT` с датой/границами задачи; для web/flight/research/current tasks добавлено требование live/fresh sources вместо stale training-memory.
- [x] **P0.2 Grounding через файловые/API side effects.** Внедрено в web/API/source skills: `flight-search-routing`, `web-article-reader`, `news-search`, `youtube-content`, `arxiv`, `blogwatcher`, `polymarket`; claims требуют `./extracts/`, `./api_responses/`, `./queries/` или эквивалент, иначе label `ungrounded`.
- [x] **P0.3 Минимальный verifier-gate для `flight-search-routing`.** Добавлен gate по actual airports, connection buffers, dates/timezones, carrier/source, price/cache caveat, visa/self-transfer/baggage risk.
- [x] **P0.5 Progress artifacts для already multi-step/delegate workflows.** Внедрено в `subagent-driven-development` и source/research skills: `plan.md → notes.md → report.md` для multi-step/delegate/high-stakes workflows; single-shot lookups explicitly skip overhead.

### P1 — условная эскалация: высокая польза, но больше latency/стоимости

- [x] **P1.1 Two-round `researcher → verifier/critic/fact-checker` для high-stakes задач.** Внедрено как conditional escalation: `flight-search-routing`, `requesting-code-review`, `news-search`, `polymarket` требуют `researcher_summary`, `facts_to_verify` и artifact paths для Round 2; blind critic explicitly insufficient.

### P2 — внедрять при следующем касании соответствующих skills/docs

- [x] **P2.1 Разделить методологию и механику.** Deferred by scope: текущие правки добавили decision/verification contract в SKILL.md; глубокое вынесение HTTP/API/CLI механики в `scripts/` оставлено до следующего касания каждого конкретного skill, чтобы не раздувать blast radius.
- [x] **P2.2 Session-файлы как recovery source.** Внедрено в `subagent-driven-development`: при `(empty)`, truncation или unverifiable success сначала recovery из concrete artifacts, затем Hermes session files при необходимости.
- [x] **P2.3 `cwd=job_dir` workspace isolation для subprocess-агентов.** Deferred: актуальный execution scope — `delegate_task`/skills/docs, не программный запуск `hermes acp`; зафиксировано в runbook as future UI/ACP/orchestration pattern.

### P3 — отложить до реальной UI/orchestration задачи

- [x] **P3.1 Flat event schema между ACP и UI/SSE.** Deferred by design: UI/дашборд над сабагентами не входит в текущий scope; оставлено для отдельной UI/orchestration задачи.
- [x] **P3.2 Custom ACP Client middleware.** Deferred by design: `_Forwarder(Client)` / permission-blocking / event filtering / rate limiting нужны только при программном использовании ACP, не как обязательный skill-паттерн.

### Closing

- [x] После P0/P1 правок синхронизировать source skills и installed/runtime skills, если у конкретного проекта есть split вроде `hermes_skills/` vs `hermes-data/skills/`.
- [x] Проверить, какие изменения стали durable knowledge и куда их перенесли: skills, `runbooks.md`, `infrastructure.md` или fact_store.
- [x] Обновить `## Verification` результатами фактической проверки.
- [x] Поставить `Current status: done` или `cancelled/superseded`.
- [x] Перенести файл в `archive/2026/<status>/`.

## Verification

План считается выполненным, когда:

- **P0 выполнен первым** или явно задокументировано, почему отдельный P0 пункт пропущен.
- Initial target skills из `## Steps` проверены и либо обновлены, либо для каждого оставлен explicit skip/defer reason.
- В delegate_task skills есть date/current-context preamble rule для каждого сабагента; для web/flight/research задач правило требует fresh-source verification вместо stale training-memory.
- В web/API/scrape skills есть artifact/grounding contract: claims с URL/API data должны ссылаться на side-effect files в рабочем каталоге; missing artifact явно понижает claim до ungrounded.
- В `flight-search-routing` добавлен verifier-gate для critical travel facts: airports, connection buffers, carrier/date/price source, cache/live caveat.
- Для high-stakes задач описан two-round `researcher → verifier/critic/fact-checker` pipeline, где Round 2 получает `researcher_summary` и `facts_to_verify` из первого раунда.
- Для multi-step/delegate workflows зафиксированы progress artifacts (`plan.md → notes.md → report.md` или эквивалент).
- P2/P3 паттерны либо перенесены в правильный durable layer (`runbooks.md`, infrastructure/docs, skill references, fact_store), либо явно оставлены deferred с причиной.
- Root `/home/konstantin/docs/plans/` после закрытия не содержит этот файл со статусом `done/superseded/cancelled`.

Execution verification, 2026-05-05:

- Updated installed/runtime skills directly under `/home/konstantin/.hermes/skills`: `flight-search-routing` 2.1.0, `subagent-driven-development` 1.2.0, `requesting-code-review` 2.1.0, `web-article-reader` 1.1.0, `news-search` 1.1.0, `youtube-content` 1.1.0, `arxiv` 1.1.0, `blogwatcher` 2.1.0, `polymarket` 1.1.0.
- Python verification passed: all modified SKILL.md files have valid frontmatter/name/description; group checks passed for date/current-context, stale training-memory, artifact grounding, verifier handoff, progress artifacts, and ungrounded-claim rules.
- Durable cross-skill contract copied to `/home/konstantin/docs/runbooks.md` section `Searcharvester-derived research/delegation guardrails` and `fact_store` fact `132`.
- `/home/konstantin/searcharvester` git status verified clean.
- Hermes core repo was not modified by this plan. `git status` for `/home/konstantin/.hermes/hermes-agent` is not clean, but changed tracked files have mtimes 2026-05-01 and backup mtime 2026-04-27; this plan's writes targeted user-layer skills/docs/fact_store only.
- P2.1/P2.3 and P3 are explicitly deferred: no Hermes core, ACP middleware, UI, or Searcharvester source changes were made.
- Archive verification completed: root `plans/` no longer contains this file after move; archived copy is `/home/konstantin/docs/plans/archive/2026/done/2026-05-05-searcharvester-patterns.md`.

## Risks / pitfalls

- **Overengineering:** двухраундовая схема дороже и медленнее; она не должна стать default path для простых lookups.
- **Two-round escalation criteria:** включать полноценный `researcher → verifier` только когда есть деньги/покупка/non-refundable decision, даты/deadlines/стыковки, airport identity, visa/self-transfer/baggage risk, конфликтующие источники, неполные API/cache results или явная просьба пользователя проверить особенно тщательно.
- **Two-round kill criteria:** для простых lookup-задач ограничиваться date/current-context preamble + grounding artifacts; blind critic без `researcher_summary` и `facts_to_verify` не считать верификацией.
- **False confidence:** наличие URL в ответе не равно grounding; нужен artifact на диске или другой проверяемый side effect.
- **Stale date:** дата в parent prompt не гарантирует дату в subagent context.
- **Layer drift:** если оставить выводы только в этом плане, они выпадут из исполняемых workflows.
- **Runtime split:** в некоторых проектах source skills и runtime skills лежат в разных местах; правка только source-каталога может не попасть в агентный runtime.
- **ACP coupling:** UI/дашборды, которые читают raw ACP events напрямую, станут хрупкими при смене ACP/Hermes/SDK.

## Status
Current status: done


## Notes
2026-05-05: execution started. Scope: user-layer Hermes skills/docs/fact_store only; Hermes core repo and `/home/konstantin/searcharvester` remain source/reference, not mutation targets.

2026-05-05: обновлено после internet/source-freshness анализа. Файл переименован по policy из `searcharvester-patterns.md` в `2026-05-05-searcharvester-patterns.md`; добавлены remote latest commit, target skills, P0.5 progress artifacts и escalation/kill criteria для two-round verification.

2026-05-05: pre-execution active-plan audit found blockers in installed skills: missing delegate current-context/date, stale-training-memory guardrail, cross-skill grounding contract, `researcher_summary`/`facts_to_verify` handoff, and `plan.md → notes.md → report.md` progress artifacts. These blockers were addressed during execution; see `## Verification`.


- Нормализовано из архитектурной заметки `searcharvester-patterns.md` в активный план.
- Ранжирование обновлено по принципу «что даст максимум пользы здесь и сейчас»:
  1. **P0:** date/current-context injection, filesystem/API grounding, минимальный verifier-gate для `flight-search-routing`.
  2. **P0.5:** progress artifacts для already multi-step/delegate workflows.
  3. **P1:** full two-round verification только для high-stakes задач.
  4. **P2:** methodology/scripts split, session-file recovery, `cwd=job_dir` workspace isolation — внедрять при следующем касании.
  5. **P3:** flat event schema и custom ACP Client middleware — отложить до реальной UI/orchestration работы.
- Причина ранга: P0 закрывает самые вероятные текущие ошибки — stale date, URL/API hallucination и travel-fact misverification — без тяжёлого deep-research overhead.

2026-05-05: execution completed and archived. P0/P0.5/P1 implemented in installed Hermes skills; durable guardrails copied to runbooks/fact_store; P2/P3 core/UI/ACP work deferred by scope; Searcharvester source remained clean; Hermes core had pre-existing dirty state only. Archived at `/home/konstantin/docs/plans/archive/2026/done/2026-05-05-searcharvester-patterns.md`.
