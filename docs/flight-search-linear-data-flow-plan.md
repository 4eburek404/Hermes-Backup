# Flight Search: линейный поток данных

## Статус

План реализован в ветке `refactor/flight-search-linear-data-flow`.

- request: `flight_search_request.v1`;
- plan: `flight_search_plan.v2`;
- result: `flight_search_result.v6`;
- answer: `flight_search_user_answer.v8`;
- trace: `flight_route_trace_diagnostic.v2`;
- skill: `0.11.0`;
- CLI: `0.8.0`.

## Production flow

```text
raw JSON
  -> SearchRequest
  -> SearchPlan
  -> SearchExecutor.execute(plan)
  -> SearchEvidence
  -> SearchDecision
  -> FlightSearchResult
  -> pure render
  -> stdout
```

Defaults применяются только в `SearchRequest.from_payload()`. Planning не
обращается к провайдерам. Execution выполняет primary probes, pure fallback
assessment, не более одной fallback wave, заранее запланированные evidence
probes, одно завершение ledger и один freeze evidence.

Ledger индексирован уникальным `probe_id`; полный logical query key отвечает за
dedupe. Terminal state не переоткрывается, а cache status хранится отдельно.
Provider result содержит одно поле `offers`.

После freeze один раз строятся OfferGraph, единый candidate envelope, scoring и
DecisionFrontier. Provider aggregate, direct, RU-policy, round-trip и
two-one-way варианты проходят этот же decision path. Result projection и
renderer не создают, не удаляют и не переставляют варианты.

## Public output

`flight_search_result.v6` содержит ровно:

```text
schema_version
request
route
evidence
frontier
answer
```

`frontier.option_ids` и порядок catalog IDs обязаны совпадать. Единственный
текст — `answer.rendered_text`. Text stdout равен этому полю плюс один terminal
newline. Structured catalog не хранит текстовые зеркала.

Schema validation защищает request, plan, result, answer, graph и diagnostic
trace. Внутренние evidence/decision типы защищаются Python models, semantic
validation и subprocess tests. `$ref` разрешаются только через packaged local
registry.

Semantic validation проверяет route/request consistency, frontier/catalog IDs,
round-trip completeness, segment continuity и chronology, offset-aware
timestamps, layovers, currency, ledger/evidence counts, caveats и точное
повторное pure rendering.

## Acceptance

- полный offline suite;
- Ruff, format check, pyflakes, vulture и compileall;
- schema/resource/registry audit;
- belief-map rebuild и boundary audit;
- реальный subprocess E2E с локальным stdlib Tutu MCP stub;
- text/JSON equivalence и пустой success stderr;
- один provider call на logical query;
- source live smoke `SVX→FRA 2026-08-10` и `NTE→SVX 2026-07-23`;
- `maint doctor` и `maint check`;
- repo-wide reference audit и push текущей ветки.

Исходная fixture-дата `2026-07-09` стала прошлой относительно даты реализации
`2026-07-11`, поэтому strict request validation закономерно её отклоняет.
Subprocess fixture использует `2026-07-23`, сохраняя тот же маршрут и сегменты
`KL1424`, `KL1959` и `IST→SVX`.
