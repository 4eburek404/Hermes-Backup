# Plan: memory hygiene

## Goal
Провести read-first гигиену holographic/built-in memory: проверить конфигурацию, SQLite/FTS/entity health, built-in memory pressure, противоречия и явные дубликаты/stale-кластеры; выполнить только безопасные минимальные изменения, если они прямо следуют из запроса и верифицируются.

## Context
Константин попросил: "run гигиену памяти". Релевантные процедуры: skill `holographic-memory-hygiene`, `hermes-agent`, plan governance. Для destructive bulk cleanup нужен audit report; прямой запрос разрешает cleanup, но удаления/объединения должны быть точечными и проверенными.

## Non-goals
- Не редактировать `MEMORY.md`, `USER.md`, `SOUL.md` без отдельного явного разрешения.
- Не включать automatic extraction.
- Не сохранять сырые логи/секреты в план или память.
- Не удалять факты только из-за низкого trust/retrieval_count.

## Steps
- [x] Проверить live memory provider/config и SQLite метрики.
- [x] Проверить FTS5/entity extraction health и pressure built-in memory.
- [x] Получить inventory через `fact_store list`, explicit contradictions и targeted duplicate/stale clusters.
- [x] Если есть безопасные очевидные cleanup-действия, выполнить минимально и проверить; иначе зафиксировать proposed mutations.
- [x] Обновить статус плана и архивировать после verification.

## Verification
- Provider/config и DB metrics получены из live tools/scripts.
- FTS5/entity health проверены скриптом: 15 passed, 0 failed, `STATUS: HEALTHY`.
- `fact_store` semantic view использован: `list`, `contradict`, targeted `search`/`probe` clusters.
- Mutations выполнены точечно: updated facts `116,126,119,143,140,138,96,100,103,44,128,53,46`; removed facts `115,117,120,125,127,114,86,102,144,145,141,139,97,99,101,108,80,106,124`.
- Post-mutation verification: `facts=70`, `facts_fts=70`, removed IDs absent, `contradict` returned 0.
- Итоговый отчёт отделяет проверенные факты от экспертных гипотез.

## Risks / pitfalls
- `retrieval_count` может быть ненадёжен и не должен быть основанием для удаления.
- `contradict=[]` не доказывает отсутствие semantic duplicates.
- Cron/model/provider/ACL/current-state facts быстро устаревают и требуют live verification перед утверждением как текущей истины.
- Backups могут сохранять секреты; не создавать лишние dumps.

## Status
Current status: done

## Notes
- Closed 2026-05-05 19:52:50 CEST +0200 after live verification.
- Holographic provider active; plugin available; `auto_extract=false`.
- Live DB after cleanup: 70 facts, 70 FTS rows, 284 entities, 336 fact-entity links, 4 memory banks; categories: project 21, user_pref 30, general 9, tool 10; tagged facts 55.
- Built-in memory pressure low enough for current guardrail shape: `USER.md` 999 chars / 14 lines; `MEMORY.md` 934 chars / 4 lines.
- Main stale/duplicate clusters consolidated: news delegation, simplicity/anti-overengineering, Паша Calendar color, holographic FTS/entity health, flight-search thresholds/contracts/cache/tooling, VPS/Nimb/OpenClaw incident state, Ollama cloud model availability.
- VPS/Nimb/OpenClaw cleanup is explicitly not marked complete; fact 96 records incomplete state until reverified.
