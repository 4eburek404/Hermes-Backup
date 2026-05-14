PYTHON ?= python3
PREFIX ?= $(HOME)/.local
BIN := $(PREFIX)/bin/knowledge
PROJECT := $(CURDIR)

.PHONY: install-local test smoke

install-local:
	mkdir -p "$(PREFIX)/bin"
	printf '%s\n' '#!/usr/bin/env bash' 'PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" exec $(PYTHON) -m knowledge_cli "$$@"' > "$(BIN)"
	chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m knowledge_cli --json doctor
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m knowledge_cli --json docs inventory --max-depth 2
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m knowledge_cli --json plans audit
	PYTHONPATH="$(PROJECT):$${PYTHONPATH:-}" $(PYTHON) -m knowledge_cli --json memory metrics
