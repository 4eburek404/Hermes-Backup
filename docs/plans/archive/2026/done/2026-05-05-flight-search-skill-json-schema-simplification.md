# Plan: flight-search-routing JSON Schema simplification

## Goal
Упростить интеграцию business-flight логики в skill `flight-search-routing`: нормативный reference должен стать route-independent **JSON Schema** для уже существующей политики preferred airports / live-first routing, а `SKILL.md` должен остаться коротким dispatcher-ом без дублирующего runbook-текста, без route/date facts и без описания прежних неправильных шагов.

## Context
Текущее целевое понимание:

- Не создавать новые концептуальные сущности, если уже хватает существующей политики preferred airports / airport quality.
- Не вводить отдельный словарь хабов как самостоятельную новую модель, если это можно выразить через preferred airports и airport compatibility.
- Не создавать дополнительные “заметки с отсылками” вместо улучшения самого reference.
- Generic reference должен быть переписан как JSON Schema contract: компактная структура, контролируемые поля, положительные правила, validation gates.
- Reference должен быть без привязки к маршрутам, датам, flight numbers и конкретному SVX↔CDG кейсу.
- Golden answer остаётся примером качества ответа, но не источником generic route facts и не условием применения алгоритма.
- Для каждого нетривиального поиска skill должен применять live-first алгоритм: CLI/batched discovery, preferred-airport checks, безопасные стыковки, practical ticketing, затем цена.
- Cached API остаётся только source type / reconnaissance layer, но не gate для бизнес-рекомендации.

Проверенные источники перед обновлением плана:

- `skill_view(flight-search-routing)` показал текущий `SKILL.md`; при execution snapshot текущая версия уточнена как `2.3.1`, target bump остаётся `2.4.0`.
- `skill_view(flight-search-routing, references/business-flight-live-routing-algorithm.md)` показал текущий generic markdown reference, который нужно заменить/переписать.
- `skill_view(flight-search-routing, references/ist-exact-priority-svx-cdg-2026-08.md)` показал route-specific golden example; его нельзя превращать в generic contract.
- `/home/konstantin/docs/plans/README.md` прочитан: план для многошаговой правки skill должен жить в `/home/konstantin/docs/plans/` и иметь `Goal`, `Context`, `Non-goals`, `Steps`, `Verification`, `Risks / pitfalls`, `Status`.
- Holographic memory/fact_store: найден и обновлён существующий durable fact про flight searches так, чтобы он говорил про `preferred-airport policy`, а не создавал новую терминологию.

Memory/guardrails check:

- В injected `MEMORY` уже есть guardrail: `MEMORY = always-on guardrails + указатели, не база фактов`; значит длинный алгоритм должен жить в skill/reference, не в memory.
- В injected `MEMORY` есть запрет редактировать `MEMORY.md`, `USER.md`, `SOUL.md` без явного разрешения; этот план их не трогает.
- В fact_store есть hygiene rule: перед `add` сначала `search`; stale/wrong — `update/remove`. Поэтому существующий fact был обновлён, новая заметка/новая сущность не создавалась.
- В fact_store есть отдельный guardrail про Ollama Cloud: не использовать `json_schema` как режим constrained decoding для structured output. Это не конфликтует с задачей: здесь JSON Schema — формат reference-файла skill, не режим генерации модели.

## Non-goals
- Не выполнять саму перепаковку skill в рамках обновления этого плана без отдельной команды на выполнение.
- Не запускать новый поиск авиабилетов.
- Не редактировать `MEMORY.md`, `USER.md`, `SOUL.md`.
- Не вводить новые conceptual labels вместо существующей preferred-airport политики.
- Не создавать pointer-only заметки, которые просто ссылаются на другой файл.
- Не превращать JSON Schema reference в модельный `json_schema` enforcement для Ollama/OpenAI structured output.
- Не хранить route-specific факты SVX↔CDG в generic schema/reference.
- Не удалять golden answer artifact из `/home/konstantin/flight_search_artifacts/`; он остаётся сохранённым примером.
- Не раздувать `SKILL.md` повторением полного алгоритма, который должен жить в schema reference.

## Analysis
Текущий дефект — не в направлении, а в форме и связности интеграции.

Что оставить:

- Business-flight routing остаётся default для нетривиальных поисков.
- Preferred-airport policy остаётся главным способом выразить качество аэропортов и допустимость замен.
- Live CLI / saved artifacts остаются предпочтительным источником для рекомендаций.
- Cached API остаётся допустимым источником разведки, но не финальной проверкой.
- Golden answer остаётся примером формата ответа.

Что убрать или заменить:

- Убрать prose-runbook как generic reference.
- Убрать route/date/flight-number facts из generic reference.
- Убрать объяснения прежних ошибок и “не делай так, как раньше” из нормативного алгоритма.
- Убрать отдельную новую taxonomy, если её можно выразить через `preferred_airports`, `airport_compatibility`, `source_policy`, `ranking_policy`, `answer_contract`.
- Убрать pointer-only notes: если reference плохой, его нужно переписать, а не создавать ещё один слой ссылок.

