# Memory Architecture Refactoring — 2026-05-01

## Context

User initiated a review of MEMORY.md architecture after reading an article about SOUL.md and context management. The article argued that always-on context should be minimized — load only what's needed per task. This triggered a deep audit of the entire knowledge layering system.

## Process

1. Analyzed current MEMORY.md (11 entries, ~1300 chars, 58% of capacity).
2. Analyzed current USER.md (10 entries, ~1375 chars).
3. Reviewed SOUL.md (49 lines, 4459 bytes).
4. Listed all fact_store entries (34 facts).
5. Reviewed docs/ (infrastructure.md, runbooks.md, user-context.md, plans/).
6. Delegated analysis to two external models (DeepSeek v4-pro and GPT-oss 120b) for independent opinions.
7. Synthesized findings with user corrections.

## Key Decisions (with user corrections)

### What was removed from MEMORY and why

| Entry | Why removed | Where it lives now |
|---|---|---|
| Hindsight ≠ Holographic | Covered by SOUL principle 3 and USER.md | SOUL, USER |
| Cron: pin model+ TZ | Operational procedure, not always-on | runbooks.md, fact_store |
| Known-wrong (ollama only) | Expanded into compound entry with #2 and #3 | MEMORY (kept, expanded) |
| Не путать текущий год | Not a real recurring error | Removed entirely |
| Context-switch: ask before switching | User said "your invention" — removed | Removed entirely |
| Execution gate: re-read skill | Covered by SOUL principle 5 and skill | SOUL |
| Credentials + Gmail personal | Gmail: "ты что прицепился к почте моей?! Отвянь!" — 3 copies already exist in USER, fact_store, user-context. Credentials: searchable from runbooks | USER.md, fact_store, runbooks.md |
| Plans pointer | Duplicated Docs pointer | Merged into Docs entry |
| DO-NOT-EDIT guardrail | Kept in MEMORY | — |
| Holographic hygiene (old verbose) | Compressed into compact version | MEMORY (new) |
| MEMORY = index/pointers | Architectural principle, not always-on fact | SOUL knowledge layers |

### What was removed from USER.md and why

| Entry | Why removed | Where it lives now |
|---|---|---|
| Compact curated-memory preference | Duplicates MEMORY § Holographic | MEMORY |
| Google services App Password | Searchable from fact_store #9, user-context.md | fact_store, user-context.md |
| Gmail personal-only | "Отвянь" — 3 redundant copies exist | fact_store #20, user-context.md |

### Critical user corrections during analysis

1. **"Context-switch — это твои додумки"**: The context-switch rule was not requested by the user. It was invented by the agent after a single incident. Removed.
2. **"Gmail — ты что прицепился к почте моей?!"**: Gmail personal-only rule was over-protected. It already existed in 3 places (USER.md, fact_store, user-context.md). Adding it to MEMORY was agent over-protection, not genuine safety.
3. **"Hindsight не нужен, забудь совсем"**: Covered by SOUL and USER.md. No need for a third copy.
4. **"Holographic куда дел? Сосредоточься, важное упускаешь!"**: When asked to simplify, agent initially proposed removing Holographic hygiene — which is a self-referential meta-rule about MEMORY itself (the bootstrap problem from GPT-5.5 analysis). User caught the error.

### The "bootstrap problem" (from GPT-5.5 analysis)

Self-referential rules (rules about how to use MEMORY itself) MUST be in always-on MEMORY. If they're moved to fact_store or docs, the agent won't think to search for them before modifying MEMORY — which is exactly when the rule is needed. Holographic hygiene is the prime example: "search before add" prevents pollution, but an agent that doesn't have this rule in context won't search for it before adding.

## Final Architecture

### MEMORY.md (4 entries, 601 chars, 27% capacity)

```
§ Docs: /home/konstantin/docs/ — infrastructure.md, runbooks.md, user-context.md, plans/. Читать релевантный файл перед изменениями.
§ Known-wrong: (1) ollama run/pull :cloud = ENOSPC → HTTP API; (2) json_schema не работает для Ollama Cloud → json_object + enum; (3) теги моделей точные: gemma4:31b-cloud не :cloud.
§ Holographic: search before add → update не duplicate. Устаревшее → update/remove. Нет ценности → не сохранять. auto_extract = off.
§ DO-NOT-EDIT: MEMORY.md, USER.md, SOUL.md — не править без явного разрешения; при запросе — показывать diff. Остальные файлы тоже только по разрешению.
```

### USER.md (7 entries, 970 chars, 70% capacity)

Identity, analysis style, fact/hypothesis separation, compact conclusions, attribution, brief format, branch-first workflow.

### SOUL.md (updated after restoration)

The initial cleanup proposal made SOUL too compact and removed behavioral teeth. On 2026-05-01 Konstantin explicitly asked to restore the behavioral constitution. The active `~/.hermes/SOUL.md` was rewritten as a merged constitution: old strong invariants + useful knowledge-layer routing + permission model + activation boundary.

Required SOUL invariants now include: fact vs hypothesis boundary, precise cause attribution, proactive intelligence/reactive mutation, anti-dead-weight routing, strict holographic retrieval+hygiene protocol, skill/docs/plan discipline, analysis/communication rules, permission model, and prompt-snapshot activation caveat.

See `references/soul-behavioral-constitution.md` for the restoration details and future editing checklist.

### DO-NOT-EDIT guardrail location

The explicit core-file guardrail remains in MEMORY: `MEMORY.md`, `USER.md`, and `SOUL.md` must not be edited without explicit permission. SOUL may still contain the broader permission model as a behavioral law; this is not the same as duplicating the literal DO-NOT-EDIT guardrail.

## Lessons

1. **Over-protection is a real anti-pattern.** When a rule exists in 3+ places (Gmail, credentials), adding it to MEMORY doesn't increase safety — it increases noise and maintenance burden.
2. **"Would I know to search for this?" is the right test**, but "would I search" ≠ "should this be always-on". Rules about MEMORY itself (holographic hygiene, DO-NOT-EDIT) are self-referential and fail the search test.
3. **External model analysis is valuable** for architecture decisions. Both models caught things the primary agent missed (bootstrap problem, json_schema quirk, over-protection pattern).
4. **User corrections are first-class signals.** "Твои додумки" and "отвянь" are strong corrections that override agent analysis.