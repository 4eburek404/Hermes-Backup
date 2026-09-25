# Матрица требований и доказательств

Снимок статуса: 2026-09-25. Таблица связывает наблюдаемые требования с тестовыми
узлами и указывает фактический охват. Пройденные gates подтверждают только описанные
сценарии; непроверенные варианты остаются за их границами.

| Спецификация | Наблюдаемое требование | Test node IDs | Фактический охват и статус |
|---|---|---|---|
| S1 | Сохранить offers, цену, валюту, тарифные условия, времена и пагинацию успешного поиска. | `tests/test_successful_search.py::test_successful_search_preserves_source_results_prices_and_conditions` | Baseline fixture: один запрос в одну сторону, все 3 предложения и их тарифы. GREEN в make spec и make check. Не доказывает live-интеграцию или поведение всех маршрутов. |
| S2 | Production CLI использует MCP SDK client/session и вызывает `search_avia` с запросом пользователя. | `tests/test_production_sdk_search.py::test_production_cli_uses_sdk_search_avia_and_returns_product_result` | Настоящий SDK 2.2.0 и записанный in-memory server; 1 targeted node GREEN. HTTP и живой Tutu проверяет отдельный live smoke. |
| S3 | Tool-level error остаётся ошибкой, а не пустой выдачей. | `tests/test_tool_error.py::test_tool_error_is_reported_as_error_not_empty_search` | Настоящий SDK client/session получает записанную причину Tutu и поднимает ошибку; 1 targeted node GREEN. Другие transport/CLI формы проверяет S8. |
| S4 | Цена относится ко всей группе и остаётся связана с валютой и условиями своего fare variant. | `tests/test_party_pricing.py::test_party_total_price_is_not_multiplied_again` | Проверяет 2 offers и 8 вариантов: сумму, валюту, багаж, ручную кладь, возврат, обмен и изменяемость. GREEN; baggage/refundable mutation даёт RED. |
| S5 | Пересадки, self-transfer evidence и значения каждого сегмента сохраняются без выдуманных полей прямого рейса. | `tests/test_connections.py::test_connection_offer_preserves_segments_and_transfer_evidence` | Проверяет 2 offers и все сегменты записи; при `segments_count > 1` top-level `carrier` и `flight_number` остаются null. GREEN; мутация выдуманного top-level рейса даёт RED. |
| S6 | Round-trip сохраняет outbound и return как отдельные legs и каждый segment. | `tests/test_round_trip.py::test_round_trip_preserves_both_legs_and_outbound_route` | Проверяет оба offers, длительность каждого leg и все поля каждого сегмента. GREEN; мутация номера/перевозчика return-сегмента даёт RED. |
| S7 | Пустой результат сохраняет объяснение источника или счётчики фильтра. | `tests/test_empty_result_evidence.py::test_upstream_note_survives_empty_result`; `tests/test_empty_result_evidence.py::test_filter_drops_survive_empty_result` | Две формы пустого ответа: `upstream_note` и `post_filter_dropped_wrong_carrier`. GREEN; это не обобщает любую пустую выдачу до «рейсов нет». |
| S8 | CLI сообщает ошибки ввода, tool, transport, timeout и результата через exit status/stderr без успешного JSON в stdout. | Девять IDs перечислены в разделе S8 ниже и в [specs/09-cli-errors.md](../specs/09-cli-errors.md). | Девять targeted cases GREEN с настоящим SDK и in-memory server там, где применимо. Не распространяется на retry policy или живой transport. |

## Узлы S8

- `tests/test_cli_errors.py::test_invalid_json_uses_argparse_error_contract`
- `tests/test_cli_errors.py::test_non_object_json_uses_argparse_error_contract`
- `tests/test_cli_errors.py::test_tool_error_emits_full_reason_on_stderr`
- `tests/test_cli_errors.py::test_transport_error_emits_reason_on_stderr`
- `tests/test_cli_errors.py::test_timeout_emits_reason_on_stderr[with-message]`
- `tests/test_cli_errors.py::test_timeout_emits_reason_on_stderr[empty-message]`
- `tests/test_cli_errors.py::test_missing_text_fails_without_success_json`
- `tests/test_cli_errors.py::test_malformed_result_text_fails_without_success_json`
- `tests/test_cli_errors.py::test_invalid_search_result_fails_without_success_json`

## Gate evidence

- `make PYTHON=/Users/home/.venvs/hermes-backup/bin/python spec` — 17 passed.
- `TUTU_LIVE=1 PYTHONDONTWRITEBYTECODE=1 make PYTHON=/Users/home/.venvs/hermes-backup/bin/python check` — 22 passed, 1 live test deselected; Ruff passed, 16 Python files already formatted, documentation command checks passed for 16 files.
- `make PYTHON=/Users/home/.venvs/hermes-backup/bin/python live` — 1 passed in 2.71 seconds against live Tutu MCP.
- SDK/CLI targeted command `/Users/home/.venvs/hermes-backup/bin/python -m pytest -q tests/test_cli_errors.py tests/test_production_sdk_search.py tests/test_tool_error.py` — 11 passed.
- S4–S6 targeted command `/Users/home/.venvs/hermes-backup/bin/python -m pytest -q -p no:cacheprovider tests/test_party_pricing.py::test_party_total_price_is_not_multiplied_again tests/test_connections.py::test_connection_offer_preserves_segments_and_transfer_evidence tests/test_round_trip.py::test_round_trip_preserves_both_legs_and_outbound_route` — 3 passed.
- Three temporary in-memory `_project_text` mutations were detected (exit 1): changed return-leg segment flight/carrier; changed party-fare baggage/refundable; invented top-level carrier/flight_number for multi-segment offers. The mutations were not written to runtime files.

## External status

**Remote CI: GREEN.** [GitHub Actions run 36174651955](https://github.com/4eburek404/Hermes-Backup/actions/runs/36174651955) passed for commit `8f6dce235d69f5ef1dc14debb58a8ba01ac5a145` on `new-tutu` (2026-09-25), installing the locked dependencies and running `make check` on Ubuntu with Python 3.13.

**Branch protection: NOT VERIFIED.** A successful workflow run does not establish that the check is required for merging.

**Agent evaluation: PENDING.** The external harness path/identifier is not available in this workspace. Do not claim an evaluation run or verdict. The required artifact must identify commit and model, exact user request, SDK arguments and result, trajectory, final answer, and separate outcome and trajectory verdicts. Agent evaluation remains separate from product specs, local gates, and live smoke.