Целевая архитектура:

1. `SKILL.md` — короткий dispatcher:
   - когда использовать skill;
   - default profile: business flight search;
   - обязательная загрузка JSON Schema reference для нетривиального поиска;
   - live-first source policy;
   - короткий список catastrophic airport mismatches;
   - verification checklist.

2. `references/business-flight-routing.schema.json` — единственный generic normative reference:
   - JSON Schema metadata;
   - preferred-airport policy;
   - airport compatibility policy;
   - source policy;
   - search pipeline contract;
   - candidate construction contract;
   - ranking policy;
   - answer contract;
   - validation gates.

3. Existing route-specific golden reference — example only:
   - не загружать по умолчанию;
   - не использовать как generic source of truth;
   - не переносить route facts в schema;
   - не создавать новый example pointer, если текущий файл можно просто оставить явно scoped.

## Proposed target files
- Modify: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md`
- Create/replace normative reference: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/references/business-flight-routing.schema.json`
- Remove old competing generic reference after replacement: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/references/business-flight-live-routing-algorithm.md`
- Modify only if needed for scope clarity: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/references/ist-exact-priority-svx-cdg-2026-08.md`
- Keep unchanged: `/home/konstantin/flight_search_artifacts/ist_exact_su_u6_tk_2026-08-15_20/golden_answer.md`

## Steps
- [x] Step 1 — Snapshot current skill state.
  - Load `flight-search-routing` with `skill_view`.
  - Load current generic markdown reference.
  - Load existing route-specific golden reference.
  - Do not edit before this snapshot.
  - Evidence 2026-05-05: snapshot read `SKILL.md` v2.3.1 (29,243 bytes), old generic reference (6,745 bytes), golden reference (5,909 bytes), and this plan (16,869 bytes).

- [x] Step 2 — Draft `business-flight-routing.schema.json` as the single generic reference.
  - Use JSON Schema vocabulary: `$schema`, `$id`, `title`, `description`, `type`, `required`, `properties`, `$defs`, `additionalProperties`.
  - Keep the schema route-independent: no origin/destination-specific examples, no concrete dates, no flight numbers.
  - The schema should describe the expected policy/config object and validation gates, not narrate history.

- [x] Step 3 — Encode defaults through existing preferred-airport policy.
  - Use fields such as `default_profile`, `preferred_airports`, `airport_compatibility`, `secondary_airport_policy`.
  - Do not introduce a separate top-level hub taxonomy if preferred-airport policy can express the rule.
  - Use positive rules: preferred, acceptable fallback, secondary requires explicit acceptance or named trade-off.

- [x] Step 4 — Encode airport compatibility as validation data.
  - Include primary mismatch checks such as `IST/SAW`, `DXB/DWC/SHJ`, `SVO/DME/VKO`, `LHR/LGW/LTN/STN`.
  - Express them as incompatible airport groups and preferred/fallback/secondary airport sets.
  - Avoid route-specific cases and old-case examples.

- [x] Step 5 — Encode source/search pipeline as policy contract.
  - `source_policy.priority`: live CLI artifacts first, non-RU segment schedule cross-check where useful, airline calendar where relevant, cached API as reconnaissance.
  - `artifact_policy.required_for`: multi-step searches, high-stakes recommendations, final itinerary claims.
  - `tool_economy`: prefer batched CLI and local artifact parsing over many individual tool calls.
  - `cached_api_policy`: define as source class with caveats, not as a story about wrong usage.

- [x] Step 6 — Encode candidate construction.
  - Normalize segment records: carrier, flight number, operating carrier if available, airports, local datetimes, duration, source, price hint.
  - Enforce airport compatibility and same-airport connection checks.
  - Encode connection buffer policy: same-airport separate-ticket minimum, business preferred buffer, cross-airport handling.
  - Include practical ticketing grouping as a ranking/answer field, not as route-specific advice.

- [x] Step 7 — Encode ranking policy.
  - Rank by business value: operational viability, elapsed time, preferred airports, connection safety, schedule quality, ticketing practicality, then price.
  - Preserve frontier representatives only when useful: main recommendation, safer alternative, schedule alternative, materially cheaper acceptable option.
  - Do not list rejected/tight options unless they prevent a plausible bad purchase decision.

- [x] Step 8 — Encode answer contract.
  - Brief status first.
  - Verified source facts next.
  - Main recommendation before price discussion.
  - Include local times/timezones, layovers, elapsed time, airport equality/compatibility, source caveats.
  - Include practical ticketing grouping when relevant.
  - Keep route-specific facts out of the generic schema.

- [x] Step 9 — Simplify `SKILL.md`.
  - Keep short default statement and dispatcher behavior.
  - Replace duplicated runbook text with pointer to `references/business-flight-routing.schema.json`.
  - Keep only minimal inline catastrophic mismatch examples.
  - Remove narrative about previous wrong steps.
  - Remove requirement-like phrasing tied to the user restating preferences.
  - Bump version from current observed `2.3.1` to `2.4.0`.

