# Plan: memory architecture optimization

## Goal

Снизить always-on избыточность в `MEMORY.md`, `USER.md` и `SOUL.md` без потери behavioral enforcement: короткие триггеры остаются в always-on слоях, полные процедуры и rationale живут в skills/docs/fact_store.

## Context

Текущая архитектура уже движется к правильной схеме: built-in memory = compact guardrails + pointers; docs = human-readable context; skills = executable procedures; fact_store = atomic durable facts.

Проблема не только в размере, а в source-of-truth и enforcement:

- `MEMORY.md` был сжат, но всё ещё нуждается в повторной ревизии: сейчас он одновременно содержит guardrails, routing, holographic mini-protocol, promotion rule и лишний пример про `~/code/clis/`.
- `SOUL.md` (~9KB) содержит полезные behavioral rules, но часть текста процедурная и дублирует MEMORY/skills/docs.
- `USER.md` (~1.7KB) частично дублирует `docs/user-context.md`, но содержит важные always-on response triggers.
- `holographic-memory-hygiene` и `daily-knowledge-distillation` skills уже существуют; их не нужно создавать заново.
- `runbooks.md` уже содержит sections for do-not-edit interpretation, benchmark models, daily distillation, and holographic hygiene; нужен review, а не blind extraction.

## Non-goals

- Не править `MEMORY.md`, `USER.md`, `SOUL.md` без отдельного явного разрешения и diff review.
- Не удалять behavioral triggers только потому, что похожий текст есть в docs/skills.
- Не превращать docs или skills в replacement для always-on enforcement.
- Не создавать заново уже существующие skills.
- Не делать `/restart` или `/reset` при незавершённых writes; сначала завершить изменения и verification, потом запросить подтверждение пользователя.

## Design principle

Не устранять любое дублирование механически. Разделять:

- **Canonical full procedure**: skill/runbook/doc.
- **Always-on trigger / guardrail**: `SOUL.md`, `USER.md`, `MEMORY.md`.
- **Atomic durable fact**: `fact_store`.
- **Raw/session history**: `session_search`.

Минимальное дублирование safety/enforcement правил допустимо и полезно, если без него агент не загрузит нужный on-demand слой вовремя.

## Problems to solve

1. **MEMORY.md needs second revision**
   - Текущий размер около 1.3KB, не целевой ~1KB.
   - Содержит смесь: DO-NOT-EDIT, routing gate, promotion threshold, layer map, holographic mini-protocol, example `~/code/clis/`.
   - Нужно оставить только то, что действительно нужно на каждом ходе: self-protection guardrails + compact routing cues + holographic trigger pointer.

2. **SOUL.md is overlong but not disposable**
   - Нужно сжать процедуры, но сохранить behavioral enforcement.
   - Нельзя полностью удалять routing/holographic/skills/plans/activation boundary: они запускают нужное поведение до чтения docs/skills.

3. **USER.md duplicates docs/user-context.md but carries critical cues**
   - Нужно убрать verbose explanations, но сохранить high-impact response triggers.
   - Цель не 500–800B любой ценой; безопаснее 900–1200 chars, если это сохраняет качество.

4. **Docs/runbooks have overlap with skills**
   - Нужно проверить, где runbooks дублируют skill procedures.
   - Оставлять short pointers/rationale в docs; executable details — в skills.

5. **Plan governance drift**
   - Этот plan должен иметь `Goal`, `Non-goals`, `Steps`, `Verification`, `Risks / pitfalls`, `Status`.
   - Sensitive memory work needs backups, diffs, and verification before claiming done.

## Steps

- [x] Read current plan, plan governance, and current `MEMORY.md` before updating this plan.
- [x] Inventory current live state:
  - [x] read `/home/konstantin/.hermes/SOUL.md`;
  - [x] read `/home/konstantin/.hermes/memories/USER.md`;
  - [x] read `/home/konstantin/.hermes/memories/MEMORY.md`;
  - [x] confirm skill availability for `holographic-memory-hygiene` and `daily-knowledge-distillation`;
  - [x] inspect relevant `docs/infrastructure.md`, `docs/runbooks.md`, `docs/user-context.md` sections.
- [x] Prepare proposed diffs only:
  - [x] `MEMORY.md` revised compact version;
  - [x] `SOUL.md` revised compact constitution;
  - [x] `USER.md` revised compact profile;
  - [x] docs/runbooks pointer cleanup checked; no immediate edit needed.
