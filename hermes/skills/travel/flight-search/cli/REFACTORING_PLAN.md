# План упрощения `flight-search` CLI

Дата анализа: 2026-08-02
База: ветка `dev`, commit `96835d479b523c5bf6d8945f67ce7a932d0e5749`
Область: `hermes/skills/travel/flight-search/cli`

## 1. Цель и критерий успеха

Цель — уменьшить количество собственного инфраструктурного кода и прослоек, не меняя поисковую семантику, публичные JSON-контракты и текст ответа путешественнику.

Рефакторинг считается успешным, если одновременно выполнены условия:

- удалён код без production-вызовов и совместимые фасады без подтверждённых внешних потребителей;
- собственный YAML-парсер заменён зрелым продуктом;
- два самостоятельных HTTP-стека сведены к уже объявленному `httpx2`;
- ручной lifecycle Tutu MCP удаляется только после отдельного доказательного spike;
- число production-модулей и строк снижается, а новые слои, фабрики и интерфейсы не появляются;
- результаты `search` до и после совпадают по контрактам и смысловым инвариантам;
- все допустимые прямые варианты остаются видимыми;
- `data.answer.rendered_text` остаётся единственным каноническим текстом ответа;
- directional direct-first/gateway fallback, round-trip pairing/coverage и различие между feasibility пересадки и защитой билета сохраняются.

План следует ponytail-порядку: сначала не создавать, затем переиспользовать код проекта, затем stdlib, затем уже установленную/объявленную зависимость, и только после этого рассматривать новую зависимость.

## 2. Фактическое состояние

### 2.1. Инвентаризация

AST-инвентаризация production-пакета `flights_cli` дала:

| Область | Python-файлы | LOC | Классы | Функции/методы |
|---|---:|---:|---:|---:|
| `pipeline` | 18 | 5 063 | 24 | 192 |
| `providers` | 10 | 2 855 | 2 | 94 |
| `execution` | 10 | 2 549 | 11 | 90 |
| `domain` | 15 | 2 292 | 19 | 95 |
| `reporting` | 11 | 1 896 | 3 | 71 |
| корень пакета | 11 | 1 440 | 7 | 68 |
| `orchestrators` | 3 | 879 | 4 | 25 |
| `adapters` | 6 | 857 | 2 | 27 |
| `commands` | 5 | 667 | 2 | 29 |
| `contracts` | 3 | 533 | 0 | 13 |
| `data` | 3 | 246 | 2 | 10 |
| `ports` | 2 | 94 | 3 | 5 |
| **Итого** | **97** | **19 371** | **79** | **719** |

Тестовый набор содержит 45 файлов `test_*.py`.

Runtime-зависимости из `pyproject.toml`:

- `httpx2==2.9.1`;
- `jsonschema>=4.22,<5`;
- `mcp==2.0.0`.

В каноническом venv также установлены `PyYAML 6.0.3`, `anyio 4.14.2`, `pydantic 2.13.4`, `click 8.4.2`, `attrs 26.1.0`; они транзитивные и не являются разрешением использовать их без прямого объявления. Lock-файл рядом с CLI не найден.

### 2.2. Реальный production-путь

1. `flights_cli/__main__.py` вызывает `flights_cli.cli.main()`.
2. `cli.py::build_parser()` строит дерево `argparse`; leaf parser получает `func` и `command_name` из `CommandSpec`.
3. `cli.py::main()` валидирует CLI-настройки, создаёт `Store`, при необходимости обновляет статический каталог и вызывает handler.
4. `commands/search.py::command_search()` читает JSON, строит типизированный `SearchRequest` и вызывает `SearchWorkflow.run()`.
5. `orchestrators/search_workflow.py` последовательно выполняет:
   `SearchPlanBuilder` → `SearchExecutor` → `SearchDecisionBuilder` → diagnostic/result projection → `build_flight_search_result()`.
