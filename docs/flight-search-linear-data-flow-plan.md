# Flight Search: анализ потока данных и план линейного pipeline

## Статус документа

Этот документ фиксирует анализ актуального `main` и план обновления. Рабочий код
на этом этапе не изменяется.

- Репозиторий: `4eburek404/Hermes-Backup`
- Базовый commit: `98086f7`
- Рабочая ветка: `refactor/flight-search-linear-data-flow`
- Skill: `flight-search 0.10.0`
- CLI: `flights-cli 0.7.0`
- Активные публичные контракты: request v1, result v5, agent report v5,
  user answer v7
- Базовый тестовый статус: `413 passed, 105 subtests passed`

## Цель

Сделать основной поиск билетов одной проверяемой цепочкой:

```text
request
  -> plan
  -> execute
  -> decide
  -> answer
  -> stdout
```

У каждого этапа должен быть один вход, один выход и одна ответственность. Только
этап `execute` имеет право обращаться к провайдерам. Отчётный слой не ищет,
не планирует, не ранжирует и не добавляет новые варианты.

Для агента Golden Path должен состоять из одного вызова CLI и дословной передачи
готового stdout пользователю.

## Главные выводы

1. Критический дефект границы исполнения: `build_route_trace()` вызывается
   дважды и при этом сам запускает provider/evidence operations.
2. Критический дефект единого решения: report builder добавляет варианты после
   DecisionFrontier, поэтому frontier не является фактическим источником ответа.
3. Критический дефект agent boundary: Golden Path отдаёт модели большой JSON,
   хотя CLI уже умеет печатать готовый validated text.
4. Формат ответа раздвоен на `agent_display` и `answer_display`; финальный формат
   скрывает номер рейса, часть IATA и визуальные разделители времени.
5. Request, flow, evidence и planning представлены несколькими параллельными
   объектами, часть которых сохраняет пустые поля удалённого runtime.
6. Существующие тесты покрывают слои, но не успешный полный путь от raw fixture
   до stdout и ответа агента.

## Границы задачи

В задачу входят:

- упорядочивание внутренних контрактов и владельцев данных;
- отделение provider side effects от расчётов и отчёта;
- устранение повторного исполнения одних и тех же стадий;
- единый источник вариантов, попадающих в ответ;
- однозначный формат каждого сегмента маршрута;
- сокращение активного `SKILL.md` до одного happy path;
- детерминированный CLI end-to-end тест;
- отдельная проверка границы `CLI -> агент -> пользователь`.

В задачу не входят:

- бронирование или покупка;
- новые провайдеры;
- новые пассажирские составы или классы обслуживания;
- изменение базового scope `один взрослый, эконом`;
- пересмотр всех правил ранжирования, аэропортов и допустимых пересадок без
  отдельного доказанного дефекта;
- совместимость со старыми версиями контрактов через runtime adapters.

## Фактический поток данных сейчас

### 1. Вход CLI

`commands/search.py` выполняет следующую цепочку:

```text
JSON file
  -> read_json_object
  -> normalize_search_request              dict
  -> JSON Schema validation                dict
  -> search_request_to_options              LiveAssemblyOptions
  -> run_live_route_assembly
  -> build_validated_agent_report
  -> build_search_result
```

На этой границе исходный request остаётся словарём, затем превращается в
`LiveAssemblyOptions`, а позже оборачивается read-only proxy `SearchRequest`.

### 2. Планирование

```text
LiveAssemblyOptions
  -> SearchRequest proxy
  -> FlowDecision
  -> EvidencePlan
  -> flight_runtime_plan.v1                 dict
  -> flight_search_plan.v1                  dict
```

`flight_runtime_plan.v1` хранит route context, `flow_decision`, `evidence_plan`,
метрики и пустой `segments`. Затем `SearchPlanBuilder` использует его для
построения primary и gateway queries.

`flight_search_plan.v1` при этом обязательно содержит:

