# Plan: Test DeepSeek V4 Pro for knowledge distillation

## Goal

Проверить `deepseek-v4-pro:cloud` на той же real-data задаче дистилляции знаний, где уже тестировались `glm-5.1:cloud` и `gpt-5.5/openai-codex`.

## Context

- Модель добавлена в Hermes config и доступна в Ollama как `deepseek-v4-pro:cloud`.
- Предыдущий real-data prompt: `/tmp/kd_realdata_prompt_short.md`.
- Предыдущие результаты: `/tmp/kd_realdata_short_glm.json`, `/tmp/kd_realdata_short_codex.json`, `/tmp/kd_realdata_glm_vs_gpt55_raw.md`.
- Benchmark mode: целевые docs не редактировать по результатам модели; raw outputs/result files только в `/tmp`.

## Non-goals

- Не pin'ить модель на cron.
- Не менять daily distillation cron.
- Не применять предложения модели к docs.
- Не менять default model.

## Steps

- [x] Проверить наличие prompt и предыдущих result-файлов.
- [x] Запустить `deepseek-v4-pro:cloud` на том же real-data prompt с отдельным timeout/result file.
- [x] Сравнить с GLM/GPT-5.5 по latency, output size и качеству distillation decisions.
- [x] Собрать raw report в `/tmp`.
- [x] Закрыть план и кратко отчитаться.

## Verification

- Result file для DeepSeek создан или явно зафиксирован timeout/error.
- Нет изменений в target docs по предложениям модели.
- Сравнение отделяет проверенные факты от интерпретации.

## Risks / pitfalls

- DeepSeek V4 Pro может долго уходить в thinking; нужен отдельный timeout.
- Если модель не успеет на full real-data prompt, нужен короткий retry или зафиксировать ограничение.

## Status

Current status: done

## Notes

Keep user-facing report concise.
