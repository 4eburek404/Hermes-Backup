# S7 — пустая выдача сохраняет объяснение источника и фильтров

## Дано

Используются записанные ответы:
- `fixtures/avia/past-date.json`, где Tutu вернул пустую выдачу с `upstream_note`;
- `fixtures/avia/unknown-carrier.json`, где предложения были отброшены фильтром.

## Когда

Продукт обрабатывает эти ответы.

## Тогда

- пустой список предложений не уничтожает объяснение источника;
- `upstream_note` сохраняется, если он присутствует;
- ненулевые `post_filter_dropped_*` сохраняются вместе с их фактическими значениями;
- `total_matched_exact` сохраняется;
- эти случаи остаются отличимы от пустой выдачи без объяснения и без срабатывания фильтров.

## Исполнение

Проверки выполняются на записанных raw MCP responses без сети:
[tests/test_empty_result_evidence.py](../tests/test_empty_result_evidence.py),
node IDs `test_upstream_note_survives_empty_result` и
`test_filter_drops_survive_empty_result`. Эта спецификация не утверждает,
что любая пустая выдача означает «рейсов нет».