- `mandatory_controls`, который в runtime создаётся пустым;
- `fallback_segment_plan`, который в активном runtime создаётся с пустым
  `segments`;
- `coverage_expectations`;
- primary и gateway queries.

Таким образом, два plan-объекта существуют одновременно, а часть обязательных
полей сохраняет форму удалённого segment-assembly пути.

### 3. Исполнение

`LiveAssemblyRunner.run()` сейчас делает:

```text
initialize_state
  -> primary offer queries
  -> direct-presence gate
  -> gateway waves
  -> preliminary build_route_trace
  -> decide whether direct-mode fallback is needed
  -> optional fallback wave
  -> final build_route_trace
```

Название `build_route_trace` создаёт впечатление чистой сериализации, но внутри
него выполняются:

- `run_aggregate_controls`;
- graph coverage controls;
- gateway discovery over provider results;
- `probe_ledger.finalize_unexecuted()`;
- OfferGraph construction;
- candidate materialization;
- DecisionScorer;
- DecisionFrontier;
- date-window inventory construction;
- route-trace serialization.

Поскольку `build_route_trace()` вызывается для preliminary и final результата,
aggregate controls, graph building и scoring выполняются повторно. Для решения
о fallback используются только counts из frontier; aggregate controls на эти
counts не влияют.

### 4. Provider result

Provider adapter возвращает типизированный `ProviderProbeResult`, содержащий
`normalized_offers` и `normalized_result`. Затем execution layer немедленно
преобразует его в свободный словарь с `top_offers`.

Следующие слои снова поддерживают несколько возможных имён одного содержания:

```text
top_offers | normalized_offers | offers | normalized_result.offers
```

Это означает, что типизированная граница существует только у адаптера, но не
защищает основной pipeline.

### 5. Решение и отчёт

После DecisionFrontier `build_agent_report()` снова выполняет selection logic:

1. Берёт primary и alternative options из frontier.
2. Превращает aggregate controls в дополнительные пользовательские варианты.
3. Добавляет RU-priority alternative options.
4. Повторно применяет часть stop-policy логики.
5. Только после этого строит `UserAnswerInput`.

Следовательно, утверждение документации «final traveler text from
DecisionFrontier only» сейчас не соответствует коду. Вариант может попасть в
пользовательский каталог, не пройдя единый DecisionScorer/DecisionFrontier.

### 6. Пользовательский ответ

В `flight_search_user_answer.v7` одно содержание сериализуется несколькими
способами:

- structured `catalog.items[].directions[].segments[]`;
- `catalog.items[].agent_display.lines`;
- `catalog.items[].agent_display.text`;
- `catalog.items[].render_line`;
- `answer_lines`;
- `rendered_text`.

Semantic validator затем проверяет равенство зеркал.

Дополнительно используются две разные грамматики:

- `agent_display` показывает коды аэропортов, терминалы, борт и длительность;
- финальный `rendered_text` строится отдельным `answer_display` renderer.

Финальный renderer сейчас:

- не показывает номер рейса;
- скрывает IATA origin у первого сегмента;
- пишет время как `0540 0635`, без двоеточия и без подписи вылет/прилёт;
- указывает дату вылета в начале строки, а дату прилёта только суффиксом при
  смене календарного дня;
- формирует визуально компактный, но неоднозначный для пользователя блок.

### 7. Граница CLI -> агент

CLI уже умеет в text mode:

1. повторно валидировать `user_answer`;
2. напечатать только `rendered_text`.

Но Golden Path в `SKILL.md` принудительно использует `--json`. Агент получает
полный envelope и должен самостоятельно найти:

```text
data.agent_report.user_answer.rendered_text
```

После этого агент может сократить или заново собрать маршрут. Именно эта граница
не защищена существующими CLI contract tests.

### 8. Тесты

Тестовая база хорошо покрывает отдельные функции и схемы. Однако:

- subprocess tests не проводят успешный `search` через весь pipeline;
- `test_search_app_adapts_request...` подменяет и assembly, и report builder;
- provider fixtures проверяются как файлы и используются в adapter/unit tests,
  но не проходят через полный CLI;
- нет теста `raw provider fixture -> normalized probes -> graph -> frontier ->
  report -> exact stdout`;
- нет автоматической проверки, что агент передал stdout без изменений.

## Дополнительный drift документации

Актуальная документация уже содержит проверяемые расхождения:

- `pipeline-reference.md` указывает `apps.search.normalize_search_request`, тогда
  как функция находится в `commands/search.py`;
- в одном месте задан `TUTU_MAX_PAGES = 3`, а ниже говорится о чтении до десяти
  страниц;
- описание заявляет единственный источник вариантов DecisionFrontier, но report
  builder добавляет aggregate и RU-priority options после frontier;
- `fallback_segment_plan` остаётся обязательным контрактным полем, хотя runtime
  заполняет его пустым значением.

## Целевой поток данных

```text
flight_search_request.v1
  -> SearchRequest
  -> SearchPlan
  -> SearchExecution
  -> SearchEvidence
  -> SearchDecision
  -> FlightSearchResult
  -> render once
  -> stdout
```

### SearchRequest

Единственная нормализованная immutable-модель пользовательского запроса.

Инварианты:

- request schema проверена;
- IATA/currency/provider policy нормализованы;
- даты проверены один раз;
- все defaults применены;
- последующие этапы не читают исходный произвольный dict.

`SearchRequest` должен заменить `LiveAssemblyOptions` как canonical имя и тип.
Существующие вложенные `RouteOptions`, `FilterOptions`, `EvidenceOptions` и
`OutputOptions` можно сохранить как части `SearchRequest`. Отдельный proxy и
параллельный тип `LiveAssemblyOptions` после миграции удаляются.

### SearchPlan

Единственный результат planning stage.

Он содержит:

- route context;
- primary probes;
- conditional fallback probes;
- evidence requirements;
- execution limits;
- provider policy;
- output limits;
- причины планирования, необходимые для diagnostics.

Planning stage не обращается к live providers и не создаёт execution statuses.

`FlowDecision` и `EvidencePlan` могут остаться внутренними чистыми policy
functions, но наружу planning stage отдаёт только один `SearchPlan`. Отдельные
runtime/search/fallback plan containers не передаются дальше параллельно.

### SearchExecution

Единственный владелец provider side effects.

```text
execute primary probes
  -> assess explicit fallback gate
  -> execute at most one bounded fallback wave when required
  -> execute required aggregate/evidence probes once
  -> finalize ledger once
  -> freeze SearchEvidence
```

Инварианты:

- каждый `probe_id` имеет ровно один terminal state;
- одна логическая provider query выполняется не более одного раза;
- результат провайдера сохраняется в одной canonical форме;
- `not_executed`, `skipped`, `failed`, `not_supported` различаются;
- после freeze provider calls запрещены.

### SearchEvidence

Immutable snapshot выполненного поиска:

- canonical probe results;
- normalized offers;
- provider failures;
- cache/freshness metadata;
- coverage ledger;
- direct-mode/fallback decision facts.

`ProviderProbeResult` не превращается в цепочку словарей с разными alias полями.
Если отдельное execution DTO необходимо, оно должно иметь одно поле `offers` и
один schema/type owner.

### SearchDecision

Чистый этап без I/O:

```text
SearchEvidence
  -> OfferGraph
  -> CandidateEnvelope
  -> DecisionScorer
  -> DecisionFrontier
```

Все варианты, которые могут быть показаны пользователю, включая provider
aggregate candidates и RU-priority controls, сначала преобразуются в единый
CandidateEnvelope и проходят одну decision policy.

Report builder не имеет права добавлять option, которого нет в SearchDecision.