6. `execution/search_executor.py` сначала запускает direct-запросы, отдельно вычисляет наличие direct по направлениям, затем запускает broad/gateway только для направлений без подходящего direct.
7. Provider results превращаются в offer graph (`offer_graph_builder.py`), candidate envelope (`offer_graph_materializer.py`), проходят validation/scoring/frontier (`candidate_validation.py`, `decision_scorer.py`, `frontier_selection.py`).
8. `result_builder.py` требует точного сохранения ID и порядка frontier, строит `answer`, валидирует JSON Schema и семантические инварианты.
9. `reporting/user_answer.py` создаёт `answer.rendered_text`; `output.py::render_search_user_text()` возвращает именно его в text mode. В JSON mode он доступен как `data.answer.rendered_text` внутри общего envelope.

### 2.3. Контракты, которые нельзя упростить

- `frontier_selection.py::build_decision_frontier()` не должен скрывать допустимые direct-кандидаты diversity/output pruning; direct limit обязан покрывать все допустимые direct в рамках публичной политики.
- Gateway fallback вычисляется отдельно для outbound/return. Наличие direct в одном направлении не блокирует fallback в другом.
- `offer_graph_materializer.py::_covers_requested_trip()` и round-trip pairing должны подтверждать обе стороны поездки; нельзя считать два несвязанных one-way полным round trip без явной пары.
- `candidate_validation.py::_ticket_protection()` со статусом `unprotected` не равен `connection_status=impossible`. Защита билета и физическая/временная осуществимость пересадки — разные оси.
- Cross-airport соединения остаются запрещены; `min_cross_airport_min` не включает альтернативный механизм трансфера.
- JSON Schema и семантическая проверка взаимодополняют друг друга: вторую нельзя заменить только генерацией моделей.

## 3. Доказательства и гипотезы

### Подтверждено

- `ruff 0.15.20` проходит по production-коду без замечаний.
- `vulture 2.16` с confidence 80% не нашёл кандидатов. На 60% он показывает только намеренно переопределённые mutator-методы `FrozenDict/FrozenList`, четыре неиспользуемых значения `AbsenceReason` и атрибут `TutuMcpClient.playbook`; первые и последний имеют подтверждённое поведение/тесты, поэтому это не dead code.
- Полный поиск production-imports показал только два не-entrypoint модуля с нулевым входящим production-import: `domain/provider_offer_filter.py` и `pipeline/candidate_ranker.py`. Оба используются только тестами как compatibility surface.
- Класс `AbsenceReason` и все четыре его значения не имеют вызовов во всём CLI.
- `reporting/user_answer_contracts.py` — фасад над `contracts.registry` и `contracts.validation`; собственного поведения нет.
- `pipeline/offer_graph.py` — фасад над builder/materializer/model; production-потребитель один (`SearchDecisionBuilder`).
- `data/yaml_subset.py` содержит 198 строк собственного YAML-парсера. `PyYAML` уже установлен транзитивно.
- Сравнение текущего парсера и `yaml.safe_load()` совпало для `gateway_priors.yaml`, но не для `route_access_profiles.yaml`: некавыченный код страны `NO` PyYAML интерпретирует как `False`. Это обязательный migration case, а не теоретический риск.
- `urllib.request` используется отдельно в `kupibilet_transport.py` и `static_catalog.py`, хотя `httpx2` уже является прямой runtime-зависимостью. В `kupibilet_transport.py` дополнительно вручную реализовано gzip-декодирование.
- `TutuMcpClient` уже оборачивает официальный `mcp.Client`, но добавляет собственные task, queue, drain и cancellation lifecycle. Его нельзя объявить лишним без проверки таймаутов и отмены.

### Требует проверки в реализации

- Есть ли внешние импорты compatibility-модулей за пределами репозитория. До удаления нужен grep установленного skill/runtime и краткая запись о допустимости внутреннего breaking change.
- Может ли `mcp==2.0.0` напрямую и корректно закрывать Streamable HTTP session при timeout/external cancellation без worker queue. Это отдельный spike.
- Полная API-паритетность `httpx2==2.9.1` для нужных ошибок/декодирования должна проверяться тестами текущей pinned-версии; документация по более новой версии не является доказательством.

