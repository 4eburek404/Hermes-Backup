PYTHON ?= python3
PREFIX ?= $(HOME)/.local
BIN := $(PREFIX)/bin/hh-ru
PROJECT := $(CURDIR)

.PHONY: install-local test smoke

install-local:
	mkdir -p "$(PREFIX)/bin"
	printf '%s\n' '#!/usr/bin/env bash' 'PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" exec $(PYTHON) -m hh_ru_cli "$$@"' > "$(BIN)"
	chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m hh_ru_cli --json doctor
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m hh_ru_cli --json vacancies search Python --area 1 --per-page 5 --dry-run

