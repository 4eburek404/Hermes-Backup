PYTHON ?= python3
PREFIX ?= $(HOME)/.local
BIN := $(PREFIX)/bin/article
PROJECT := $(CURDIR)

.PHONY: install-local test smoke

install-local:
	mkdir -p "$(PREFIX)/bin"
	printf '%s\n' '#!/usr/bin/env bash' 'PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" exec $(PYTHON) -m article_cli "$$@"' > "$(BIN)"
	chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m article_cli --json doctor
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m article_cli --json read tests/fixtures/sample.html
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m article_cli summary-input tests/fixtures/sample.html --max-chars 500