## 4. Матрица keep/delete/merge/replace

| Решение | Файл / символ | Обоснование | Ожидаемый эффект |
|---|---|---|---:|
| Delete | `domain/provider_offer_filter.py` | Ноль production-imports; только re-export `stop_policy.filter_provider_offers` | −1 модуль, −8 LOC |
| Delete | `pipeline/candidate_ranker.py` | Ноль production-imports; только re-export scoring/frontier | −1 модуль, −21 LOC |
| Delete | `domain/vocabulary.py::AbsenceReason` | Ноль ссылок во всём CLI | −1 класс, около −10 LOC |
| Merge | `reporting/user_answer_contracts.py` | Только re-export и вычисление версии; прямые imports из `contracts` короче | −1 модуль, около −19 LOC |
| Merge | `pipeline/offer_graph.py` | Compatibility-фасад с одним production-потребителем | −1 модуль, около −22 LOC |
| Merge | `commands/search.py::{PreparedSearchRequest, SearchArtifacts}` | Однополевый wrapper и контейнер, нужный только diagnose; достаточно `SearchRequest` + `SearchRunArtifacts` | −2 класса, ориентир −15…30 LOC |
| Replace | `data/yaml_subset.py`, вызов в `data/config_loader.py` | Готовый YAML parser лучше собственного subset-parser | −1 модуль, ориентир −175…195 LOC net |
| Replace | `providers/kupibilet_transport.py::post_kupibilet_search`, `decode_http_body` | Уже объявленный `httpx2` умеет sync HTTP, status handling, JSON и decompression | ориентир −15…30 LOC |
| Replace | `providers/static_catalog.py::default_fetch_url` | Второй urllib-stack можно свести к тому же `httpx2` | ориентир −10…20 LOC |
| Spike | `providers/tutu_client.py::TutuMcpClient` worker/queue/drain | Официальный MCP SDK уже есть, но lifecycle-инварианты пока не доказаны | если spike успешен: −250…350 LOC |
| Keep | `cli.py` + stdlib `argparse` | Stdlib уже покрывает subcommands, parents и leaf dispatch; смена на Click/Typer создаст migration без нужной функции | 0 |
| Keep | `command_surface.py::CommandSpec` | Это фактический registry command names/audience/catalog policy, используемый CLI, maint и version manifest | 0 |
| Keep | `contracts/validation.py` + `jsonschema` | Schema validation уже делегирована продукту; собственный код проверяет межполевые flight-инварианты | 0 |
| Keep | `domain/immutable.py` | Нужна глубокая неизменяемость JSON-подобных evidence; stdlib `MappingProxyType` не замораживает вложенные списки | 0 |
| Keep | `providers/live_cache.py` | 78 LOC, два потребителя, простой TTL и прозрачный JSON; `diskcache` добавит больше surface, чем удалит | 0 |
| Keep | offer graph, pairing, scoring, connection policy, rendering | Это уникальные правила flight-search; generic graph/ranking library их не заменяет | 0 |
| Keep | `execution/diagnostic_probe_runner.py` | Малый, но реальный provider boundary для debug-команды; не compatibility façade | 0 |

## 5. Оценка готовых продуктов

### 5.1. PyYAML — заменить сейчас

- Текущий код: `data/yaml_subset.py::{parse_yaml_subset, _parse_block, _parse_mapping, _parse_list, ...}`.
- Ответственность: parsing mapping/list/scalar subset, ошибки с path/line.
- Кандидат: `yaml.safe_load` из PyYAML. Официальная документация указывает, что `safe_load` создаёт только простые типы и не конструирует произвольные Python-объекты: <https://pyyaml.org/wiki/PyYAMLDocumentation>.
- Contract fit: обе конфигурации — обычные YAML mapping/list/scalar.
- Недостающие возможности/различия: YAML 1.1 boolean resolution меняет `NO` на `False`; сообщения исключений имеют другой формат; `safe_load` может вернуть не-mapping/`None`.
- Миграция: добавить прямую зависимость `PyYAML>=6.0,<7`, заменить вызов, проверять top-level `dict`, оборачивать `yaml.YAMLError` в текущий `CliError`, заключить `NO` в кавычки, закрепить parity fixture.
- Packaging/runtime: одна новая прямая зависимость, но новых фактически установленных пакетов в текущем venv не появляется. Нужно проверить wheel/Windows/macOS packaging в CI.
- Вердикт: **replace now**.