- [x] Step 10 — Remove the old generic markdown reference.
  - After schema exists and `SKILL.md` points to it, remove `references/business-flight-live-routing-algorithm.md`.
  - Do not replace it with a pointer-only note.
  - Verify no `SKILL.md` or reference list points to the removed file.

- [x] Step 11 — Keep the golden answer scoped as example only.
  - Keep existing route-specific reference only if its first scope lines clearly say example/regression only.
  - Do not move it or create new example wrapper unless needed for skill tooling.
  - Ensure loading discipline does not load it by default for every flight search.

- [x] Step 12 — Validate JSON and schema linkage.
  - Run JSON parse validation on `business-flight-routing.schema.json`.
  - If `jsonschema` package exists, validate a minimal sample policy object against the schema.
  - Use `skill_view(flight-search-routing)` to confirm `SKILL.md` points to the schema, and `skill_view(flight-search-routing, file_path=...)` to confirm the JSON schema is directly loadable. Current `linked_files` enumerates Markdown references and does not list `.json` files.
  - Search schema for route-specific tokens: `SVX`, `CDG`, `2026-08`, `U6773`, `TK1833`, `TK1822`, `U6774`.

- [x] Step 13 — Validate simplification.
  - Search `SKILL.md` and generic schema for stale old-reference phrasing.
  - Confirm generic instructions use existing preferred-airport terminology, not a new separate hub taxonomy.
  - Confirm old wrong-step narrative is gone from generic instructions.
  - Confirm cached API is expressed as source policy, not a cautionary essay.
  - Confirm JSON Schema is documented as a skill reference schema, not model structured-output enforcement.

- [x] Step 14 — Update this plan during execution.
  - Mark steps complete as they are done.
  - Add exact verification evidence to `Notes`.
  - Close/archive only after implementation is complete and verified.

## Verification
Implementation is complete only if all checks pass:

- [x] `references/business-flight-routing.schema.json` exists inside the `flight-search-routing` skill directory.
- [x] The schema parses as valid JSON.
- [x] The schema is route-independent: no `SVX`, `CDG`, `2026-08`, `U6773`, `TK1833`, `TK1822`, `U6774`.
- [x] The schema uses preferred-airport / airport-compatibility policy rather than creating a separate new hub taxonomy.
- [x] `SKILL.md` version is bumped to `2.4.0`.
- [x] `SKILL.md` points to `references/business-flight-routing.schema.json` as the default non-trivial flight-search reference.
- [x] `SKILL.md` no longer contains a long duplicated business-routing runbook.
- [x] Old generic markdown reference is removed, not replaced by a pointer-only note.
- [x] Existing SVX↔CDG golden reference remains available only as an example/regression artifact.
- [x] `skill_view(flight-search-routing)` shows the schema pointer in `SKILL.md`, and direct `skill_view(flight-search-routing, file_path='references/business-flight-routing.schema.json')` loads the schema. Note: current `linked_files` output lists Markdown references, not `.json` files.
- [x] No secrets, tokens, credential paths, raw logs, or unnecessary new notes are introduced.

## Risks / pitfalls
- JSON Schema can become too verbose if it tries to encode prose. Keep schema as contract and controlled vocabulary, not essay.
- Removing too much prose from `SKILL.md` can make the skill less discoverable. Keep a compact dispatcher plus reference pointer.
- Deleting the old markdown reference before updating `SKILL.md` would create a broken pointer. Update pointers first, then remove.
- Route-specific examples are useful for regression, but dangerous as defaults. Keep them clearly scoped.
- The phrase “JSON Schema” can be confused with model structured-output `json_schema`. Keep the distinction explicit.
- Creating new terminology when existing preferred-airport policy is sufficient will reintroduce the complexity this plan is meant to remove.

## Status
Current status: done

## Notes
- 2026-05-05: План создан по просьбе пользователя перед дальнейшей правкой skill. На этом шаге skill ещё не переписывался.
- 2026-05-05: План обновлён: убрана новая hub taxonomy как отдельная сущность, target reference уточнён как route-independent JSON Schema вокруг existing preferred-airport / airport-compatibility policy, pointer-only notes запрещены.
- 2026-05-05: Execution started after explicit user command. Snapshot confirmed current `SKILL.md` version `2.3.1`; plan version wording normalized to target bump `2.3.1 → 2.4.0`.
- 2026-05-05: Implementation completed and verified. Created `references/business-flight-routing.schema.json` (24,362 bytes, 863 lines, 16 top-level required fields, 6 `$defs`); simplified `SKILL.md` from 29,243 bytes / 233 lines to 8,666 bytes / 118 lines and bumped version `2.3.1 → 2.4.0`; updated golden reference scope to the new schema; removed old `business-flight-live-routing-algorithm.md`. Verification passed: JSON parse, Draft 2020-12 schema check, generated sample validation, forbidden schema tokens 0, stale old-reference/classic terms 0, secret-risk hits 0. Tool nuance: `skill_view` direct file load confirms the JSON schema, while `linked_files` currently lists Markdown references only.
