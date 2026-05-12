# context-input-baseline

Цель: добавить read-only диагностику input-context overhead в Hermes без изменения runtime-поведения.

## План
1. Начать с чистого клона `origin/main` и создать ветку `context-input-baseline`.
2. Найти форматы session/request dumps и существующие метрики token/session analytics.
3. Добавить `scripts/analyze_context_overhead.py`:
   - читает локальные session/request dumps;
   - строит markdown и json отчёты;
   - считает totals, averages, breakdowns, oversize hotspots, cache/compression markers.
4. Добавить fixtures и минимальные тесты парсера/генератора отчёта.
5. Добавить документацию запуска в `docs/context-baseline.md`.
6. Прогнать help/report/pytest и проверить, что в diff нет секретов и реальных дампов.

## Ограничения
- Не менять prompt builder, context compressor, toolsets, skills loading или пользовательский config.
- Не трогать реальные sessions/logs/request dumps.
- Все изменения должны быть обратимыми.