### 5.2. HTTPX2 — заменить urllib сейчас

- Текущий код: `kupibilet_transport.py::post_kupibilet_search`, `decode_http_body`; `static_catalog.py::default_fetch_url`.
- Ответственность: GET/POST, timeout, status/error body, JSON/body, content decoding.
- Кандидат: уже объявленный `httpx2==2.9.1`. Метаданные установленного пакета заявляют sync/async API и automatic decompression; документация проекта: <https://httpx2.pydantic.dev/>.
- Contract fit: простые синхронные GET/POST.
- Недостающие возможности: текущие `CliError.message/details`, 1000-символьный error body и `Retry-After` надо сохранить явно; API проверяется на pinned 2.9.1.
- Миграция: заменить каждый transport напрямую, без нового общего client factory. Общий helper добавлять только если после двух реализаций остаётся дословный блок не менее примерно 10 строк.
- Packaging/runtime: новых зависимостей нет; удаляются два urllib error surface и ручной gzip.
- Вердикт: **replace now**, с MockTransport/monkeypatch тестами.

### 5.3. Официальный MCP Python SDK — spike

- Текущий код: `providers/tutu_client.py::TutuMcpClient`, `_session_worker`, `_await_response`, `_drain_task`, `_close_stack`; retry/cancel glue в `tutu_mcp.py`.
- Ответственность: Streamable HTTP session, playbook preflight, tool calls, deadline refresh, cleanup under cancellation, error attribution.
- Кандидат: уже pinned `mcp==2.0.0`; проект использует `mcp.Client` и `streamable_http_client`. MCP называет Python SDK официальным Tier 1 SDK: <https://modelcontextprotocol.io/docs/sdk> и <https://github.com/modelcontextprotocol/python-sdk>.
- Contract fit: transport и tool invocation покрываются SDK.
- Недостающие возможности: не доказано, что direct context manager сохраняет текущие гарантии cleanup при `asyncio.CancelledError`, timeout во время close и nested exception groups; playbook preflight остаётся domain/provider rule.
- Миграция: сначала тестовый spike на pinned 2.0.0 с fake server/transport, затем минимальный direct wrapper. Retry pagination и Tutu payload normalization не переносить в SDK.
- Packaging/runtime: новых пакетов нет; upgrade MCP не входит в этот рефакторинг.
- Вердикт: **spike**; при одном неснятом lifecycle regression — **keep custom**.

### 5.4. Click/Typer вместо argparse — не заменять

- Текущий код: `cli.py`, `command_surface.py`.
- Кандидат: Click уже транзитивно установлен; Typer потребовал бы новую прямую зависимость.
- Contract fit: команды построить можно, но точный help output, положение `--json`, exit codes и error envelopes придётся мигрировать.
- Выигрыш: ориентировочно только косметическое сокращение регистрации аргументов; command policy registry всё равно остаётся.
- Риск: большой CLI diff при нулевой продуктовой ценности.
- Вердикт: **keep argparse**. Stdlib уже поддерживает subcommands/parent parsers: <https://docs.python.org/3/library/argparse.html>.

### 5.5. Pydantic вместо SearchRequest/semantic validators — не заменять

- Текущий код: `pipeline/search_request.py`, `contracts/validation.py`.
- Кандидат: Pydantic установлен транзитивно через MCP.
- Contract fit: простые типы и часть defaults покрываются; межсегментная chronology, airport continuity, frontier/catalog equality и rendered-text purity остаются custom.
- Риск: два источника схемы — packaged JSON Schema и generated schema; изменение error paths/messages; прямая зависимость от транзитивного пакета.
- Вердикт: **keep dataclasses + jsonschema + semantic validators**. Отдельный Pydantic spike не окупается.

