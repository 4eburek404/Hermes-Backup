# Build auto diagnostics (happy-path oriented)

Этот файл фиксирует **реальную причину «агент клинит»** при простом `build auto`: не падение слоя агента, а детерминированный ранний контрольный fail в CLI.

## Частый фальстарт: route inference

1. `--json build auto` сначала делает `infer_build_route(...)`.
2. Если данных недостаточно или сигнатура многозначна, команда возвращает `ok=false` с кодами вроде:
   - `route_input_insufficient`
   - `route_ambiguous`
   - (реже) `route_unknown`
3. Признак в логике: шаг `infer_route` есть в `process`, но нет ручного `route=...` или дальнейшей сборки.

На практике это особенно вероятно для:
- `https://example.com?...` и других неизвестных host без строгой привязки,
- неполных ссылок на домен перевозчика без параметров брони.

## Что делать последовательно (минимум шума)

1. `diagnose route-detect` перед `build auto`:
   - `python <SKILL_DIR>/scripts/flight_calendar_ics.py --json diagnose route-detect --url <...>`
   - проверяем `route`, `confidence`, `evidence`, `code` ошибки.
2. Если inference OK и маршрут понятен, повторяем `build auto`.
3. Если inference OK, но build всё ещё fail:
   - смотрим `error.code` из CLI envelope,
   - затем при необходимости `diagnose bundle-check --bundle-dir` (после `--json build auto --output-dir ...` в debug-сценарии),
   - и/или `diagnose validate --input <itinerary.json>`.

## Гарантия готового handoff (для агента)

Агент считает путь успешным только при код-валидном handoff с:
- `data.agent_handoff.ready == true`
- `data.agent_handoff.artifact_inspection_required == false`
- `data.agent_handoff.safe_summary.verification_ok == true`

Проверки `ready` завязаны на:
- `segments_count >= 1`
- `verification.ok == true`
- `event_count == segments_count`
- `ics_mode == "0600"`

## Куда не смотреть на happy path

- Не нужно искать «красивую» реализацию `def command_aeroflot` в `aeroflot.py` при диагностике маршрута: точка входа для Aeroflot находится в `parser.py` как `command_aeroflot`.
- Не менять маршрутизацию вручную до появления нового, безопасного доказательства из `diagnose route-detect`.
