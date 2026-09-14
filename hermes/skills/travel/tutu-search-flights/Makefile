# Единственный список команд проекта. Агент не изобретает команды и не держит
# их в голове. Повторяющаяся последовательность становится целью в тот же день.

.PHONY: check arch test lint types docs-check discover clean

## check — ворота. Задача не закрыта, пока команда не прошла и её вывод не показан.
check: arch test lint types docs-check
	@echo ""
	@echo "✓ ворота пройдены"

## arch — архитектурные тесты: направление зависимостей, чистота ядра, границы
arch:
	uv run pytest tests/architecture

## test — юнит-тесты и самопроверка обвязки
test:
	uv run pytest tests --ignore=tests/architecture

## lint — стиль и мёртвый код
lint:
	uvx ruff check .
	uvx ruff format --check .

## types — строгая типизация исходников
types:
	uv run mypy

## docs-check — команда, названная в документации, существует
docs-check:
	python3 scripts/check_docs.py

## discover — переснять спецификацию Tutu MCP в fixtures/. Единственная живая сеть.
discover:
	python3 probe.py meta
	python3 probe.py avia

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
