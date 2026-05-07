# Plan: Daily Knowledge Distillation Cron

## Goal

Создать ежедневный cron на 21:00 по времени Константина, который дистиллирует знания за день: извлекает самое полезное из дневных сессий, аккуратно актуализирует файлы в `/home/konstantin/docs/`, избегает дублей, удаляет/заменяет устаревшие записи и присылает краткий отчёт в Telegram.

## Context

- Пользователь: Konstantin Orlov, timezone UTC+5 / Asia/Yekaterinburg.
- Host timezone на момент планирования: CEST UTC+2 (`2026-04-27 21:48:42 CEST +0200`).
- Значит 21:00 пользователя = 18:00 host time, cron expression: `0 18 * * *` при текущем host timezone.
- Долгосрочные docs: `/home/konstantin/docs/`.
- Плановая папка: `/home/konstantin/docs/plans/`.
- Политика памяти: curated, не auto-extract мусор, не добавлять бездумно, не хранить секреты.

## Non-goals

- Не включать внешний memory provider.
- Не складывать в docs полные логи разговоров или сырые outputs.
- Не создавать «дневник выполненных задач» ради дневника.
- Не перезаписывать большие разделы без причины.
- Не сохранять OAuth-токены, API keys, секреты.

## Skill assessment

Skill для этого процесса **желателен**, потому что задача повторяемая, сложная и имеет важные правила качества:

- извлечь знания за день;
- отличить устойчивое знание от временной детали;
- найти правильный файл назначения;
- проверить дубли;
- обновить/заменить устаревшее, а не только добавлять;
- сделать отчёт о внесённых и отклонённых изменениях.

Но skill нужно создавать только после явного подтверждения пользователя. До создания skill cron должен иметь self-contained prompt с полным алгоритмом.

## Steps

- [x] Зафиксировать план в `/home/konstantin/docs/plans/`.
- [x] Создать ежедневный cron на 21:00 UTC+5 / 18:00 host CEST.
- [x] Дать cron self-contained prompt с алгоритмом curated distillation.
- [x] Дать cron доступ к `session_search`, `file`, `terminal`.
- [x] Проверить созданный cron и его расписание.
- [x] Предложить создать отдельный Hermes skill для этой процедуры.
- [x] Пользователь подтвердил создание skill.
- [x] Создать skill `daily-knowledge-distillation`.
- [x] Валидировать skill.
- [x] Обновить cron, привязав skill.

## Verification

Готово, если:

- cron создан и имеет `job_id`;
- schedule соответствует 21:00 пользователя при текущем host timezone;
- prompt явно запрещает бездумное добавление;
- prompt требует проверять существующие docs и избегать дублей;
- prompt требует различать: added / updated / removed / skipped;
- prompt требует Telegram-отчёт;
- skill не создан без подтверждения.

## Risks / pitfalls

- Host timezone может измениться; тогда `0 18 * * *` перестанет соответствовать 21:00 UTC+5.
- `session_search` может не дать идеального среза именно за день; cron должен явно искать сегодняшние и недавние сессии, а не фантазировать.
- Модель может начать добавлять мусор в docs; prompt должен требовать conservative updates.
- Модель может удалять полезные записи слишком агрессивно; удаления допустимы только когда запись явно устарела/противоречит новым проверенным фактам.
- Секреты нельзя сохранять даже если они встречаются в истории.

## Status

Current status: done — cron created (`62e7a25f4e15`), skill `daily-knowledge-distillation` created and attached.

## Notes

Первую версию cron лучше сделать self-contained, без skill. После теста и подтверждения пользователя создать skill `daily-knowledge-distillation` и привязать его к cron.

Result:

- Skill `daily-knowledge-distillation` created under local Hermes skills.
- Cron `62e7a25f4e15` updated to load this skill.
- Prompt shortened: operational doctrine lives in the skill; cron prompt carries only run-specific context.
