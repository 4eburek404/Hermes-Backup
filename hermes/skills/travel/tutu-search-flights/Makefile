# Единая точка запуска повторяющихся действий проекта.

.PHONY: check test spec live lint check-doc-commands discover clean

check: test lint check-doc-commands

## Все тесты, включая исполняемые продуктовые спецификации.
test:
	uv run --extra dev pytest tests

## Первая продуктовая спецификация (RED до реализации поиска).
spec:
	uv run --extra dev pytest tests/test_successful_search.py

## Живая интеграционная проверка Tutu MCP через SDK; только вручную.
live:
	TUTU_LIVE=1 uv run --extra dev pytest -m live tests/test_live_search.py

## Стиль файлов Python.
lint:
	uvx ruff check .
	uvx ruff format --check .

## Проверяет, что команды make ..., указанные в документации, существуют в Makefile.
check-doc-commands:
	python3 scripts/check_doc_commands.py

## Обновляет исследование Tutu MCP через probe.py (живая сеть).
discover:
	python3 probe.py meta
	python3 probe.py avia

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
