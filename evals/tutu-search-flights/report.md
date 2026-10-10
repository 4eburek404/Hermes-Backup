# Tutu Search-Flights — проверка и офлайн-переоценка

Дата завершения: 10 октября 2026 г.
Ветка: `new-tutu`
Исходный SHA до этой работы: `55effd14b8245125cf9c47e65aad4dd84e8ec24a`
SHA контрольного снимка исходного рабочего дерева: `dfee765aff46bb9a799a60a9d40ef3f3449f26bf`
SHA версии evaluator для всех шести переоценок: `4ddcc7e0e8431d3327d9bfa2b7c58d6d2d1e1da9bb54f61f1080f19dc6fab9f5`

## Матрица исходных и новых оценок

Обозначения: O — outcome, T — trajectory, P — privacy. Новая оценка получена из сохранённых трасс; `ERROR`/`UNDEFINED` не трактуется как PASS или подтверждённый FAIL.

| Сценарий | Модель | Исходная O / T / P | Новая O / T / P |
|---|---|---|---|
| `search-results-reflect-tutu` | GPT-6 Luna | PASS / FAIL / UNDEFINED | PASS / FAIL / UNDEFINED |
| `missing-cabin-baggage-weight` | GPT-6 Luna | PASS / FAIL / UNDEFINED | PASS / ERROR / UNDEFINED |
| `party-price-and-fare` | GPT-6 Luna | FAIL / FAIL / UNDEFINED | PASS / ERROR / UNDEFINED |
| `search-results-reflect-tutu` | Nemotron 3 Ultra | FAIL / FAIL / UNDEFINED | FAIL / FAIL / UNDEFINED |
| `missing-cabin-baggage-weight` | Nemotron 3 Ultra | FAIL / FAIL / UNDEFINED | ERROR / ERROR / UNDEFINED |
| `party-price-and-fare` | Nemotron 3 Ultra | FAIL / FAIL / UNDEFINED | PASS / ERROR / UNDEFINED |

## Причины изменений и итоговые ограничения

- В трассах Scenario 3 у обеих моделей корректная длительность `3 ч 40 мин` раньше давала ложный Outcome FAIL: evaluator разбирал часы и минуты раздельно. Исправленный парсер сопоставил общую длительность с fixture; O изменился FAIL → PASS. Проверены также краткая запись `3ч 40м`, часовой пояс `+03:00` и `(RUB)`.
- Для GPT-6 Luna в Scenario 2 MCP fixture был обслужен на повторном вызове, но сохранённый результат CLI обрезан и не содержит `exit_code`. Поэтому прежний Trajectory FAIL уточнён до `ERROR` (недостаточно доказательств), а не повышен до PASS. В Scenario 3 та же причина: fixture обслужен, но exit code не зафиксирован.
- Для Nemotron в Scenario 2 трасса заканчивается HTTP 429 до инструментального выполнения. Исходный FAIL заменён на `ERROR` для Outcome и Trajectory: качество ответа и прохождение маршрута не наблюдались.
- В Scenario 1 trajectory остаётся FAIL у обеих моделей. Для GPT запрос содержал `view=full`; схема Tutu задаёт default `compact`, поэтому это не эквивалентный аргумент. Для Nemotron первый вызов менял маршрут на IATA-коды MOW/AER, второй не получил fixture из-за отличающегося набора аргументов. Изменение маршрута не считается эквивалентностью.
- Эквивалентность replay допускает только значения схемы `search_avia` по умолчанию для `adults=1`, `page=1`, `sort=price_asc`, `view=compact`, когда ключ отсутствует в ожидаемых аргументах. `page_size` не ослаблялся; пассажиры, маршрут, дата и фильтры остаются точными. Основание — записанная схема `hermes/skills/travel/tutu-search-flights/fixtures/meta/tools-list.json`.
- Ни одна неопределённая оценка не повышена до PASS; P остаётся `UNDEFINED` вне области сценариев. Оценки не подтверждают ранжирование моделей или устойчивость по повторным прогонам.

## Проверки

- `PYTHONPATH=. pytest -q tests/contract/test_tutu_search_flights_eval_contract.py` — **16 passed**.
- `pytest -q tests/contract` — **139 passed**.
- `py_compile` для evaluator, replay и reassessment CLI; `run_eval.py --help`; `reevaluate_saved.py --help` — **PASS**.
- Офлайн-переоценка: **6/6** сохранённых трасс; `agent_execution_count=0` относится к самой переоценке. В исходных сохранённых запусках зафиксирован `agent_execution_count=1` на каждый run — эти исторические значения оставлены без изменений. Все новые оценки помечены одной версией evaluator SHA `4ddcc7e0…`. Агент, semantic judge и сетевые запросы при переоценке не запускались.
- Первый прямой запуск целевого модуля без `PYTHONPATH=.` завершился ошибкой импорта `evals`; повтор с корнем проекта в `PYTHONPATH` прошёл. Полный contract-набор также прошёл.

## Доказательства и безопасность

Артефакты находятся в `evals/tutu-search-flights/reassessments/evaluator-v3/`:

- `batch_manifest.json` — все шесть run ID, статусы, `agent_execution_count=0` и общий evaluator SHA;
- `original-scores/` — отдельные побайтные копии первоначальных `score.json`;
- каталоги по run ID — новые `score.json`, диагностические причины, evidence и ссылки на события;
- `raw-traces/` — сохранённые исходные потоки и имеющиеся MCP boundary traces;
- `source-manifest.json` и `event-refs.json` — SHA-256 исходников/копий и ссылки на события. Исходные файлы под `~/.hermes/evals/.../20261009-comparison/` не изменялись.

Проверка публикуемых артефактов на типовые credential/token маркеры, email-адреса и приватные IP не выявила совпадений. Это проверка по шаблонам, не формальная гарантия отсутствия любых чувствительных данных.

Промежуточные evaluator-v1/v2 удалены после сравнения содержимого. Отличающиеся исторические результаты v1 (14 файлов) и batch manifest v2 (1 файл), отсутствовавшие по тем же путям/в байтах в v3, сохранены в `reassessments/evaluator-v3/intermediate-history/` с SHA-256; они явно архивные и не участвуют в активной матрице v3.

## Публикация

Контрольный снимок исходного рабочего дерева сохранён отдельным commit `dfee765aff46bb9a799a60a9d40ef3f3449f26bf`. Финальный commit и remote SHA указаны в сообщении о завершении этой задачи.
