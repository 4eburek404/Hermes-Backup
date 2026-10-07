# Offline reassessment: pytest evidence v1

## Исправленные источники ложного evidence

До исправления контрспецификации дали ожидаемый RED на исходном evaluator (`7aea9e4fd7184a735fe813d50b4a87e3441c95d2`): **3 failed, 5 passed**. Падения были именно на stale evidence после write_file, stale evidence после edit_file и фиктивном `run_app`; положительный real-helper control при этом оставался зелёным.

- **Устаревший снимок тестов.** В исполняемой фикстуре сначала проходят три теста `regular/default/shout`, затем успешный `write_file` заменяет `tests/test_app.py` единственным `assert True`; реальный pytest возвращает `1 passed`. Прежние проверки больше не засчитываются. Для фактической замены через `edit_file` снимок тоже инвалидируется. Содержимое, которое нельзя достоверно реконструировать, остаётся `UNCONFIRMED`.
- **Поддельный `run_app`.** Фикстурный helper возвращает заранее созданные `returncode/stdout`, не запуская приложение; pytest действительно проходит, но поведение приложения не подтверждается. Положительный контроль использует fixture-helper с `subprocess.run([sys.executable, 'app.py', *args], ...)` и исполняемую `app.py`; распознаются все три соответствующих probes.
- **Неполный/противоречивый pytest.** Успешный exit code без совпадения количества тестов, filtered/selected tests и skipped tests не подтверждают реконструированный полный набор.

Исправления ограничены распознаванием доказательств: воспроизводимый снимок из точного содержимого успешного `write_file`, консервативная инвалидация при неподдерживаемых изменениях, узкое AST-распознавание реального fixture-helper и сверка полного набора тестов с pytest summary. Неизвестные формы остаются `UNCONFIRMED`; общий stdout составной команды не распределяется между процессами по ожидаемым строкам. Универсальные интерпретаторы Python/shell не добавлялись.

## Окончательные проверки

- `python3 -m pytest -q tests/contract/test_development_workflow_pytest_evidence.py` — **8 passed**.
- `python3 -m pytest -q tests/contract` — **133 passed**.
- Новых Hermes/LLM-прогонов не было; команды, записанные в исторических трассах, не исполнялись.

## Пересчёт опубликованных трасс

Оценки вычислены evaluator-ом по исходному manifest и прежним критериям Trajectory; результаты предыдущего пересчёта не подставлялись.

- **r1 — Outcome PASS, Trajectory PASS.** RED: [raw trace L20](../../runs/20261006T073402Z/published-bdd-skill/runs/r1/raw_stream.jsonl#L20); production change: [L22](../../runs/20261006T073402Z/published-bdd-skill/runs/r1/raw_stream.jsonl#L22); GREEN: [L24–25](../../runs/20261006T073402Z/published-bdd-skill/runs/r1/raw_stream.jsonl#L24). Evidence и event references — [`r1/evidence.json`](r1/evidence.json), [`r1/score.json`](r1/score.json), [`r1/event-refs.json`](r1/event-refs.json).
- **r2 — Outcome PASS, Trajectory PASS.** RED: [L22](../../runs/20261006T073402Z/published-bdd-skill/runs/r2/raw_stream.jsonl#L22); production change: [L24](../../runs/20261006T073402Z/published-bdd-skill/runs/r2/raw_stream.jsonl#L24); GREEN: [L26–27](../../runs/20261006T073402Z/published-bdd-skill/runs/r2/raw_stream.jsonl#L26). Evidence и event references — [`r2/evidence.json`](r2/evidence.json), [`r2/score.json`](r2/score.json), [`r2/event-refs.json`](r2/event-refs.json).
- **r3 — Outcome PASS, Trajectory FAIL.** До изменения production trace содержит только сохранённый regular-тест в прочитанном файле ([L12](../../runs/20261006T073402Z/published-bdd-skill/runs/r3/raw_stream.jsonl#L12)); попытка с shout/default заканчивается RED ([L18–19](../../runs/20261006T073402Z/published-bdd-skill/runs/r3/raw_stream.jsonl#L18)); production меняется на [L20–21](../../runs/20261006T073402Z/published-bdd-skill/runs/r3/raw_stream.jsonl#L20), после чего GREEN виден на [L24–25](../../runs/20261006T073402Z/published-bdd-skill/runs/r3/raw_stream.jsonl#L24). Поэтому default не имеет достаточного pre-change evidence; `current observable behavior` остаётся `UNCONFIRMED`. Подтверждённого нарушения порядка нет. Evidence и event references — [`r3/evidence.json`](r3/evidence.json), [`r3/score.json`](r3/score.json), [`r3/event-refs.json`](r3/event-refs.json).

В event references указаны исходные номера строк и SHA-256 конкретных call/result JSONL-строк; сами исходные трассы не копировались в этот пакет.

## Хеши и воспроизведение

Перед и после повторного извлечения совпали все 10 хешей manifest, исходных evidence, scores и raw streams; см. [`source-checksums.json`](source-checksums.json). Проверка исходных pinned-хешей также завершилась успешно.

Команда воспроизведения:

```sh
python3 evals/development-workflow/reassess_published.py
```

Результат повторён в отдельной чистой копии, содержащей только опубликованные для расчёта evaluator/harness, script, manifest, checksum pins и входы r1–r3. Все 12 выходных файлов (evidence, scores, event refs и provenance) совпали побайтно; SHA-256 приведены в [`clean-copy-verification.json`](clean-copy-verification.json). Программа отказывается перезаписывать непустой каталог результатов.

## Ограничения

Распознаватель намеренно ограничен fixture-формой `run_app` с прямым вызовом `subprocess.run` для `sys.executable app.py`, простыми полными pytest-наборами и поддерживаемым V4A patch. Изменённая/неизвестная форма helper, неоднозначное изменение тестового файла, неполная или противоречивая pytest-сводка остаются `UNCONFIRMED`. Другие способы редактирования и более сложные тестовые/ shell-конструкции не интерпретируются.