Если preliminary evaluation нужна для direct-mode fallback, она оформляется как
явная чистая функция `assess_fallback(primary_evidence)`. Она не запускает
aggregate controls, не финализирует ledger и не строит отчёт.

### FlightSearchResult и rendering

Report stage является чистой проекцией SearchDecision и SearchEvidence.

Публичная форма следующей версии:

```text
flight_search_result.v6
  request
  route
  evidence
  frontier
  answer
```

Вложенный `agent_report` удаляется: result уже содержит те же разделы, а text mode
отдаёт `answer.rendered_text`. `agent_report.v5` и его registry entry удаляются в
том же contract migration без compatibility adapter.

У user answer остаются два разных по назначению источника:

- structured catalog — machine truth;
- `rendered_text` — единственный human text.

`answer_lines`, `render_line`, `agent_display.text` и `agent_display.lines` не
должны быть отдельными сериализованными зеркалами. Нужные строки вычисляются
локально renderer/validator из structured catalog.

Diagnostic trace строится из уже готовых stage artifacts. Он наблюдает pipeline,
но не является транспортом между execution, decision и report.

## Целевой формат маршрута

Каждый сегмент должен быть самодостаточным. Рекомендуемая грамматика:

```text
Нашёл варианты NTE -> SVX. Время местное для каждого аэропорта.

1. KL1420 · 09.07 17:20 Нант (NTE) -> 09.07 18:55 Амстердам (AMS)
   Пересадка в AMS: 2 ч 05 мин
   KL1959 · 09.07 21:00 Амстердам (AMS) -> 10.07 01:20 Стамбул (IST)
   Пересадка в IST: 11 ч 30 мин
   SU2137 · 10.07 12:50 Стамбул (IST) -> 10.07 19:55 Екатеринбург (SVX)
   Общее время: ... · 104 521 RUB
```

Обязательные поля каждой строки сегмента:

- flight number либо явное `номер рейса не предоставлен`;
- дата и время вылета;
- origin city и IATA;
- дата и время прилёта;
- destination city и IATA;
- терминал только когда он известен;
- никакого вывода времени без двоеточия;
- никакого неявного перехода на следующий день.

Между соседними сегментами обязательно указываются аэропорт и длительность
пересадки. При смене аэропорта отдельно указывается ground-transfer risk.

## План реализации

### Этап 0. Зафиксировать acceptance contract

До изменения production code подготовить локальный red test для маршрута
`NTE -> AMS -> IST -> SVX` и согласованный expected stdout. В историю ветки
попадают только зелёные commits.

Acceptance contract фиксирует:

- порядок сегментов;
- номера рейсов;
- даты и локальные времена обоих концов каждого сегмента;
- календарный переход;
- расположение layover строго между соседними сегментами;
- цену и ticketing caveat;
- отсутствие debug JSON в text mode.

### Этап 1. Одна request-модель и один plan

Изменения:

1. Выбрать один canonical typed request owner.
2. Удалить read-only proxy, который только повторяет `LiveAssemblyOptions`.
3. Компилировать `FlowDecision` и `EvidencePlan` внутрь одного `SearchPlan`.
4. Создать `flight_search_plan.v2`.
5. Удалить обязательные пустые `fallback_segment_plan` и
   `mandatory_controls`, если у них нет активного runtime значения.
6. Заменить `build_live_route_segment_plan` на честно названный route-context или
   plan builder.
7. Упростить `diagnose plan`: один plan, без пустых `segments/probe_specs` зеркал.

Критерии завершения:

- от validated request до execution передаётся один SearchPlan;
- plan можно построить offline и schema-validate;
- plan не содержит полей, существующих только ради удалённого runtime;
- все planning tests работают через один entrypoint.

### Этап 2. Выделить execution boundary

Изменения:

1. Создать явный `SearchExecutor`/`SearchExecution` entrypoint.
2. Перенести туда primary, gateway, fallback и aggregate probes.
3. Перенести туда `ProbeExecutionLedger.finalize_unexecuted()`.
4. Сохранить результаты в canonical `SearchEvidence`.
5. Удалить provider calls из `LiveSearchResultBuilder`.
6. Заменить текущий preliminary full build на чистый fallback assessment.
7. Обеспечить idempotency по `probe_id` и logical query key.

Критерии завершения:

- provider adapters вызываются только из execution package;
- aggregate controls исполняются один раз;
- ledger финализируется один раз;
- повторный вызов report/trace builder не вызывает сеть;
- отдельный тест считает фактические provider calls.

### Этап 3. Один decision path

Изменения:

1. Строить OfferGraph после freeze SearchEvidence.
2. Нормализовать aggregate offers и RU-priority candidates до scoring.
3. Передавать все reportable candidates в один CandidateEnvelope.
4. Выполнять DecisionScorer/DecisionFrontier один раз для финального результата.
5. Перенести selection/stop-policy ветви из `agent_report_builder.py` в decision
   layer либо удалить их как дубли.
6. Запретить report builder добавлять варианты после frontier.

Критерии завершения:

- каждый `catalog.item.option_id` существует в SearchDecision;
- порядок каталога выводится из одной decision policy;
- report builder не импортирует provider execution code;
- result одинаков при повторном pure render одного SearchDecision.

### Этап 4. Упростить report и output contracts

Изменения:

1. Ввести следующую версию search result и user answer contract.
2. Оставить structured catalog и один `rendered_text`.
3. Удалить сериализованные текстовые зеркала.
4. Заменить две renderer-грамматики одной.
5. Сделать строки сегментов самодостаточными по формату выше.
6. Генерировать public frontier и catalog независимо из одного SearchDecision,
   связывая их по `option_id`, без обратной зависимости frontier от renderer.
7. Удалить старые schemas и tests в том же migration change; не добавлять
   compatibility adapter.

Критерии завершения:

- semantic validator проверяет structured facts и детерминированный render, а не
  равенство нескольких сохранённых копий;
- номер рейса и обе endpoint date/time видны в stdout;
- final text строится одной функцией;
- `search` в text mode печатает только validated `rendered_text`.

### Этап 5. Сократить SKILL.md

Agent-facing happy path:

```text
1. Создать flight_search_request.v1.
2. Выполнить python3 -m flights_cli search --request <file> без --json.
3. При exit code 0 вернуть stdout дословно.
4. При exit code != 0 показать ошибку и остановиться.
```

Правила:

- не сокращать;
- не переставлять варианты;
- не собирать маршрут заново;
- не отвечать из raw provider JSON;
- не запускать diagnostics автоматически;
- diagnostics использовать только по явному запросу на разбор проблемы.

Provider internals, airport policy и debug procedure остаются в references, а не
в Golden Path.

Критерии завершения:

- в активном skill есть один пользовательский путь;
- агенту не нужно читать вложенный JSON path;
- успешный ответ агента совпадает с stdout CLI;
- failure path не запускает скрытые дополнительные probes.

### Этап 6. End-to-end tests

#### Детерминированный CLI E2E

Добавить настоящий subprocess test, который:

1. Поднимает локальный Tutu MCP stub.
2. Передаёт его URL через `FLIGHTS_TUTU_MCP_URL`.
3. Возвращает empty/full-route evidence для `NTE -> SVX`, feeder offer
   `NTE -> AMS -> IST` и destination leg `IST -> SVX` из fixtures.
4. Запускает реальный parser и команду:

   ```bash
   python3 -m flights_cli search --request request.json
   ```

5. Не patch-ит planner, executor, normalizer, OfferGraph, scorer, report builder
   или renderer.
6. Сравнивает stdout с exact expected text.
7. Проверяет журнал stub server: каждая ожидаемая query выполнена один раз.

Этот тест должен проходить без внешней сети и без live-provider marker.

#### JSON E2E

