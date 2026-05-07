# Plan: Interaction patterns ensemble analysis

## Goal
Глубоко проанализировать историю взаимодействий Константина с Hermes/агентом: выделить эффективные паттерны, повторяющиеся ошибки, guardrails и практические правила поведения. Запустить ансамбль моделей GLM 5.1, DeepSeek V4 Pro и Gemma на одинаковом raw JSON evidence-пакете, затем дать итоговый отчёт с разграничением evidence/гипотез/ограничений.

## Context
Запрос из Telegram 2026-05-06: «Анализируй наше с тобой взаимодействие по истории сессий ... дай raw json на анализ ... Сделай ансамбль из glm5.1, DeepSeek-v4-pro, gemma4b ... Потом с вас отчёт».

Релевантные ограничения:
- не сохранять raw transcripts, секреты, токены, credential paths;
- для cloud Ollama моделей использовать HTTP API `http://127.0.0.1:11434/v1/chat/completions`, не `ollama run`/`ollama pull`;
- DeepSeek V4 Pro может тратить completion budget на hidden reasoning и вернуть неполный JSON — это нужно отразить как ограничение, если повторится;
- итог должен быть не summary, а анализ/выводы.

## Non-goals
- Не менять USER.md/MEMORY.md/SOUL.md, cron, config, skills или docs по результатам анализа без отдельного запроса.
- Не сохранять долговременные факты/правила в fact_store/memory в рамках этой задачи, если пользователь явно не попросит.
- Не выгружать пользователю полные raw transcripts.

## Steps
- [x] Собрать контекст из session_search, fact_store и релевантных docs/skills.
- [x] Сформировать обезличенный/безопасный raw JSON evidence-пакет для анализа моделей.
- [x] Запустить GLM 5.1, DeepSeek V4 Pro и Gemma на одинаковом JSON-пакете через Ollama HTTP API.
- [x] Сохранить raw model outputs и сводный JSON-артефакт во временный/рабочий файл без секретов.
- [x] Синтезировать собственные выводы gpt-5.5 + выводы ансамбля в отчёт для Telegram.
- [x] Проверить наличие артефакта, отсутствие секретов/raw transcripts и закрыть/архивировать план.

## Verification
- Есть файл raw JSON/ensemble output, путь проверен.
- Все три модели либо вернули анализ, либо явно зафиксирована причина сбоя/ограничение.
- Итоговый отчёт разделяет проверенные факты, интерпретацию/гипотезы, эффективные паттерны, ошибки и guardrails.
- План закрыт и архивирован после выполнения.

## Risks / pitfalls
- DeepSeek V4 Pro может вернуть truncation/parse error из-за hidden reasoning.
- Session_search даёт summaries, а не полный transcript; выводы нужно маркировать как evidence from summaries/docs/fact_store, а не абсолютную истину.
- Слишком большой evidence-пакет ухудшит JSON compliance; нужен компактный, high-signal пакет.
- Нельзя превращать единичную ошибку в широкое правило без повторяемости/прямого подтверждения.

## Status
Current status: done

## Notes
Создан как task-control plan; не является долговременной базой знаний.
2026-05-06: Выполнено. Артефакты: `/tmp/interaction_patterns_ensemble_20260506/raw_evidence_packet.json`, `/tmp/interaction_patterns_ensemble_20260506/interaction_patterns_full_raw.json`, `/tmp/interaction_patterns_ensemble_20260506/interaction_patterns_synthesis.json`. Все три модели вернули parseable JSON; secret scan по token-like/private-key/sensitive credential-path regex дал 0 совпадений.