### 5.6. Disk cache/retry/graph libraries — не добавлять

- `diskcache`/аналог ради 78 LOC `live_cache.py`: нет требований к eviction, multiprocess locking или SQL indexing.
- `tenacity` ради одного двухпопыточного Tutu retry: доменные deadline/error details всё равно останутся.
- `networkx` ради offer graph: алгоритмы проекта — не generic traversal, а flight pairing, coverage, ticketing и connection policy.
- Вердикт: **keep custom**, пока измеримое требование не превысит существующий небольшой код.

## 6. Пошаговый план маленьких обратимых PR

### PR 0 — сделать baseline детерминированным

Состав:

1. Исправить только датированные тестовые fixtures: не использовать даты, которые становятся прошедшими, либо передавать фиксированное `today` на input boundary.
2. Зафиксировать characterization tests для пяти инвариантов из раздела 2.3.
3. Сохранить golden stdout для text search и JSON paths.

Текущий baseline на 2026-08-02: **437 passed, 8 failed, 183 subtests passed**. Все 8 failures вызваны датами `2026-07-20`/`2026-08-01`, ставшими прошедшими; это не результат рефакторинга, но пока suite не может быть merge gate.

Success gate:

- весь offline suite зелёный из корня `cli`;
- отдельные тесты доказывают direct completeness, directional fallback, round-trip coverage, `unprotected != impossible`, exact `rendered_text`.

Rollback: revert test-only commit; production не затронут.

### PR 1 — удалить подтверждённый dead/compatibility code

Состав:

1. Удалить `AbsenceReason`.
2. Перевести тесты с `pipeline.candidate_ranker` на owning modules и удалить façade.
3. Перевести тест архитектуры с `domain.provider_offer_filter` на `stop_policy`, удалить façade.
4. Перед удалением выполнить repo/runtime import search; если найден внешний consumer, оставить deprecated shim на один release.

Success gate: full offline suite; `ruff`; `vulture --min-confidence 80`; import smoke для всех production modules.

Оценка: −2 модуля, около −39 LOC.
Rollback: восстановить только два re-export файла и enum.

### PR 2 — убрать внутренние façade/wrapper классы

Состав:

1. Прямые импорты contract version/validators, удалить `user_answer_contracts.py`.
2. `SearchDecisionBuilder` импортирует builder/materializer из owning modules; удалить `offer_graph.py`.
3. `prepare_search_request()` возвращает `SearchRequest`; diagnose получает `request.to_payload()` напрямую.
4. Убрать `PreparedSearchRequest` и, если trace остаётся простым, `SearchArtifacts`; не создавать заменяющий DTO.

Success gate: CLI help goldens, diagnose plan/trace contracts, search JSON/text contract suite, architecture tests.

Оценка: −2…3 модуля, −2 класса, примерно −50…75 LOC.
Rollback: один PR, re-export façады можно восстановить без data migration.

### PR 3 — PyYAML

Состав:

1. Объявить PyYAML напрямую.
2. Добавить parity tests старого результата для двух packaged YAML files.
3. Закавычить `"NO"` в `route_access_profiles.yaml` и тестировать, что это строка.
4. Перевести `load_yaml_mapping()` на `yaml.safe_load`, сохранить strict/empty/error policy.
5. Удалить `yaml_subset.py` и его unit tests, оставив tests loader behavior.

Success gate: config, gateway priors, route access profile tests; package build/install smoke; Windows/macOS dependency resolution; full suite.

Оценка: −1 модуль, net −175…195 LOC.
Rollback: восстановить parser и YAML без кавычки; persisted user data не меняется.

### PR 4 — один HTTP stack

Состав:

1. Перевести Kupibilet POST на `httpx2`.
2. Перевести static catalog GET на `httpx2`.
3. До migration зафиксировать fixture-матрицей фактическую GET- и POST-семантику redirect для 301/302/303/307/308.
4. По умолчанию воспроизвести её точно: Kupibilet POST не должен незаметно повторяться на 307/308, поэтому blanket `follow_redirects=True` для него недостаточен. Для static-catalog GET он допустим только после подтверждения матрицей.
5. Любое изменение redirect-поведения вынести в отдельно согласованный и документированный change с доказательствами по безопасности и поведению provider.
6. Удалить `decode_http_body`; полагаться на проверенное automatic decoding pinned-версии.
7. Сохранить `CliError` shape, `Retry-After`, status и error-body truncation.
8. Не вводить глобальный singleton client; reuse client добавлять только после профилирования.

Success gate: tests 2xx/4xx/5xx, malformed JSON, gzip, timeout, transport error, Retry-After; redirect-матрица GET/POST × 301/302/303/307/308 доказывает точный parity, включая отсутствие silent POST replay на 307/308; catalog dry-run/refresh fixtures; offline CLI suite.

Оценка: −25…50 LOC, −1 ручной decoder, −1 transport technology.
Rollback: оба transport change независимы; можно откатить один, не откатывая другой.

### PR 5a — MCP lifecycle spike, без production-switch

Матрица:

- normal initialize → playbook → search → close;
- empty/invalid playbook;
- timeout initialize/call/close;
- external cancellation во время call;
- nested ExceptionGroup transport failures;
- first retry failure, second success;
- terminal non-retryable MCP error;
- отсутствие leaked tasks/resources после каждого case.

Артефакт PR: тестовый harness и краткий verdict в PR description. Production code не переключать.

Success gate: direct `mcp.Client` на **pinned 2.0.0** проходит всю матрицу с теми же `CliError.type/details` и без pending tasks.

Rollback: удалить spike tests/harness.

### PR 5b — убрать ручной MCP worker, только при зелёном spike

Состав:

1. Оставить нормализацию URL, extraction payload и playbook preflight.
2. Использовать прямой SDK context/transport.
3. Удалить command queue, worker task, custom drain/close stack там, где SDK доказал эквивалентность.
4. Не смешивать с upgrade `mcp`, pagination или provider parser refactor.

Success gate: вся spike matrix, `test_tutu_client.py`, `test_tutu_mcp.py`, offline e2e; один opt-in live Tutu smoke с проверкой отсутствия leaked session.

Оценка при успехе: −250…350 LOC.
Rollback: восстановить старый `TutuMcpClient`; provider/result contracts не меняются.

### PR 6 — контрольный deletion pass

После PR 1–5:

1. Пересобрать belief map и проверить boundaries.
2. Повторить AST inventory, production in-degree scan, `ruff`, `vulture` 80/60.
3. Удалять новые кандидаты только после проверки call sites и runtime imports.
4. Не объединять крупные domain-файлы ради числа файлов: merge только если две части всегда меняются вместе и разделение не защищает dependency direction.

Success gate: документированный before/after и отсутствие новых архитектурных нарушений.

## 7. Итоговый прогноз

Без рискованного MCP switch реалистичная цель первых четырёх PR:

- **−4…6 production-модулей**;
- **примерно −290…360 net LOC**;
- один YAML parser вместо 198 LOC собственного;
- один HTTP stack вместо двух;
- без новых абстракций.

Если MCP spike успешен, суммарный ориентир:

- **−540…710 net LOC**;
- удаление большей части ручного session-worker lifecycle.

Это оценки, не KPI. Нельзя удалять contract/domain checks ради достижения числа строк.

## 8. Non-goals

- Не менять provider ranking, prices, route coverage или число отображаемых допустимых direct options.
- Не объединять connection feasibility и ticket protection.
- Не менять схемы `flight_search_request.v3`, `flight_search_result.v9`, `flight_search_user_answer.v11` и trace schema в тех же PR.
- Не переписывать CLI на Click/Typer.
- Не заменять offer graph на generic graph library.
- Не переписывать provider parsers и carrier/airport normalization без отдельного дефекта.
- Не обновлять одновременно `mcp`, `httpx2`, `jsonschema`.
- Не вводить repository/service/factory/interface с единственной реализацией.
- Не удалять supporting documentation до переноса долговечных правил в активные документы/тесты.
- Не использовать live provider results как единственный regression oracle; основные gates должны быть frozen/offline.