- [x] Review `MEMORY.md` first:
  - [x] keep DO-NOT-EDIT / no restart-reset unfinished writes guardrail;
  - [x] keep default-deny memory routing gate;
  - [x] keep concise pointer to holographic hygiene skill;
  - [x] remove or move non-every-turn examples/details;
  - [x] target around ~1KB, but not by deleting safety-critical cues.
- [x] Compress `SOUL.md` conservatively:
  - [x] keep 6 principles;
  - [x] keep permission model;
  - [x] compress knowledge routing to short behavioral trigger;
  - [x] compress holographic protocol to trigger + minimal loop, not full audit procedure;
  - [x] compress skills/docs/plans rule to enforcement cue;
  - [x] keep activation boundary in 1–2 lines.
- [x] Compress `USER.md` conservatively:
  - [x] keep identity/language/timezone/role;
  - [x] keep deep-analysis expectation;
  - [x] keep checked-facts vs hypotheses expectation;
  - [x] keep compact-conclusion preference;
  - [x] keep exact-cause attribution;
  - [x] keep copyable commands/links cue;
  - [x] keep repo/deploy and debugging/root-cause guardrails if still needed always-on.
- [x] Apply changes only after explicit approval of diffs.
- [x] Post-edit verification:
  - [x] reread changed files;
  - [x] check sizes/line counts;
  - [x] search docs/skills for stale references;
  - [x] check no secrets/token-like values introduced;
  - [x] verify skills referenced by MEMORY/SOUL exist;
  - [x] after all writes complete, ask user whether to `/reset`/fresh-session verify prompt behavior.

## Proposed target architecture

- `MEMORY.md`: ~1KB, guardrails + routing cues + holographic hygiene pointer. No ordinary facts, no procedures, no examples that are not needed every turn.
- `USER.md`: compact always-on communication contract, likely ~900–1200 chars rather than arbitrary 500–800B.
- `SOUL.md`: compact behavioral constitution, likely ~3.5–5KB rather than unsafe 2KB target.
- `docs/user-context.md`: expanded preferences, rationale, work-context hypotheses.
- `docs/infrastructure.md`: current system map, memory architecture, paths, operational risks.
- `docs/runbooks.md`: short repeatable procedures and pointers to canonical skills.
- Skills: full executable procedures, including holographic memory hygiene and daily distillation.
- `fact_store`: atomic durable facts with entity recall and trust scoring.
- `session_search`: detailed raw history and temporary progress.

## Verification

Success means:

- `MEMORY.md`, `USER.md`, `SOUL.md` are smaller or better layered without losing enforcement-critical cues.
- No direct behavioral trigger exists only in an on-demand file that the agent might not load.
- Referenced skills actually load.
- Docs/runbooks point to canonical skills where appropriate and do not contain stale source-of-truth claims.
- DO-NOT-EDIT and no-restart-with-unfinished-writes guardrails remain effective.
- Activation boundary remains documented enough to prevent false claims that SOUL edits apply to the current cached prompt immediately.
- Final report separates verified file changes from hypotheses and proposals.

## Risks / pitfalls

- Over-compressing `SOUL.md` can remove the trigger that makes the agent load the right memory/docs/skills.
- Over-compressing `USER.md` can degrade normal answers because `docs/user-context.md` is not read every turn.
- Treating all duplication as bad can remove intentional safety redundancy.
- Moving `/restart` guardrail only to docs/runbooks is unsafe; it must remain always-on.
- Using size targets as hard KPIs can optimize bytes instead of behavior.
- Claiming changes are active immediately is wrong if current session uses cached system prompt.
- Creating duplicate skills/facts because search missed hidden/archive skill locations.

## Status

Current status: done

## Notes

Updated after review: the previous plan was too deletion-oriented. Revised approach prioritizes enforcement preservation, adds `MEMORY.md` second revision as first-class work, and treats existing skills/docs as current artifacts to audit rather than recreate blindly.

Completed 2026-05-03: backed up protected files to `/home/konstantin/.hermes/backups/memory-architecture-optimization-20260503-193937`; applied approved compact versions of `MEMORY.md`, `USER.md`, and `SOUL.md`; verified content, sizes, referenced skills, stale plan references, and no token-like strings in active changed files. Fresh-session/reset verification remains a separate user decision because current session may use cached prompt snapshot.
