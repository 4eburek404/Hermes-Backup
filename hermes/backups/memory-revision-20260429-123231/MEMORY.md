Прошлый негативный опыт был с продуктом Hindsight (другой продукт, не holographic memory). Holographic memory — отдельный плагин, не судить по Hindsight.
§
Long-term docs live in /home/konstantin/docs/: README.md, user-context.md, infrastructure.md, runbooks.md, plans/. Read relevant file before changing Hermes/memory/cron/Codex/Ollama setup. Multi-step work needs a plan in plans/.
§
Многошаговые планы AI-агента всегда можно записывать в /home/konstantin/docs/plans/ без отдельного подтверждения; незаписанный план не считается планом.
§
Если пользователь говорит «не редактировать файлы» или просит plan-only/benchmark/dry-run, это включает docs, plans, skills, config, built-in memory, cron и credentials; допустимы только chat output или scratch в /tmp, если явно не разрешено иное.
§
Google-сервисы: Gmail (Himalaya CLI + App Password; exact path redacted in backup) и Calendar (service account; exact key path redacted in backup). Всё chmod 600.
§
Правила holographic памяти: 1) Перед fact_store add — всегда search. Похожий → update. 2) Изменения — update, не add. 3) memory add — только важное для built-in+holographic. 4) contradict раз в неск. сессий. 5) Устаревшее — remove сразу.
§
Execution gate rule: перед любой batch-операцией, меняющей состояние внешней системы (email, БД, API), перечитывать релевантную секцию skill непосредственно перед вызовом. Не полагаться на то, что skill был загружен ранее в сессии — attention LLM деградирует через 10+ ходов, и procedural habits (стандартные CLI-паттерны) пересиливают declarative knowledge из skill. Himalaya: delete, move, expunge — главные триггеры.
§
Урок из аудита крон-джобов: если крон-джоб отчитывается на неправильном языке — проверить model pinning. Null model = fallback на default, который может не знать русский. Всегда явно пинить модель и провайдер на каждом крон-джобе.
§
Дистилляция: cron/entry/orchestrator/curator — OpenAI Codex gpt-5.5; workers — glm-5.1:cloud, deepseek-v4-pro:cloud, gemma4:31b-cloud; timeout 200s; JSON: json_object+enums+strip_codeblock(), НЕ json_schema.