## 9. Обязательные команды-gates для каждого implementation PR

Из `hermes/skills/travel/flight-search/cli` с каноническим Python:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/home/.venvs/hermes-backup/bin/python -m pytest tests -q -p no:cacheprovider
/Users/home/.venvs/hermes-backup/bin/ruff check flights_cli tests --no-cache
/Users/home/.venvs/hermes-backup/bin/vulture flights_cli --min-confidence 80
```

Для PR, затрагивающего search path, дополнительно:

- contract tests: CLI, request/result, offer graph, candidate ranker/frontier, user answer;
- round-trip fixture с проверкой `covers_requested_trip` и direction pairing;
- direct fixture, где несколько допустимых direct вариантов все присутствуют в frontier/catalog;
- mixed-direction fixture: direct outbound + fallback return;
- self-transfer fixture: осуществимая пересадка остаётся `unprotected`, но не `impossible`;
- text-mode stdout содержит канонический `answer.rendered_text`, за которым следует ровно один завершающий `\n` (`stdout == answer.rendered_text + "\n"`); renderer и содержимое ответа не меняются;
- JSON mode содержит тот же текст по `data.answer.rendered_text`.

Перед merge: `git diff --check`, package build/install smoke и проверка, что PR не содержит `.belief_map*`, `.bx-dev/`, caches или generated artifacts.

## 10. Фактический результат PR0–PR6

Срез `origin/dev` → `f1410fb` дал следующие изменения production-кода:

- production-модули: **97 → 92** (−5);
- физический production LOC: **19 371 → 18 805** (−566);
- классы: **79 → 74**;
- функции и методы: **719 → 698**;
- прямые зависимости: **3 → 4** из-за явного объявления PyYAML;
- consumers `urllib`: **2 → 0**;
- импорты ручного gzip decoder: **1 → 0**;
- production diff: **+205/−771**.

Удалены пять модулей: `data/yaml_subset.py`,
`domain/provider_offer_filter.py`, `pipeline/candidate_ranker.py`,
`pipeline/offer_graph.py` и `reporting/user_answer_contracts.py`. Среди
удалённых wrapper/lifecycle symbols: `AbsenceReason`, `PreparedSearchRequest`,
`SearchArtifacts`, `build_search_artifacts()`, `YamlSubsetError`,
`parse_yaml_subset()`, `decode_http_body()`, а также ручные MCP session-worker
механизмы `_session_worker()`, `_await_response()`, `_drain_task()`,
`_close_stack()`, `_reset_session()` и command queue.

Итоговые gates: **459 passed, 1 skipped, 206 subtests passed**; Ruff, Vulture
с `--min-confidence 80` и belief-map boundaries (**216**) чистые. Дополнительно
пройдены import smoke, `maint doctor`, `maint check`, package build/install и
offline lifecycle/terminal error cases; opt-in live Tutu acceptance покрыл initialize/playbook/search/close, cleanup session/client и отсутствие leaked tasks.

Контрольный deletion pass не нашёл новых кандидатов категории `SAFE_NOW`.
Сохранена намеренная сложность offer graph, connection/ticketing policy,
provider parsing и error-contract boundaries: их удаление или объединение не
подтверждено эквивалентным более простым решением.

Установленный runtime остаётся устаревшим самостоятельным snapshot и в рамках
этих PR не публиковался. Для обновления требуется полная замена дерева с
удалением отсутствующих файлов и последующий `maint check`; overlay-copy
запрещён.

Несоответствие между заявленным `Python >=3.10` и использованием
`enum.StrEnum` существовало до рефакторинга. Это отдельный follow-up вне scope:
поддержка Python 3.10 не исправлена и не считается подтверждённой.
