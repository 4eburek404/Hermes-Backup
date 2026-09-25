# S8 — ошибки production CLI

Эта исполняемая спецификация задаёт наблюдаемый контракт CLI для некорректного
ввода и ошибок поиска.

## Дано

Production CLI получает один позиционный аргумент с JSON. Ошибки поиска
воспроизводятся детерминированно: tool-level error, отсутствие текста и
некорректный текст результата приходят от локального in-memory MCP `Server`
через настоящий MCP SDK 2.2.0; транспортная ошибка и таймаут внедряются на
границе создания MCP client. Для вложенной `ExceptionGroup` причина берётся
из leaf exception и должна сохраниться в stderr.

## Когда

CLI разбирает аргумент или выполняет живой поиск.

## Тогда

- невалидный JSON и JSON-значение не-объект завершают argparse с кодом 2;
  stdout пуст, stderr содержит usage и причину;
- tool-level error выводит полный текст причины в stderr и завершается с кодом 1;
- транспортная ошибка и таймаут завершаются с кодом 1, сохраняя причину в stderr; если у исключения нет сообщения, stderr содержит имя его типа;
- отсутствующий текст, синтаксически некорректный текст и JSON результата,
  не соответствующий модели поиска, завершаются с кодом 1 и сообщением в stderr;
- при любой ошибке поиска stdout пуст: успешный JSON и `offers: []` не выдаются.

## Исполняемые проверки и граница

[test_cli_errors.py](../tests/test_cli_errors.py) закрепляет каждый исход:

- `test_invalid_json_uses_argparse_error_contract`
- `test_non_object_json_uses_argparse_error_contract`
- `test_tool_error_emits_full_reason_on_stderr`
- `test_transport_error_emits_reason_on_stderr`
- `test_timeout_emits_reason_on_stderr[with-message]`
- `test_timeout_emits_reason_on_stderr[empty-message]`
- `test_missing_text_fails_without_success_json`
- `test_malformed_result_text_fails_without_success_json`
- `test_invalid_search_result_fails_without_success_json`

Проверки с MCP проходят через настоящий SDK client/session/call на in-memory
server; два сетевых сбоя внедряются на границе создания client. HTTP и живой
Tutu не используются. Спецификация закрепляет коды выхода и потоки CLI, без
повторов, политики таймаутов или поведения при живой сети.