Тем же fixture transport проверить `--json` как machine/debug surface:

- schema validation итогового result;
- segment order и endpoint chronology;
- `catalog option ids` принадлежат frontier;
- `rendered_text` совпадает с text-mode stdout;
- diagnostic trace не присутствует в public search result.

#### Skill/agent acceptance

CLI E2E не ловит изменение ответа моделью после tool call. Нужен отдельный
Hermes acceptance/eval:

```text
user request
  -> flight-search skill
  -> CLI tool call
  -> final assistant message
```

Проверка: final assistant message после нормализации только terminal newline
равен stdout CLI. Добавление вступления, сокращение сегментов или изменение дат
считается failure.

### Этап 7. Документация, версии и удаление старого

Изменения:

1. Обновить `pipeline-reference.md` по реальным функциям и контрактам.
2. Убрать противоречия по pagination и provider limits.
3. Обновить `report-contract.md`, `cli-maintenance.md`, `debug-playbook.md` и
   `references/index.md`.
4. Обновить `SKILL.md`, CLI README и version manifest атомарно.
5. Поднять версии как минимум minor, поскольку меняются публичный output contract
   и agent workflow.
6. Удалить старые schema resources, старые test fixtures и импорты в том же
   change, не сохраняя legacy adapters.
7. Проверить source/runtime parity перед заявлением о runtime behavior.

Критерии завершения:

- документация описывает только существующие entrypoints;
- version manifest совпадает с package, skill и registry;
- `maint doctor` и `maint check` проходят;
- source и runtime идентичны для опубликованной версии.

## Предлагаемые границы commits

Каждый commit должен оставлять suite зелёным.

1. `test(flight-search): add deterministic route acceptance harness`
2. `refactor(flight-search): unify request and search plan`
3. `refactor(flight-search): isolate provider execution snapshot`
4. `refactor(flight-search): make decision frontier the only option source`
5. `refactor(flight-search): simplify result and answer contracts`
6. `fix(flight-search): render explicit segment dates times and flight numbers`
7. `docs(flight-search): switch skill to verbatim text golden path`
8. `test(flight-search): lock cli and skill end-to-end behavior`
9. `chore(flight-search): bump versions and verify runtime parity`

Локальный red/green цикл может объединять код и соответствующий acceptance test
до commit. В удалённую ветку не отправляются заведомо красные промежуточные
commits.

## Общие критерии готовности

Обновление считается завершённым только если одновременно выполнено всё:

- один canonical agent command;
- successful agent answer равен CLI stdout;
- один typed request и один SearchPlan;
- provider calls существуют только в execution stage;
- каждый probe имеет один terminal state и исполняется максимум один раз;
- SearchEvidence immutable после execution;
- OfferGraph и final DecisionFrontier строятся один раз после evidence freeze;
- каждый показанный option прошёл единый decision path;
- report/renderer не выполняют поиск и не добавляют варианты;
- в public answer нет дублирующих текстовых зеркал;
- каждый сегмент показывает flight number, обе даты, оба локальных времени и оба
  IATA;
- CLI subprocess E2E проходит без внешней сети;
- skill/agent acceptance ловит любое переписывание stdout;
- полный offline suite, lint, schema tests, doctor и maintenance check зелёные;
- активная документация и version manifest соответствуют коду.

## Рекомендуемый первый implementation slice

Первый change не должен начинаться с массового удаления файлов. Минимальный
вертикальный slice:

1. Создать fixture-backed MCP E2E harness и expected NTE-SVX output.
2. Вынести preliminary fallback assessment из `build_route_trace()`.
3. Переместить aggregate execution и ledger finalization в execution stage.
4. Доказать тестом, что provider query вызывается один раз.
5. Построить final route trace/report один раз.

После этого pipeline уже получает безопасную execution boundary. Затем можно
менять plan и public contracts, не смешивая сетевые side effects с миграцией
формата ответа.
