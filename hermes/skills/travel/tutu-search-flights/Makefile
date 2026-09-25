# Все Python-команды используют один выбранный интерпретатор.
PYTHON ?= python3

.PHONY: check test spec live lint check-doc-commands discover clean

check: test lint check-doc-commands

## Все тесты без live-маркера; TUTU_LIVE не включает сетевые тесты в gate.
test:
	$(PYTHON) -m pytest -m 'not live' tests

## Детерминированные executable product specifications.
spec:
	$(PYTHON) -m pytest -m 'not live' \
		tests/test_successful_search.py \
		tests/test_production_sdk_search.py \
		tests/test_tool_error.py \
		tests/test_party_pricing.py \
		tests/test_connections.py \
		tests/test_round_trip.py \
		tests/test_empty_result_evidence.py \
		tests/test_cli_errors.py

## Живая интеграционная проверка Tutu MCP через SDK; только вручную.
live:
	TUTU_LIVE=1 $(PYTHON) -m pytest -m live tests/test_live_search.py

## Стиль файлов Python.
lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

## Проверяет, что команды make ..., указанные в документации, существуют в Makefile.
check-doc-commands:
	$(PYTHON) scripts/check_doc_commands.py

## Обновляет исследование Tutu MCP через probe.py (живая сеть).
discover:
	$(PYTHON) probe.py meta
	$(PYTHON) probe.py avia

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
