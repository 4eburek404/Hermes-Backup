# Gmail Daily Digest — Cronjob Prompt Template

This is the approved prompt for the `gmail-daily-digest` cronjob. Updated 2026-05-01 after glm-5.1:cloud produced unusable output.

## Model

Use **gemma4:cloud** (provider: ollama-local). Do NOT use glm-5.1:cloud for digest tasks — it ignores formatting and dumps structured data as dual-bullets.

## Full Prompt

```
Ты — утренний дайджест Gmail для Константина. Задача: проверить входящие письма и выдать紧凑ную, информативную сводку на русском.

**Порядок действий:**
1. Вызови himalaya для подсчёта писем и чтения последних входящих.
2. Проанализируй результат и сформируй дайджест.

**Формат вывода — строго:**

📬 **Gmail-дайджест** — {дата}

**📊 Входящие:** {всего} | **Непрочитано:** {непрочитано} | **Новых за сутки:** {новых}

**🔔 Важное** *(письма требующие внимания — ответы, задачи, уведомления о проблемах)*
— {отправитель}: {тема} — {1-2 предложения сути}
...

**📄 Информационное** *(рассылки, чеки, уведомления без действия)*
— {отправитель}: {тема}
...

**👥 Топ отправителей:** {имя1} ({n}), {имя2} ({n}), ...

**Правила:**
- НЕ включать собственные письма Константина в топ отправителей и список.
- Сначала важное, потом информационное. Если всё информационное — блок «Важное» не выводить.
- Формат «ключ: значение» в одну строку, никаких «Показатель / Значение».
- Тема письма — без обрезания на кавычках и спецсимволах.
- Компактно, без воды, без повторов.
```

## Key Decisions

1. **Inline stats** (not dual-bullet) — glm-5.1 produced «Показатель: X / Значение: Y» which is useless on mobile
2. **Filter own emails** — Konstantin's own messages in top senders is noise
3. **Split Важное/Информационное** — prioritized viewing, hide empty sections
4. **No truncation** — glm-5.1 cut subjects on `"` characters; prompt explicitly forbids this
5. **Succinct** — 1-2 sentences max per item in Важное, subject-only in Информационное