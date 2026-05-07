# MEMORY.md Optimization Session — 2026-05-03

## What happened

User reported VPS provider was hacked, server disappeared. During incident response, agent attempted to write an incident fact into MEMORY.md instead of fact_store. This triggered a full architecture review.

## Key decisions (user-corrected)

1. **Default-deny routing**: BY DEFAULT do not write to MEMORY.md. Gate test: «Нужен на КАЖДОМ ходу?» — only identity, preferences, cues pass.
2. **Promotion threshold**: 5+ independent retrievals from fact_store (corrected from 3+).
3. **Budget**: ~1KB for MEMORY.md (corrected from 2KB). Always-on context is expensive.
4. **Episodic facts → fact_store**: Server incidents, project details, service configurations all belong in fact_store with entity tags, not in always-on context.
5. **MEMORY.md does NOT list entities**: Retrieval cues should say «инфраструктура — fact_store» not enumerate «(Hermes, CLIs, fli, server)». Entity names are detail for on-demand retrieval.
6. **Holographic protocol lives in skill**: Full 5-step protocol moved from SOUL.md to this skill. MEMORY.md §3 has a one-line pointer.
7. **Layer routing canonical in MEMORY.md**: SOUL.md should not duplicate routing rules.

## Final MEMORY.md structure (2026-05-03)

```
§ DO-NOT-EDIT: MEMORY.md, USER.md, SOUL.md — не править без разрешения; запрос → diff. Без /restart|/reset при незавершённых writes (файлы, fact_store, cron, config) — сначала завершить, потом подтверждение. Внешний краш — исключение.
§ MEMORY = guardrails + указатели. По умолчанию — не писать. Gate: «Нужен на КАЖДОМ ходу?» — да → MEMORY.md (identity, preferences, cues). Нет → fact_store (инциденты, проекты, сервисы, эпизодика); skills (процедуры); docs/ (canonical context). Promotion: 5+ обращений из fact_store → ссылку. Бюджет ~1KB; превышение → evacuate в fact_store + указатели.
§ Слои: USER.md — профиль; SOUL.md — конституция; docs/ — контекст (infrastructure, runbooks, user-context, plans/); skills — процедуры (CLI ~/code/clis/ — 1 вызов вместо цепочки); fact_store — atomic facts + entity resolution + trust scoring. Holographic: probe/search → ответ → fact_feedback; add → search first (похожий → update); stale → update/remove; гигиена → skill holographic-memory-hygiene.
```

## Architecture research sources

See `references/memory-routing-research.md` for MemGPT/Letta, Zep, LangGraph, Claude memory, and cognitive science foundations (Miller, Baddeley, Cowan, Ericsson & Kintsch).

## Pending optimization (plan at /home/konstantin/docs/plans/memory-architecture-optimization.md)

1. Create holographic-memory-hygiene skill (DONE — this is it)
2. Trim SOUL.md: remove routing, holographic protocol, analysis section → 2-3KB
3. Trim USER.md: core identity only → 500-800B
4. Cross-reference consistency: /restart guardrail, holographic protocol
5. Verify docs/runbooks references point to existing skills